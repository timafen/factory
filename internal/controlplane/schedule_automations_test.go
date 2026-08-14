package controlplane

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"github.com/owainlewis/factory/internal/protocol"
)

func TestCronScheduleValidationAndVixieDaySemantics(t *testing.T) {
	for _, test := range []struct {
		name       string
		cron       string
		timezone   string
		errorMatch string
	}{
		{name: "seconds", cron: "0 0 9 * * *", timezone: "UTC", errorMatch: "five fields"},
		{name: "alias", cron: "@daily", timezone: "UTC", errorMatch: "five fields"},
		{name: "question", cron: "0 9 ? * *", timezone: "UTC", errorMatch: "unsupported"},
		{name: "embedded timezone", cron: "CRON_TZ=UTC 0 9 * * *", timezone: "UTC", errorMatch: "five fields"},
		{name: "bad step", cron: "*/0 9 * * *", timezone: "UTC", errorMatch: "positive"},
		{name: "bad zone", cron: "0 9 * * *", timezone: "Mars/Olympus", errorMatch: "IANA"},
	} {
		t.Run(test.name, func(t *testing.T) {
			_, _, _, err := parseCronSchedule(test.cron, test.timezone)
			if err == nil || !stringsContain(err.Error(), test.errorMatch) {
				t.Fatalf("parse error = %v, want %q", err, test.errorMatch)
			}
		})
	}

	schedule, _, _, err := parseCronSchedule("0 9 1 * MON", "UTC")
	if err != nil {
		t.Fatal(err)
	}
	next, err := schedule.Next(time.Date(2026, 6, 1, 9, 0, 0, 0, time.UTC))
	if err != nil {
		t.Fatal(err)
	}
	want := time.Date(2026, 6, 8, 9, 0, 0, 0, time.UTC)
	if !next.Equal(want) {
		t.Fatalf("Vixie OR next = %s, want %s", next, want)
	}

	steppedWildcard, _, _, err := parseCronSchedule("0 9 */2 * MON", "UTC")
	if err != nil {
		t.Fatal(err)
	}
	next, err = steppedWildcard.Next(time.Date(2026, 6, 7, 8, 0, 0, 0, time.UTC))
	if err != nil {
		t.Fatal(err)
	}
	want = time.Date(2026, 6, 8, 9, 0, 0, 0, time.UTC)
	if !next.Equal(want) {
		t.Fatalf("Vixie stepped wildcard next = %s, want %s", next, want)
	}
}

func TestCronScheduleDSTOverlapAndMissingLocalTime(t *testing.T) {
	overlap, _, _, err := parseCronSchedule("30 1 25 OCT *", "Europe/London")
	if err != nil {
		t.Fatal(err)
	}
	first, err := overlap.Next(time.Date(2026, 10, 24, 23, 59, 0, 0, time.UTC))
	if err != nil {
		t.Fatal(err)
	}
	second, err := overlap.Next(first)
	if err != nil {
		t.Fatal(err)
	}
	if !first.Equal(time.Date(2026, 10, 25, 0, 30, 0, 0, time.UTC)) ||
		!second.Equal(time.Date(2026, 10, 25, 1, 30, 0, 0, time.UTC)) {
		t.Fatalf("overlap instants = %s and %s", first, second)
	}

	missing, _, _, err := parseCronSchedule("30 1 29 MAR *", "Europe/London")
	if err != nil {
		t.Fatal(err)
	}
	next, err := missing.Next(time.Date(2026, 3, 28, 23, 59, 0, 0, time.UTC))
	if err != nil {
		t.Fatal(err)
	}
	if next.Year() == 2026 {
		t.Fatalf("nonexistent 2026 local time unexpectedly matched %s", next)
	}
}

func createScheduleAutomationFixture(
	t *testing.T,
	now *time.Time,
	withWorker bool,
) (*Store, protocol.AutomationDetail) {
	t.Helper()
	store := newTestStore(t)
	store.now = func() time.Time { return *now }
	workflow := createTestWorkflow(t, store, "schedule-workflow", "Scheduled maintenance", "Inspect the repository and perform the scheduled maintenance.")
	repository := createManagedTestRepository(t, store, "github.com/owainlewis/factory")
	if withWorker {
		_, err := store.RegisterWorker(context.Background(), "schedule-worker", protocol.WorkerRegistration{
			Name: "schedule-worker", WorkerVersion: "test", RuntimeVersion: "test",
			Capacity: 1, Health: "healthy", AcceptsManagedRepositories: true,
			ManagedRepositoryIDs: []string{repository.ID},
		})
		if err != nil {
			t.Fatal(err)
		}
	}
	detail, created, err := store.CreateAutomation(context.Background(), protocol.CreateAutomationRequest{
		RequestKey: "schedule-create", Title: "Daily maintenance",
		WorkflowID: workflow.Workflow.ID, RepositoryID: repository.ID,
		Context: "Use the safe managed repository only.", TimeoutSeconds: 3600,
		Trigger: protocol.AutomationTrigger{
			Type: protocol.AutomationTriggerSchedule, Cron: "0 9 * * *", Timezone: "Europe/London",
		},
	})
	if err != nil || !created {
		t.Fatalf("create schedule = created %v, error %v", created, err)
	}
	return store, detail
}

type scheduleRetryIdentity struct {
	automationID, occurrenceID, taskID, taskIDSnapshot, taskRequestKey, executionID string
	occurrences, scheduleOccurrences, tasks, executions                             int
}

func captureScheduleRetryIdentity(t *testing.T, store *Store, automationID string) scheduleRetryIdentity {
	t.Helper()
	var value scheduleRetryIdentity
	if err := store.db.QueryRow(`
		SELECT occurrence.automation_id, occurrence.id, occurrence.task_id,
		       occurrence.task_id_snapshot, task.request_key, execution.id
		FROM automation_occurrences occurrence
		JOIN tasks task ON task.id = occurrence.task_id
		JOIN executions execution ON execution.task_id = task.id
		WHERE occurrence.automation_id = ?
	`, automationID).Scan(
		&value.automationID, &value.occurrenceID, &value.taskID,
		&value.taskIDSnapshot, &value.taskRequestKey, &value.executionID,
	); err != nil {
		t.Fatal(err)
	}
	for table, destination := range map[string]*int{
		"automation_occurrences":          &value.occurrences,
		"automation_schedule_occurrences": &value.scheduleOccurrences,
		"tasks":                           &value.tasks,
		"executions":                      &value.executions,
	} {
		if err := store.db.QueryRow(`SELECT COUNT(*) FROM ` + table).Scan(destination); err != nil {
			t.Fatal(err)
		}
	}
	return value
}

func captureRetryState(t *testing.T, store *Store, executionID string) (state, diagnostic string, retries, attempts int) {
	t.Helper()
	if err := store.db.QueryRow(`
		SELECT execution.state, occurrence.diagnostic, execution.retry_count,
		       (SELECT COUNT(*) FROM attempts WHERE execution_id = execution.id)
		FROM executions execution
		JOIN automation_occurrences occurrence ON occurrence.task_id = execution.task_id
		WHERE execution.id = ?
	`, executionID).Scan(&state, &diagnostic, &retries, &attempts); err != nil {
		t.Fatal(err)
	}
	return state, diagnostic, retries, attempts
}

func claimScheduleOccurrence(
	t *testing.T,
	store *Store,
	detail protocol.AutomationDetail,
	now *time.Time,
	kind string,
	requestID string,
	token int,
) *protocol.Claim {
	t.Helper()
	enabled := enableAutomation(t, store, detail.Automation.ID)
	if kind == "scheduled" {
		*now = *enabled.Automation.NextDueAt
		if _, err := store.RegisterWorker(context.Background(), "schedule-worker", protocol.WorkerRegistration{
			Name: "schedule-worker", WorkerVersion: "test", RuntimeVersion: "test",
			Capacity: 1, Health: "healthy", AcceptsManagedRepositories: true,
			ManagedRepositoryIDs: []string{detail.Automation.RepositoryID},
		}); err != nil {
			t.Fatal(err)
		}
		if err := store.processDueSchedules(context.Background(), 10); err != nil {
			t.Fatal(err)
		}
	} else {
		if _, err := store.RunAutomationNow(context.Background(), detail.Automation.ID, protocol.RunAutomationRequest{RequestKey: requestID}); err != nil {
			t.Fatal(err)
		}
	}
	if err := store.dispatchPendingOccurrences(context.Background(), 10); err != nil {
		t.Fatal(err)
	}
	claim, err := store.Claim(context.Background(), "schedule-worker", protocol.ClaimRequest{RequestID: requestID, LeaseToken: fmt.Sprintf("%064x", token)})
	if err != nil || claim == nil {
		t.Fatalf("claim %s occurrence = %#v, error %v", kind, claim, err)
	}
	return claim
}

func TestSchedulePreviewEnableDueDispatchAndIdempotencyUseFakeClock(t *testing.T) {
	now := time.Date(2026, 8, 1, 7, 0, 0, 0, time.UTC) // 08:00 BST.
	store, detail := createScheduleAutomationFixture(t, &now, true)
	service := newAutomationService(store, nil, fakeGitHubIssueLister{})
	preview, err := service.Test(context.Background(), detail.Automation.ID)
	if err != nil || preview.NextDueAt == nil || !preview.NextDueAt.Equal(time.Date(2026, 8, 1, 8, 0, 0, 0, time.UTC)) {
		t.Fatalf("schedule preview = %#v, error %v", preview, err)
	}
	afterPreview, err := store.Automation(context.Background(), detail.Automation.ID)
	if err != nil || len(afterPreview.Occurrences) != 0 || afterPreview.Automation.NextDueAt != nil {
		t.Fatalf("preview mutated state = %#v, error %v", afterPreview, err)
	}
	enabled, err := store.SetAutomationEnabled(context.Background(), detail.Automation.ID, true, false)
	if err != nil || enabled.Automation.NextDueAt == nil || !enabled.Automation.NextDueAt.Equal(*preview.NextDueAt) {
		t.Fatalf("enable schedule = %#v, error %v", enabled, err)
	}
	now = *preview.NextDueAt
	if _, err := store.RegisterWorker(context.Background(), "schedule-worker", protocol.WorkerRegistration{
		Name: "schedule-worker", WorkerVersion: "test", RuntimeVersion: "test",
		Capacity: 1, Health: "healthy", AcceptsManagedRepositories: true,
		ManagedRepositoryIDs: []string{detail.Automation.RepositoryID},
	}); err != nil {
		t.Fatal(err)
	}
	if err := store.processDueSchedules(context.Background(), 100); err != nil {
		t.Fatal(err)
	}
	if err := store.processDueSchedules(context.Background(), 100); err != nil {
		t.Fatal(err)
	}
	if err := store.dispatchPendingOccurrences(context.Background(), 100); err != nil {
		t.Fatal(err)
	}
	if err := store.dispatchPendingOccurrences(context.Background(), 100); err != nil {
		t.Fatal(err)
	}
	current, err := store.Automation(context.Background(), detail.Automation.ID)
	if err != nil {
		t.Fatal(err)
	}
	if len(current.Occurrences) != 1 || current.Occurrences[0].Task == nil ||
		current.Occurrences[0].Kind != "scheduled" || current.Occurrences[0].ScheduledAt == nil ||
		!current.Occurrences[0].ScheduledAt.Equal(now) {
		t.Fatalf("scheduled occurrence = %#v", current.Occurrences)
	}
	if current.Automation.NextDueAt == nil || !current.Automation.NextDueAt.After(now) || current.Automation.DispatchedCount != 1 {
		t.Fatalf("schedule counters/cursor = %#v", current.Automation)
	}
	task, err := store.Task(context.Background(), current.Occurrences[0].Task.ID)
	if err != nil {
		t.Fatal(err)
	}
	for _, required := range []string{"Schedule instruction:", `"type":"schedule"`, `"kind":"scheduled"`, `"timezone":"Europe/London"`} {
		if !stringsContain(task.ResolvedPrompt, required) {
			t.Fatalf("schedule prompt missing %q:\n%s", required, task.ResolvedPrompt)
		}
	}
	if stringsContain(task.ResolvedPrompt, "Use authenticated gh") || stringsContain(task.ResolvedPrompt, "provider item") && !stringsContain(task.ResolvedPrompt, "There is no provider item") {
		t.Fatalf("schedule prompt contains provider revalidation: %s", task.ResolvedPrompt)
	}
}

func TestScheduleAutomationUpdateNormalizesAndRecoversLostResponse(t *testing.T) {
	now := time.Date(2026, 8, 1, 7, 0, 0, 0, time.UTC)
	store, detail := createScheduleAutomationFixture(t, &now, false)
	input := protocol.UpdateAutomationRequest{
		ExpectedVersion: 1, Title: "Weekday maintenance", WorkflowID: detail.Automation.WorkflowID,
		Context: "Updated schedule context.", TimeoutSeconds: 7200,
		Trigger: protocol.AutomationTrigger{Type: protocol.AutomationTriggerSchedule, Cron: " 30  10 * * MON-FRI ", Timezone: " UTC "},
	}
	updated, err := store.UpdateAutomation(context.Background(), detail.Automation.ID, input)
	if err != nil || updated.Automation.Version != 2 || updated.Automation.Trigger.Cron != "30 10 * * MON-FRI" || updated.Automation.Trigger.Timezone != "UTC" {
		t.Fatalf("update schedule = %#v, error %v", updated.Automation, err)
	}
	replayed, err := store.UpdateAutomation(context.Background(), detail.Automation.ID, input)
	if err != nil || replayed.Automation.Version != 2 {
		t.Fatalf("lost update replay = %#v, error %v", replayed.Automation, err)
	}
	input.ExpectedVersion = 2
	input.Trigger.Cron = "0 0 9 * * *"
	_, err = store.UpdateAutomation(context.Background(), detail.Automation.ID, input)
	assertErrorCode(t, err, "invalid_cron")
	input.Trigger.Cron = "0 9 * * *"
	input.Trigger.Timezone = "Not/AZone"
	_, err = store.UpdateAutomation(context.Background(), detail.Automation.ID, input)
	assertErrorCode(t, err, "invalid_timezone")
}

func TestScheduleStartupCatchUpAdvancesToFirstFutureInstant(t *testing.T) {
	now := time.Date(2026, 8, 1, 7, 0, 0, 0, time.UTC)
	store, detail := createScheduleAutomationFixture(t, &now, false)
	enabled := enableAutomation(t, store, detail.Automation.ID)
	storedDue := *enabled.Automation.NextDueAt
	now = time.Date(2026, 8, 4, 12, 0, 0, 0, time.UTC)
	if err := store.recoverAutomationRuntime(context.Background()); err != nil {
		t.Fatal(err)
	}
	if err := store.processDueSchedules(context.Background(), 100); err != nil {
		t.Fatal(err)
	}
	if err := store.processDueSchedules(context.Background(), 100); err != nil {
		t.Fatal(err)
	}
	current, err := store.Automation(context.Background(), detail.Automation.ID)
	if err != nil {
		t.Fatal(err)
	}
	if len(current.Occurrences) != 1 || current.Occurrences[0].ScheduledAt == nil ||
		!current.Occurrences[0].ScheduledAt.Equal(storedDue) || current.Occurrences[0].Diagnostic != "catch_up; 3 later scheduled instants skipped" {
		t.Fatalf("catch-up occurrence = %#v", current.Occurrences)
	}
	if current.Automation.SkippedCount != 3 {
		t.Fatalf("catch-up skipped count = %d, want 3", current.Automation.SkippedCount)
	}
	if current.Automation.NextDueAt == nil || !current.Automation.NextDueAt.After(now) {
		t.Fatalf("catch-up cursor = %#v", current.Automation.NextDueAt)
	}
}

func TestScheduleCatchUpClassificationStartsAfterDueMinute(t *testing.T) {
	for _, test := range []struct {
		name           string
		offset         time.Duration
		wantDiagnostic string
	}{
		{name: "exact due instant"},
		{name: "milliseconds after due", offset: 100 * time.Millisecond},
		{name: "end of due minute", offset: 59*time.Second + 999*time.Millisecond},
		{name: "start of next minute", offset: time.Minute, wantDiagnostic: "catch_up"},
	} {
		t.Run(test.name, func(t *testing.T) {
			now := time.Date(2026, 8, 1, 7, 0, 0, 0, time.UTC)
			store, detail := createScheduleAutomationFixture(t, &now, false)
			enabled := enableAutomation(t, store, detail.Automation.ID)
			now = enabled.Automation.NextDueAt.Add(test.offset)
			if err := store.recoverAutomationRuntime(context.Background()); err != nil {
				t.Fatal(err)
			}
			if err := store.processDueSchedules(context.Background(), 100); err != nil {
				t.Fatal(err)
			}
			current, err := store.Automation(context.Background(), detail.Automation.ID)
			if err != nil {
				t.Fatal(err)
			}
			if len(current.Occurrences) != 1 || current.Occurrences[0].Diagnostic != test.wantDiagnostic {
				t.Fatalf("occurrences = %#v, want diagnostic %q", current.Occurrences, test.wantDiagnostic)
			}
			if current.Automation.SkippedCount != 0 {
				t.Fatalf("skipped count = %d, want 0", current.Automation.SkippedCount)
			}
		})
	}
}

func TestScheduleDisabledDependencyCatchUpCountsMissedInstants(t *testing.T) {
	now := time.Date(2026, 8, 1, 7, 0, 0, 0, time.UTC)
	store, detail := createScheduleAutomationFixture(t, &now, false)
	enabled := enableAutomation(t, store, detail.Automation.ID)
	if _, err := store.SetWorkflowEnabled(context.Background(), detail.Automation.WorkflowID, false); err != nil {
		t.Fatal(err)
	}
	now = time.Date(2026, 8, 4, 12, 0, 0, 0, time.UTC)
	if err := store.processDueSchedules(context.Background(), 100); err != nil {
		t.Fatal(err)
	}
	current, err := store.Automation(context.Background(), detail.Automation.ID)
	if err != nil {
		t.Fatal(err)
	}
	if len(current.Occurrences) != 1 || current.Occurrences[0].ScheduledAt == nil ||
		!current.Occurrences[0].ScheduledAt.Equal(*enabled.Automation.NextDueAt) ||
		current.Occurrences[0].Diagnostic != "workflow_disabled; catch_up; 3 later scheduled instants skipped" {
		t.Fatalf("disabled catch-up occurrence = %#v", current.Occurrences)
	}
	if current.Automation.SkippedCount != 4 {
		t.Fatalf("disabled catch-up skipped count = %d, want 4", current.Automation.SkippedCount)
	}
	if current.Automation.NextDueAt == nil || !current.Automation.NextDueAt.After(now) {
		t.Fatalf("disabled catch-up cursor = %#v", current.Automation.NextDueAt)
	}
}

func TestScheduleRunNowConcurrentReplayDisableAndCursorIsolation(t *testing.T) {
	now := time.Date(2026, 8, 1, 7, 0, 0, 0, time.UTC)
	store, detail := createScheduleAutomationFixture(t, &now, true)
	enabled := enableAutomation(t, store, detail.Automation.ID)
	due := *enabled.Automation.NextDueAt
	const callers = 8
	var wait sync.WaitGroup
	errorsSeen := make(chan error, callers)
	for range callers {
		wait.Add(1)
		go func() {
			defer wait.Done()
			_, err := store.RunAutomationNow(context.Background(), detail.Automation.ID, protocol.RunAutomationRequest{RequestKey: "concurrent-run"})
			errorsSeen <- err
		}()
	}
	wait.Wait()
	close(errorsSeen)
	for err := range errorsSeen {
		if err != nil {
			t.Fatalf("concurrent Run now: %v", err)
		}
	}
	if err := store.dispatchPendingOccurrences(context.Background(), 100); err != nil {
		t.Fatal(err)
	}
	if _, err := store.SetAutomationEnabled(context.Background(), detail.Automation.ID, false, false); err != nil {
		t.Fatal(err)
	}
	if _, err := store.RunAutomationNow(context.Background(), detail.Automation.ID, protocol.RunAutomationRequest{RequestKey: "concurrent-run"}); err != nil {
		t.Fatalf("lost-response replay after disable: %v", err)
	}
	_, err := store.RunAutomationNow(context.Background(), detail.Automation.ID, protocol.RunAutomationRequest{RequestKey: "new-run"})
	assertErrorCode(t, err, "automation_disabled")
	current, err := store.Automation(context.Background(), detail.Automation.ID)
	if err != nil {
		t.Fatal(err)
	}
	if len(current.Occurrences) != 1 || current.Occurrences[0].Kind != "run_now" || current.Occurrences[0].Task == nil {
		t.Fatalf("concurrent Run now occurrences = %#v", current.Occurrences)
	}
	task, err := store.Task(context.Background(), current.Occurrences[0].Task.ID)
	if err != nil || task.Task.State != "queued" {
		t.Fatalf("disable changed the admitted task = %#v, error %v", task.Task, err)
	}
	if current.Automation.NextDueAt != nil {
		t.Fatalf("disabled schedule retained due cursor %s", current.Automation.NextDueAt)
	}
	var scheduledCursorCount int
	if err := store.db.QueryRow(`SELECT COUNT(*) FROM automation_schedule_occurrences WHERE automation_id = ? AND kind = 'run_now'`, detail.Automation.ID).Scan(&scheduledCursorCount); err != nil {
		t.Fatal(err)
	}
	if scheduledCursorCount != 1 || due.IsZero() {
		t.Fatalf("Run now identity count = %d, original due = %s", scheduledCursorCount, due)
	}
}

func TestScheduleAutomationFailedExecutionRetriesOnceAndIsIdempotent(t *testing.T) {
	now := time.Date(2026, 8, 1, 7, 0, 0, 0, time.UTC)
	store, detail := createScheduleAutomationFixture(t, &now, true)
	enableAutomation(t, store, detail.Automation.ID)
	if _, err := store.RunAutomationNow(context.Background(), detail.Automation.ID, protocol.RunAutomationRequest{RequestKey: "retry-once"}); err != nil {
		t.Fatal(err)
	}
	if err := store.dispatchPendingOccurrences(context.Background(), 10); err != nil {
		t.Fatal(err)
	}
	before, err := store.Automation(context.Background(), detail.Automation.ID)
	if err != nil || len(before.Occurrences) != 1 || before.Occurrences[0].Task == nil {
		t.Fatalf("dispatched run = %#v, error %v", before.Occurrences, err)
	}
	taskID := before.Occurrences[0].Task.ID
	claim, err := store.Claim(context.Background(), "schedule-worker", protocol.ClaimRequest{RequestID: "retry-first", LeaseToken: fmt.Sprintf("%064x", 1)})
	if err != nil || claim == nil {
		t.Fatalf("first claim = %#v, error %v", claim, err)
	}
	if _, err := store.CompleteAttempt(context.Background(), claim.Attempt.ID, protocol.CompleteAttemptRequest{LeaseToken: fmt.Sprintf("%064x", 1), State: "failed", Error: "temporary"}); err != nil {
		t.Fatal(err)
	}
	var state string
	var retries, attempts int
	if err := store.db.QueryRow(`SELECT state, retry_count FROM executions WHERE id = ?`, claim.Execution.ID).Scan(&state, &retries); err != nil {
		t.Fatal(err)
	}
	if err := store.db.QueryRow(`SELECT COUNT(*) FROM attempts WHERE execution_id = ?`, claim.Execution.ID).Scan(&attempts); err != nil {
		t.Fatal(err)
	}
	if state != "queued" || retries != 1 || attempts != 1 {
		t.Fatalf("first failure = state %q retries %d attempts %d", state, retries, attempts)
	}
	queued, err := store.Automation(context.Background(), detail.Automation.ID)
	if err != nil || queued.Occurrences[0].Task == nil || queued.Occurrences[0].Task.RetryStatus != "queued" {
		t.Fatalf("queued retry projection = %#v, error %v", queued.Occurrences, err)
	}
	second, err := store.Claim(context.Background(), "schedule-worker", protocol.ClaimRequest{RequestID: "retry-second", LeaseToken: fmt.Sprintf("%064x", 2)})
	if err != nil || second == nil || second.Execution.ID != claim.Execution.ID || second.Task.ID != taskID || second.Attempt.AttemptNumber != 2 {
		t.Fatalf("second claim = %#v, error %v", second, err)
	}
	if _, err := store.CompleteAttempt(context.Background(), second.Attempt.ID, protocol.CompleteAttemptRequest{LeaseToken: fmt.Sprintf("%064x", 2), State: "failed", Error: "permanent"}); err != nil {
		t.Fatal(err)
	}
	if err := store.db.QueryRow(`SELECT state, retry_count FROM executions WHERE id = ?`, claim.Execution.ID).Scan(&state, &retries); err != nil {
		t.Fatal(err)
	}
	if state != "failed" || retries != 1 {
		t.Fatalf("second failure = state %q retries %d", state, retries)
	}
	final, err := store.Automation(context.Background(), detail.Automation.ID)
	if err != nil || final.Occurrences[0].Task == nil || final.Occurrences[0].Task.RetryStatus != "final_failed" {
		t.Fatalf("final retry projection = %#v, error %v", final.Occurrences, err)
	}
}

func TestAutomationOccurrenceProjectsAttemptOutputAcrossRetryAndAPI(t *testing.T) {
	now := time.Date(2026, 8, 1, 7, 0, 0, 0, time.UTC)
	store, detail := createScheduleAutomationFixture(t, &now, true)
	enableAutomation(t, store, detail.Automation.ID)
	if _, err := store.RunAutomationNow(context.Background(), detail.Automation.ID, protocol.RunAutomationRequest{RequestKey: "attempt-output"}); err != nil {
		t.Fatal(err)
	}
	if err := store.dispatchPendingOccurrences(context.Background(), 10); err != nil {
		t.Fatal(err)
	}
	before, err := store.AutomationOccurrences(context.Background(), detail.Automation.ID, 10)
	if err != nil || len(before) != 1 || before[0].AttemptState != "" || before[0].Result != "" || before[0].Error != "" {
		t.Fatalf("occurrence without attempt = %#v, error %v", before, err)
	}

	first, err := store.Claim(context.Background(), "schedule-worker", protocol.ClaimRequest{RequestID: "attempt-output-first", LeaseToken: fmt.Sprintf("%064x", 81)})
	if err != nil || first == nil {
		t.Fatalf("first claim = %#v, error %v", first, err)
	}
	if _, err := store.CompleteAttempt(context.Background(), first.Attempt.ID, protocol.CompleteAttemptRequest{LeaseToken: fmt.Sprintf("%064x", 81), State: "failed", Error: "temporary output failure"}); err != nil {
		t.Fatal(err)
	}
	queued, err := store.AutomationOccurrences(context.Background(), detail.Automation.ID, 10)
	if err != nil || queued[0].Task == nil || queued[0].Task.RetryStatus != "queued" || queued[0].AttemptState != "failed" || queued[0].Error != "temporary output failure" {
		t.Fatalf("retry attempt projection = %#v, error %v", queued, err)
	}

	second, err := store.Claim(context.Background(), "schedule-worker", protocol.ClaimRequest{RequestID: "attempt-output-second", LeaseToken: fmt.Sprintf("%064x", 82)})
	if err != nil || second == nil {
		t.Fatalf("second claim = %#v, error %v", second, err)
	}
	if _, err := store.StartAttempt(context.Background(), second.Attempt.ID, protocol.StartAttemptRequest{LeaseToken: fmt.Sprintf("%064x", 82)}); err != nil {
		t.Fatal(err)
	}
	if _, err := store.CompleteAttempt(context.Background(), second.Attempt.ID, protocol.CompleteAttemptRequest{LeaseToken: fmt.Sprintf("%064x", 82), State: "succeeded", Result: "НАХОДКА: сертификат истекает"}); err != nil {
		t.Fatal(err)
	}
	final, err := store.AutomationOccurrences(context.Background(), detail.Automation.ID, 10)
	if err != nil || final[0].Task == nil || final[0].Task.RetryStatus != "succeeded" || final[0].AttemptState != "succeeded" || final[0].Result != "НАХОДКА: сертификат истекает" || final[0].Error != "" {
		t.Fatalf("final attempt projection = %#v, error %v", final, err)
	}

	server := httptest.NewServer(NewHandlerWithAutomation(store, slog.Default(), newAutomationService(store, slog.Default(), fakeGitHubIssueLister{})))
	defer server.Close()
	response, err := server.Client().Get(server.URL + "/api/v1/automations/" + detail.Automation.ID + "/occurrences?limit=10")
	if err != nil {
		t.Fatal(err)
	}
	requireStatus(t, response, http.StatusOK)
	page := decodeResponse[struct {
		Occurrences []protocol.AutomationOccurrence `json:"occurrences"`
	}](t, response)
	if len(page.Occurrences) != 1 || page.Occurrences[0].Result != "НАХОДКА: сертификат истекает" || page.Occurrences[0].AttemptState != "succeeded" {
		t.Fatalf("HTTP attempt projection = %#v", page)
	}
}

func TestScheduleAutomationRetryStaysWithOriginalWorker(t *testing.T) {
	now := time.Date(2026, 8, 1, 7, 0, 0, 0, time.UTC)
	store, detail := createScheduleAutomationFixture(t, &now, true)
	first := claimScheduleOccurrence(t, store, detail, &now, "run_now", "affinity-first", 401)
	if _, err := store.RegisterWorker(context.Background(), "compatible-worker", protocol.WorkerRegistration{
		Name: "compatible-worker", WorkerVersion: "test", RuntimeVersion: "test",
		Capacity: 1, Health: "healthy", AcceptsManagedRepositories: true,
		ManagedRepositoryIDs: []string{detail.Automation.RepositoryID},
	}); err != nil {
		t.Fatal(err)
	}
	if _, err := store.CompleteAttempt(context.Background(), first.Attempt.ID, protocol.CompleteAttemptRequest{LeaseToken: fmt.Sprintf("%064x", 401), State: "failed", Error: "temporary"}); err != nil {
		t.Fatal(err)
	}
	other, err := store.Claim(context.Background(), "compatible-worker", protocol.ClaimRequest{RequestID: "affinity-other", LeaseToken: fmt.Sprintf("%064x", 402)})
	if err != nil || other != nil {
		t.Fatalf("compatible worker claimed automatic retry = %#v, error %v", other, err)
	}
	retry, err := store.Claim(context.Background(), "schedule-worker", protocol.ClaimRequest{RequestID: "affinity-original", LeaseToken: fmt.Sprintf("%064x", 403)})
	if err != nil || retry == nil || retry.Execution.ID != first.Execution.ID || retry.Execution.AssignedWorkerID != "schedule-worker" {
		t.Fatalf("original worker retry claim = %#v, error %v", retry, err)
	}
}

func TestAutomationRetryStatusRequiresAutomaticRetryDiagnostic(t *testing.T) {
	t.Run("manual GitHub retry has no automatic retry status", func(t *testing.T) {
		store, detail := createAutomationFixture(t, true)
		enableAutomation(t, store, detail.Automation.ID)
		evaluation := reserveAutomation(t, store)
		if err := store.completeAutomationSuccess(context.Background(), evaluation, []protocol.GitHubIssueMatch{testIssue}); err != nil {
			t.Fatal(err)
		}
		if err := store.dispatchPendingOccurrences(context.Background(), 10); err != nil {
			t.Fatal(err)
		}
		claim, err := store.Claim(context.Background(), "automation-worker", protocol.ClaimRequest{RequestID: "github-manual-retry", LeaseToken: fmt.Sprintf("%064x", 410)})
		if err != nil || claim == nil {
			t.Fatalf("GitHub claim = %#v, error %v", claim, err)
		}
		if _, err := store.CompleteAttempt(context.Background(), claim.Attempt.ID, protocol.CompleteAttemptRequest{LeaseToken: fmt.Sprintf("%064x", 410), State: "failed"}); err != nil {
			t.Fatal(err)
		}
		if _, err := store.RetryExecution(context.Background(), claim.Execution.ID); err != nil {
			t.Fatal(err)
		}
		current, err := store.Automation(context.Background(), detail.Automation.ID)
		if err != nil || current.Occurrences[0].Task == nil || current.Occurrences[0].Task.RetryCount != 1 || current.Occurrences[0].Task.RetryStatus != "" {
			t.Fatalf("manual GitHub retry projection = %#v, error %v", current.Occurrences, err)
		}
	})

	t.Run("cancelled automatic retry remains cancelled", func(t *testing.T) {
		now := time.Date(2026, 8, 1, 7, 0, 0, 0, time.UTC)
		store, detail := createScheduleAutomationFixture(t, &now, true)
		first := claimScheduleOccurrence(t, store, detail, &now, "run_now", "cancel-retry", 420)
		if _, err := store.CompleteAttempt(context.Background(), first.Attempt.ID, protocol.CompleteAttemptRequest{LeaseToken: fmt.Sprintf("%064x", 420), State: "failed"}); err != nil {
			t.Fatal(err)
		}
		if _, err := store.CancelTask(context.Background(), first.Task.ID); err != nil {
			t.Fatal(err)
		}
		current, err := store.Automation(context.Background(), detail.Automation.ID)
		if err != nil || current.Occurrences[0].Task == nil || current.Occurrences[0].Task.RetryStatus != "cancelled" {
			t.Fatalf("cancelled automatic retry projection = %#v, error %v", current.Occurrences, err)
		}
	})
}

func TestScheduleAutomationRetryLifecycleIsExactlyOnce(t *testing.T) {
	for _, test := range []struct {
		name, kind, failure string
	}{
		{name: "scheduled completion", kind: "scheduled", failure: "completion"},
		{name: "run now expired lease", kind: "run_now", failure: "sweep"},
	} {
		t.Run(test.name, func(t *testing.T) {
			now := time.Date(2026, 8, 1, 7, 0, 0, 0, time.UTC)
			store, detail := createScheduleAutomationFixture(t, &now, true)
			first := claimScheduleOccurrence(t, store, detail, &now, test.kind, "lifecycle-first", 101)
			identity := captureScheduleRetryIdentity(t, store, detail.Automation.ID)

			if test.failure == "completion" {
				request := protocol.CompleteAttemptRequest{LeaseToken: fmt.Sprintf("%064x", 101), State: "failed", Error: "temporary"}
				if _, err := store.CompleteAttempt(context.Background(), first.Attempt.ID, request); err != nil {
					t.Fatal(err)
				}
				if _, err := store.CompleteAttempt(context.Background(), first.Attempt.ID, request); err != nil {
					t.Fatalf("replayed terminal completion: %v", err)
				}
			} else {
				now = now.Add(protocol.LeaseDuration + time.Millisecond)
				if _, err := store.db.Exec(`UPDATE workers SET last_heartbeat = ? WHERE id = ?`, now.UnixMilli(), first.Execution.AssignedWorkerID); err != nil {
					t.Fatal(err)
				}
				expired, err := store.SweepExpired(context.Background())
				if err != nil || len(expired) != 1 || expired[0].AttemptID != first.Attempt.ID {
					t.Fatalf("first sweep = %#v, error %v", expired, err)
				}
				expired, err = store.SweepExpired(context.Background())
				if err != nil || len(expired) != 0 {
					t.Fatalf("repeated sweep = %#v, error %v", expired, err)
				}
				_, err = store.CompleteAttempt(context.Background(), first.Attempt.ID, protocol.CompleteAttemptRequest{LeaseToken: fmt.Sprintf("%064x", 101), State: "failed"})
				assertErrorCode(t, err, "lease_not_owner")
			}

			if got := captureScheduleRetryIdentity(t, store, detail.Automation.ID); got != identity {
				t.Fatalf("identity changed after first failure:\n got %#v\nwant %#v", got, identity)
			}
			state, diagnostic, retries, attempts := captureRetryState(t, store, identity.executionID)
			if state != "queued" || diagnostic != "retry_queued" || retries != 1 || attempts != 1 {
				t.Fatalf("queued retry = state %q diagnostic %q retries %d attempts %d", state, diagnostic, retries, attempts)
			}

			if test.failure == "sweep" {
				var path string
				if err := store.db.QueryRow(`SELECT file FROM pragma_database_list WHERE name = 'main'`).Scan(&path); err != nil {
					t.Fatal(err)
				}
				restarted, err := Open(context.Background(), path)
				if err != nil {
					t.Fatal(err)
				}
				store = restarted
				store.now = func() time.Time { return now }
				t.Cleanup(func() { _ = restarted.Close() })
				if got := captureScheduleRetryIdentity(t, store, detail.Automation.ID); got != identity {
					t.Fatalf("identity changed across restart:\n got %#v\nwant %#v", got, identity)
				}
			}

			second, err := store.Claim(context.Background(), "schedule-worker", protocol.ClaimRequest{RequestID: "lifecycle-second", LeaseToken: fmt.Sprintf("%064x", 102)})
			if err != nil || second == nil || second.Execution.ID != identity.executionID || second.Task.ID != identity.taskID || second.Attempt.AttemptNumber != 2 {
				t.Fatalf("second claim = %#v, error %v", second, err)
			}
			finalRequest := protocol.CompleteAttemptRequest{LeaseToken: fmt.Sprintf("%064x", 102), State: "failed", Error: "permanent"}
			if _, err := store.CompleteAttempt(context.Background(), second.Attempt.ID, finalRequest); err != nil {
				t.Fatal(err)
			}
			if _, err := store.CompleteAttempt(context.Background(), second.Attempt.ID, finalRequest); err != nil {
				t.Fatalf("replayed final completion: %v", err)
			}
			if expired, err := store.SweepExpired(context.Background()); err != nil || len(expired) != 0 {
				t.Fatalf("cleanup after final failure = %#v, error %v", expired, err)
			}
			if got := captureScheduleRetryIdentity(t, store, detail.Automation.ID); got != identity {
				t.Fatalf("identity changed after final failure:\n got %#v\nwant %#v", got, identity)
			}
			state, diagnostic, retries, attempts = captureRetryState(t, store, identity.executionID)
			if state != "failed" || diagnostic != "retry_final_failed" || retries != 1 || attempts != 2 {
				t.Fatalf("final retry = state %q diagnostic %q retries %d attempts %d", state, diagnostic, retries, attempts)
			}
		})
	}
}

func TestScheduleAutomationRetryEligibilityGuardsAreExactlyOnce(t *testing.T) {
	for _, test := range []struct {
		name   string
		mutate func(*testing.T, *Store, protocol.AutomationDetail, *protocol.Claim, time.Time)
		status string
	}{
		{
			name: "cancellation",
			mutate: func(t *testing.T, store *Store, _ protocol.AutomationDetail, claim *protocol.Claim, _ time.Time) {
				if _, err := store.CancelTask(context.Background(), claim.Task.ID); err != nil {
					t.Fatal(err)
				}
			},
			status: "retry_skipped_worker_unavailable",
		},
		{
			name: "disabled Automation",
			mutate: func(t *testing.T, store *Store, detail protocol.AutomationDetail, _ *protocol.Claim, _ time.Time) {
				if _, err := store.SetAutomationEnabled(context.Background(), detail.Automation.ID, false, false); err != nil {
					t.Fatal(err)
				}
			},
			status: "retry_skipped_disabled",
		},
		{
			name: "offline worker",
			mutate: func(t *testing.T, store *Store, _ protocol.AutomationDetail, claim *protocol.Claim, now time.Time) {
				if _, err := store.db.Exec(`UPDATE workers SET last_heartbeat = ? WHERE id = ?`, now.Add(-protocol.WorkerOnlineWindow-time.Millisecond).UnixMilli(), claim.Execution.AssignedWorkerID); err != nil {
					t.Fatal(err)
				}
			},
			status: "retry_skipped_worker_unavailable",
		},
		{
			name: "unhealthy worker",
			mutate: func(t *testing.T, store *Store, _ protocol.AutomationDetail, claim *protocol.Claim, _ time.Time) {
				if _, err := store.db.Exec(`UPDATE workers SET health = 'unhealthy' WHERE id = ?`, claim.Execution.AssignedWorkerID); err != nil {
					t.Fatal(err)
				}
			},
			status: "retry_skipped_worker_unavailable",
		},
	} {
		t.Run(test.name, func(t *testing.T) {
			now := time.Date(2026, 8, 1, 7, 0, 0, 0, time.UTC)
			store, detail := createScheduleAutomationFixture(t, &now, true)
			claim := claimScheduleOccurrence(t, store, detail, &now, "run_now", "guard-first", 201)
			identity := captureScheduleRetryIdentity(t, store, detail.Automation.ID)
			test.mutate(t, store, detail, claim, now)
			request := protocol.CompleteAttemptRequest{LeaseToken: fmt.Sprintf("%064x", 201), State: "failed", Error: "guarded"}
			if _, err := store.CompleteAttempt(context.Background(), claim.Attempt.ID, request); err != nil {
				t.Fatal(err)
			}
			if _, err := store.CompleteAttempt(context.Background(), claim.Attempt.ID, request); err != nil {
				t.Fatal(err)
			}
			if got := captureScheduleRetryIdentity(t, store, detail.Automation.ID); got != identity {
				t.Fatalf("guard changed identity:\n got %#v\nwant %#v", got, identity)
			}
			state, diagnostic, retries, attempts := captureRetryState(t, store, identity.executionID)
			if state != "failed" || diagnostic != test.status || retries != 0 || attempts != 1 {
				t.Fatalf("guard result = state %q diagnostic %q retries %d attempts %d", state, diagnostic, retries, attempts)
			}
		})
	}
}

func TestScheduleAutomationRetryExcludesGitHubAndOrdinaryTasks(t *testing.T) {
	t.Run("GitHub Automation", func(t *testing.T) {
		store, detail := createAutomationFixture(t, true)
		enableAutomation(t, store, detail.Automation.ID)
		evaluation := reserveAutomation(t, store)
		if err := store.completeAutomationSuccess(context.Background(), evaluation, []protocol.GitHubIssueMatch{testIssue}); err != nil {
			t.Fatal(err)
		}
		if err := store.dispatchPendingOccurrences(context.Background(), 10); err != nil {
			t.Fatal(err)
		}
		claim, err := store.Claim(context.Background(), "automation-worker", protocol.ClaimRequest{RequestID: "github-failure", LeaseToken: fmt.Sprintf("%064x", 301)})
		if err != nil || claim == nil {
			t.Fatalf("GitHub claim = %#v, error %v", claim, err)
		}
		identity := captureScheduleRetryIdentity(t, store, detail.Automation.ID)
		request := protocol.CompleteAttemptRequest{LeaseToken: fmt.Sprintf("%064x", 301), State: "failed", Error: "GitHub failure"}
		if _, err := store.CompleteAttempt(context.Background(), claim.Attempt.ID, request); err != nil {
			t.Fatal(err)
		}
		if _, err := store.CompleteAttempt(context.Background(), claim.Attempt.ID, request); err != nil {
			t.Fatal(err)
		}
		if got := captureScheduleRetryIdentity(t, store, detail.Automation.ID); got != identity {
			t.Fatalf("GitHub failure changed identity:\n got %#v\nwant %#v", got, identity)
		}
		state, diagnostic, retries, attempts := captureRetryState(t, store, identity.executionID)
		if state != "failed" || diagnostic != "" || retries != 0 || attempts != 1 {
			t.Fatalf("GitHub failure = state %q diagnostic %q retries %d attempts %d", state, diagnostic, retries, attempts)
		}
	})

	t.Run("ordinary task", func(t *testing.T) {
		store := newTestStore(t)
		worker := registerTestWorker(t, store, "ordinary-worker", 1, protocol.RepositoryRegistration{
			Key: "factory", RemoteIdentity: "github.com/owainlewis/factory",
		})
		task := createTestTask(t, store, "ordinary-failure", worker.ID, worker.Repositories[0].ID)
		claim, err := store.Claim(context.Background(), worker.ID, protocol.ClaimRequest{RequestID: "ordinary-failure", LeaseToken: fmt.Sprintf("%064x", 302)})
		if err != nil || claim == nil {
			t.Fatalf("ordinary claim = %#v, error %v", claim, err)
		}
		var beforeTasks, beforeExecutions int
		if err := store.db.QueryRow(`SELECT COUNT(*) FROM tasks`).Scan(&beforeTasks); err != nil {
			t.Fatal(err)
		}
		if err := store.db.QueryRow(`SELECT COUNT(*) FROM executions`).Scan(&beforeExecutions); err != nil {
			t.Fatal(err)
		}
		request := protocol.CompleteAttemptRequest{LeaseToken: fmt.Sprintf("%064x", 302), State: "failed", Error: "ordinary failure"}
		if _, err := store.CompleteAttempt(context.Background(), claim.Attempt.ID, request); err != nil {
			t.Fatal(err)
		}
		if _, err := store.CompleteAttempt(context.Background(), claim.Attempt.ID, request); err != nil {
			t.Fatal(err)
		}
		var state, taskID, requestKey, executionID string
		var retries, attempts, afterTasks, afterExecutions int
		if err := store.db.QueryRow(`
			SELECT task.id, task.request_key, execution.id, execution.state,
			       execution.retry_count,
			       (SELECT COUNT(*) FROM attempts WHERE execution_id = execution.id)
			FROM tasks task JOIN executions execution ON execution.task_id = task.id
			WHERE task.id = ?
		`, task.Task.ID).Scan(&taskID, &requestKey, &executionID, &state, &retries, &attempts); err != nil {
			t.Fatal(err)
		}
		if err := store.db.QueryRow(`SELECT COUNT(*) FROM tasks`).Scan(&afterTasks); err != nil {
			t.Fatal(err)
		}
		if err := store.db.QueryRow(`SELECT COUNT(*) FROM executions`).Scan(&afterExecutions); err != nil {
			t.Fatal(err)
		}
		if taskID != task.Task.ID || requestKey != "ordinary-failure" || executionID != claim.Execution.ID ||
			state != "failed" || retries != 0 || attempts != 1 || afterTasks != beforeTasks || afterExecutions != beforeExecutions {
			t.Fatalf("ordinary failure changed retry identity: task %q request %q execution %q state %q retries %d attempts %d counts %d/%d -> %d/%d",
				taskID, requestKey, executionID, state, retries, attempts, beforeTasks, beforeExecutions, afterTasks, afterExecutions)
		}
	})
}

func TestInvalidStoredScheduleDegradesOnlyItsAutomation(t *testing.T) {
	now := time.Date(2026, 8, 1, 7, 0, 0, 0, time.UTC)
	store, detail := createScheduleAutomationFixture(t, &now, true)
	enabled := enableAutomation(t, store, detail.Automation.ID)
	now = *enabled.Automation.NextDueAt
	if _, err := store.db.Exec(`UPDATE automation_schedule_triggers SET cron = 'invalid' WHERE automation_id = ?`, detail.Automation.ID); err != nil {
		t.Fatal(err)
	}
	if err := store.processDueSchedules(context.Background(), 100); err != nil {
		t.Fatal(err)
	}
	degraded, err := store.Automation(context.Background(), detail.Automation.ID)
	if err != nil || degraded.Automation.Health.Code != "stored_schedule_invalid" || degraded.Automation.NextDueAt != nil {
		t.Fatalf("degraded schedule = %#v, error %v", degraded.Automation, err)
	}

	provider, created, err := store.CreateAutomation(context.Background(), protocol.CreateAutomationRequest{
		RequestKey: "provider-after-schedule-degradation", Title: "Provider remains available",
		WorkflowID: detail.Automation.WorkflowID, RepositoryID: detail.Automation.RepositoryID,
		TimeoutSeconds: 60,
		Trigger: protocol.AutomationTrigger{
			Type: protocol.AutomationTriggerGitHubIssue, State: "open",
			RequiredLabels: []string{"factory:ready"}, PollIntervalSeconds: 30,
		},
	})
	if err != nil || !created {
		t.Fatalf("provider Automation after schedule degradation = created %v, error %v", created, err)
	}
	service := newAutomationService(store, slog.Default(), fakeGitHubIssueLister{matches: []protocol.GitHubIssueMatch{testIssue}})
	preview, err := service.Test(context.Background(), provider.Automation.ID)
	if err != nil || len(preview.Matches) != 1 {
		t.Fatalf("provider preview after schedule degradation = %#v, error %v", preview, err)
	}
	if _, err := store.RegisterWorker(context.Background(), "api-isolation-worker", protocol.WorkerRegistration{
		Name: "api-isolation-worker", WorkerVersion: "test", RuntimeVersion: "test",
		Capacity: 1, Health: "healthy", AcceptsManagedRepositories: true,
		SourceAccess: []protocol.SourceAccess{{Provider: "github", Hostname: "github.com"}},
	}); err != nil {
		t.Fatal(err)
	}
	task, created, err := store.CreateTask(context.Background(), protocol.CreateTaskRequest{
		RequestKey: "ordinary-task-after-schedule-degradation", Title: "Ordinary task remains available",
		Description: "Prove the ordinary task API remains isolated from scheduler health.",
		Route: &protocol.TaskRoute{
			RepositoryRemoteIdentity: detail.Automation.RepositoryIdentity,
			SourceAccess:             protocol.SourceAccess{Provider: "github", Hostname: "github.com"},
		},
		TimeoutSeconds: 60,
	})
	if err != nil || !created || task.Task.State != "queued" {
		t.Fatalf("ordinary task after schedule degradation = created %v, task %#v, error %v", created, task.Task, err)
	}
}

func TestScheduleDisableAndShutdownAdmitNoFutureOccurrences(t *testing.T) {
	now := time.Date(2026, 8, 1, 7, 0, 0, 0, time.UTC)
	store, detail := createScheduleAutomationFixture(t, &now, false)
	enableAutomation(t, store, detail.Automation.ID)
	if _, err := store.SetAutomationEnabled(context.Background(), detail.Automation.ID, false, false); err != nil {
		t.Fatal(err)
	}
	now = now.Add(48 * time.Hour)
	if err := store.processDueSchedules(context.Background(), 100); err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	service := newAutomationService(store, nil, fakeGitHubIssueLister{})
	done := make(chan struct{})
	go func() { defer close(done); service.Run(ctx) }()
	cancel()
	<-done
	service.Wake()
	current, err := store.Automation(context.Background(), detail.Automation.ID)
	if err != nil || len(current.Occurrences) != 0 {
		t.Fatalf("disable/shutdown admitted occurrences = %#v, error %v", current.Occurrences, err)
	}
}

func TestScheduleShutdownDrainsOccurrenceCommittedBeforeCancellation(t *testing.T) {
	now := time.Date(2026, 8, 1, 7, 0, 0, 0, time.UTC)
	store, detail := createScheduleAutomationFixture(t, &now, true)
	enabled := enableAutomation(t, store, detail.Automation.ID)
	now = *enabled.Automation.NextDueAt
	if _, err := store.RegisterWorker(context.Background(), "schedule-worker", protocol.WorkerRegistration{
		Name: "schedule-worker", WorkerVersion: "test", RuntimeVersion: "test",
		Capacity: 1, Health: "healthy", AcceptsManagedRepositories: true,
		ManagedRepositoryIDs: []string{detail.Automation.RepositoryID},
	}); err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	service := newAutomationService(store, nil, fakeGitHubIssueLister{})
	service.afterScheduleAdmission = cancel
	done := make(chan struct{})
	go func() {
		defer close(done)
		service.Run(ctx)
	}()
	<-done

	current, err := store.Automation(context.Background(), detail.Automation.ID)
	if err != nil {
		t.Fatal(err)
	}
	if len(current.Occurrences) != 1 || current.Occurrences[0].Kind != "scheduled" || current.Occurrences[0].Task == nil {
		t.Fatalf("shutdown did not drain committed occurrence = %#v", current.Occurrences)
	}
	task, err := store.Task(context.Background(), current.Occurrences[0].Task.ID)
	if err != nil || task.Task.State != "queued" {
		t.Fatalf("shutdown-drained task = %#v, error %v", task.Task, err)
	}
}

func TestScheduleShutdownAdmissionGateRejectsRunNowAndNewDueInstants(t *testing.T) {
	now := time.Date(2026, 8, 1, 7, 0, 0, 0, time.UTC)
	store, detail := createScheduleAutomationFixture(t, &now, false)
	enabled := enableAutomation(t, store, detail.Automation.ID)
	service := newAutomationService(store, slog.Default(), fakeGitHubIssueLister{})
	server := httptest.NewServer(NewHandlerWithAutomation(store, slog.Default(), service))
	defer server.Close()
	service.StopAdmission()
	now = *enabled.Automation.NextDueAt
	if err := service.admitDueSchedules(context.Background(), 100); err != nil {
		t.Fatal(err)
	}

	const callers = 8
	statuses := make(chan int, callers)
	var wait sync.WaitGroup
	for index := range callers {
		wait.Add(1)
		go func() {
			defer wait.Done()
			body, err := json.Marshal(protocol.RunAutomationRequest{RequestKey: fmt.Sprintf("shutdown-run-%d", index)})
			if err != nil {
				t.Error(err)
				return
			}
			response, err := server.Client().Post(
				server.URL+"/api/v1/automations/"+detail.Automation.ID+"/run",
				"application/json", bytes.NewReader(body),
			)
			if err != nil {
				t.Error(err)
				return
			}
			defer response.Body.Close()
			statuses <- response.StatusCode
		}()
	}
	wait.Wait()
	close(statuses)
	for status := range statuses {
		if status != http.StatusConflict {
			t.Fatalf("Run now during shutdown status = %d", status)
		}
	}
	current, err := store.Automation(context.Background(), detail.Automation.ID)
	if err != nil || len(current.Occurrences) != 0 {
		t.Fatalf("shutdown gate admitted occurrences = %#v, error %v", current.Occurrences, err)
	}
}

func TestHTTPSchedulePreviewEnableAndRunNowAreStrictAndIdempotent(t *testing.T) {
	now := time.Date(2026, 8, 1, 7, 0, 0, 0, time.UTC)
	store, detail := createScheduleAutomationFixture(t, &now, false)
	service := newAutomationService(store, slog.Default(), fakeGitHubIssueLister{})
	server := httptest.NewServer(NewHandlerWithAutomation(store, slog.Default(), service))
	defer server.Close()
	request := func(method, path string, body any) *http.Response {
		encoded, err := json.Marshal(body)
		if err != nil {
			t.Fatal(err)
		}
		req, err := http.NewRequest(method, server.URL+path, bytes.NewReader(encoded))
		if err != nil {
			t.Fatal(err)
		}
		req.Header.Set("Content-Type", "application/json")
		response, err := server.Client().Do(req)
		if err != nil {
			t.Fatal(err)
		}
		return response
	}
	response := request(http.MethodPost, "/api/v1/automations/"+detail.Automation.ID+"/test", struct{}{})
	requireStatus(t, response, http.StatusOK)
	preview := decodeResponse[protocol.TestAutomationResult](t, response)
	if preview.NextDueAt == nil || len(preview.Matches) != 0 {
		t.Fatalf("HTTP schedule preview = %#v", preview)
	}
	response = request(http.MethodPut, "/api/v1/automations/"+detail.Automation.ID+"/enabled", map[string]any{"enabled": true})
	requireStatus(t, response, http.StatusOK)
	response.Body.Close()
	response = request(http.MethodPost, "/api/v1/automations/"+detail.Automation.ID+"/check", struct{}{})
	requireStatus(t, response, http.StatusConflict)
	response.Body.Close()
	for range 2 {
		response = request(http.MethodPost, "/api/v1/automations/"+detail.Automation.ID+"/run", protocol.RunAutomationRequest{RequestKey: "http-run"})
		requireStatus(t, response, http.StatusAccepted)
		response.Body.Close()
	}
	current, err := store.Automation(context.Background(), detail.Automation.ID)
	if err != nil || len(current.Occurrences) != 1 || current.Occurrences[0].RunRequestKey != "http-run" {
		t.Fatalf("HTTP Run now replay = %#v, error %v", current.Occurrences, err)
	}

	workflow := createTestWorkflow(t, store, "invalid-schedule-workflow", "Invalid", "Do not run.")
	repository := createManagedTestRepository(t, store, "github.com/owainlewis/invalid-schedule")
	response = request(http.MethodPost, "/api/v1/automations", map[string]any{
		"request_key": "invalid-schedule-shape", "title": "Invalid schedule shape",
		"workflow_id": workflow.Workflow.ID, "repository_id": repository.ID,
		"context": "", "timeout_seconds": 60,
		"trigger": map[string]any{"type": "schedule", "cron": "0 9 * * *", "timezone": "UTC", "state": "open"},
	})
	requireStatus(t, response, http.StatusBadRequest)
	response.Body.Close()
}
