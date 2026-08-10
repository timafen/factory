package controlplane

import (
	"context"
	"encoding/json"
	"math"
	"net/http"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/owainlewis/factory/internal/protocol"
)

func TestEfficiencyUsesMergedProductWorkAndHonestDenominators(t *testing.T) {
	store := newTestStore(t)
	now := time.Date(2026, time.August, 10, 12, 0, 0, 0, time.UTC)
	store.now = func() time.Time { return now }
	home := t.TempDir()
	t.Setenv("FACTORY_DATA_HOME", home)
	if err := os.MkdirAll(filepath.Join(home, "pilot"), 0o755); err != nil {
		t.Fatal(err)
	}

	repository := createManagedTestRepository(t, store, "github.com/example/product")
	if _, err := store.RegisterWorker(context.Background(), "efficiency-worker", protocol.WorkerRegistration{
		Name: "efficiency-worker", WorkerVersion: "test", RuntimeVersion: "test",
		Capacity: 1, Health: "healthy", AcceptsManagedRepositories: true,
		ManagedRepositoryIDs: []string{repository.ID},
	}); err != nil {
		t.Fatal(err)
	}

	seedEfficiencyTask(t, store, repository.ID, "triage", "[auto] [1/5 Triage] Честный обзор", "succeeded", now.Add(-5*time.Hour), now.Add(-4*time.Hour-50*time.Minute), now.Add(-4*time.Hour-40*time.Minute))
	seedEfficiencyTask(t, store, repository.ID, "implement", "[auto] [3/5 Implement + Test] Честный обзор", "succeeded", now.Add(-4*time.Hour-30*time.Minute), now.Add(-4*time.Hour-20*time.Minute), now.Add(-3*time.Hour-40*time.Minute))
	seedEfficiencyTask(t, store, repository.ID, "review-cancelled", "[auto] [4/5 Review] Честный обзор", "cancelled", now.Add(-3*time.Hour-30*time.Minute), now.Add(-3*time.Hour-20*time.Minute), now.Add(-3*time.Hour))
	if _, err := store.db.Exec(`UPDATE attempts SET started_at = NULL WHERE id = 'attempt-review-cancelled'`); err != nil {
		t.Fatal(err)
	}
	seedEfficiencyTask(t, store, repository.ID, "review-pass", "[auto] [4/5 Review] Честный обзор", "succeeded", now.Add(-2*time.Hour-50*time.Minute), now.Add(-2*time.Hour-40*time.Minute), now.Add(-2*time.Hour-20*time.Minute))
	seedEfficiencyTask(t, store, repository.ID, "verify-fail", "[auto] [5/5 Verify] Честный обзор", "failed", now.Add(-2*time.Hour-10*time.Minute), now.Add(-2*time.Hour), now.Add(-time.Hour-50*time.Minute))
	seedEfficiencyTask(t, store, repository.ID, "verify-pass", "[auto] [5/5 Verify] Честный обзор", "succeeded", now.Add(-time.Hour-40*time.Minute), now.Add(-time.Hour-30*time.Minute), now.Add(-time.Hour-10*time.Minute))
	seedEfficiencyTask(t, store, repository.ID, "dead-end", "[auto] [3/5 Implement + Test] Окончательный тупик", "failed", now.Add(-90*time.Minute), now.Add(-80*time.Minute), now.Add(-70*time.Minute))
	patrolID := seedEfficiencyTask(t, store, repository.ID, "patrol", "[auto] [1/5 Triage] Патруль", "succeeded", now.Add(-80*time.Minute), now.Add(-75*time.Minute), now.Add(-65*time.Minute))
	scheduledID := seedEfficiencyTask(t, store, repository.ID, "scheduled", "Плановое обслуживание", "succeeded", now.Add(-75*time.Minute), now.Add(-70*time.Minute), now.Add(-62*time.Minute))
	seedEfficiencyTask(t, store, repository.ID, "helper", "[helper] обновить индекс", "succeeded", now.Add(-70*time.Minute), now.Add(-65*time.Minute), now.Add(-60*time.Minute))
	linkEfficiencySchedule(t, store, repository.ID, patrolID, "patrol", PipelinePatrolInstruction, now)
	linkEfficiencySchedule(t, store, repository.ID, scheduledID, "maintenance", "Run scheduled maintenance.", now)

	writeJSONLines(t, filepath.Join(home, "pilot", "merges.jsonl"), []any{
		map[string]any{"task_id": "task-verify-pass", "base": "Честный обзор", "at": now.Add(-time.Hour).Format(time.RFC3339)},
		// A duplicate receipt must not inflate throughput.
		map[string]any{"task_id": "task-verify-pass", "base": "Честный обзор", "at": now.Add(-59 * time.Minute).Format(time.RFC3339)},
	})
	writeJSONLines(t, filepath.Join(home, "pilot", "release-events.jsonl"), []any{
		map[string]any{"id": "factory-7", "at": now.Add(-30 * time.Minute).Format(time.RFC3339), "kind": "failed_release", "rollback": true},
		map[string]any{"id": "factory-7", "at": now.Add(-29 * time.Minute).Format(time.RFC3339), "kind": "failed_release", "rollback": true},
	})

	summary, err := store.Efficiency(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if summary.ReleaseObservationStartedAt == nil {
		t.Fatal("release observation start is missing")
	}
	day := summary.Periods[metricsWindow24Hours]
	if day.Assessment != "low_data" {
		t.Fatalf("small sample assessment = %q", day.Assessment)
	}
	got := day.Current
	if got.CompletedWorks != 1 || got.LeadTimeSeconds.Sample != 1 {
		t.Fatalf("merged work sample = %#v", got)
	}
	if got.ReviewFirstPass.Count != 0 || got.ReviewFirstPass.Total != 1 ||
		got.VerifyFirstPass.Count != 0 || got.VerifyFirstPass.Total != 1 {
		t.Fatalf("first-pass rates = review %#v verify %#v", got.ReviewFirstPass, got.VerifyFirstPass)
	}
	if got.Rounds.Sample != 1 || got.Rounds.Median == nil || *got.Rounds.Median != 2 ||
		got.Rounds.P90 == nil || *got.Rounds.P90 != 2 {
		t.Fatalf("round distribution = %#v", got.Rounds)
	}
	if got.AutomaticRecoveries != 2 {
		t.Fatalf("automatic recoveries = %d, want cancelled Review + failed Verify", got.AutomaticRecoveries)
	}
	if got.FinalDeadEnds.Count != 1 || got.FinalDeadEnds.Total != 2 ||
		got.FinalDeadEnds.Rate == nil || math.Abs(*got.FinalDeadEnds.Rate-0.5) > 0.000001 {
		t.Fatalf("dead-end denominator = %#v", got.FinalDeadEnds)
	}
	if got.ProductStageTasks != 7 || got.Excluded.Patrol != 1 || got.Excluded.Scheduled != 1 || got.Excluded.Helper != 1 || got.Excluded.Total != 3 {
		t.Fatalf("product/service split = product %d excluded %#v", got.ProductStageTasks, got.Excluded)
	}
	if got.ReleaseFailures != 1 || got.Rollbacks != 1 {
		t.Fatalf("release incidents = failures %d rollbacks %d", got.ReleaseFailures, got.Rollbacks)
	}
	var shareTotal float64
	for _, share := range got.TimeShares {
		if share.Share == nil || share.DenominatorSeconds != 4*time.Hour.Seconds() {
			t.Fatalf("time share denominator = %#v", share)
		}
		shareTotal += *share.Share
	}
	if math.Abs(shareTotal-1) > 0.000001 {
		t.Fatalf("time shares total = %f", shareTotal)
	}
}

func TestEfficiencyUsesRealLegacyMergeJournalLine(t *testing.T) {
	store := newTestStore(t)
	originalLocal := time.Local
	time.Local = time.FixedZone("Factory local", -5*60*60)
	t.Cleanup(func() { time.Local = originalLocal })

	now := time.Date(2026, time.August, 10, 19, 0, 0, 0, time.UTC)
	store.now = func() time.Time { return now }
	home := t.TempDir()
	t.Setenv("FACTORY_DATA_HOME", home)
	if err := os.MkdirAll(filepath.Join(home, "pilot"), 0o755); err != nil {
		t.Fatal(err)
	}
	repository := createManagedTestRepository(t, store, "github.com/example/product")
	if _, err := store.RegisterWorker(context.Background(), "efficiency-worker", protocol.WorkerRegistration{
		Name: "efficiency-worker", WorkerVersion: "test", RuntimeVersion: "test",
		Capacity: 1, Health: "healthy", AcceptsManagedRepositories: true,
		ManagedRepositoryIDs: []string{repository.ID},
	}); err != nil {
		t.Fatal(err)
	}

	mergeAt := time.Date(2026, time.August, 10, 18, 30, 26, 0, time.UTC)
	seedEfficiencyTaskWithID(t, store, repository.ID,
		"ea6b7c68-13de-4455-ad78-311ab8dd65e0", "legacy-merge",
		"[auto] [5/5 Verify] Настройки Пилота не раскрывают канал уведомлений локальным воркерам",
		"succeeded", mergeAt.Add(-time.Hour), mergeAt.Add(-50*time.Minute), mergeAt.Add(-10*time.Minute))
	journal := []byte("{\"task_id\": \"ea6b7c68-13de-4455-ad78-311ab8dd65e0\", \"base\": \"Настройки Пилота не раскрывают канал уведомлений локальным воркерам\", \"at\": \"2026-08-10 13:30:26\"}\n")
	if err := os.WriteFile(filepath.Join(home, "pilot", "merges.jsonl"), journal, 0o644); err != nil {
		t.Fatal(err)
	}

	merges, err := loadEfficiencyMerges()
	if err != nil {
		t.Fatal(err)
	}
	if len(merges) != 1 || !merges[0].at.Equal(mergeAt) || merges[0].at.Location() != time.UTC {
		t.Fatalf("legacy merge parsed as %#v, want %s UTC", merges, mergeAt)
	}
	summary, err := store.Efficiency(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	got := summary.Periods[metricsWindow24Hours].Current
	if got.CompletedWorks != 1 || got.LeadTimeSeconds.Sample != 1 ||
		got.LeadTimeSeconds.Median == nil || *got.LeadTimeSeconds.Median != time.Hour.Seconds() {
		t.Fatalf("legacy journal metrics = %#v", got)
	}
}

func TestEfficiencyEmptyPeriodsDoNotInventRatesOrGreenStatus(t *testing.T) {
	store := newTestStore(t)
	now := time.Date(2026, time.August, 10, 12, 0, 0, 0, time.UTC)
	store.now = func() time.Time { return now }
	t.Setenv("FACTORY_DATA_HOME", t.TempDir())

	summary, err := store.Efficiency(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	for _, key := range []string{metricsWindow24Hours, metricsWindow7Days} {
		period := summary.Periods[key]
		if period.Assessment != "low_data" || period.Current.CompletedWorks != 0 ||
			period.Current.LeadTimeSeconds.Median != nil || period.Current.ReviewFirstPass.Rate != nil ||
			period.Current.FinalDeadEnds.Rate != nil {
			t.Fatalf("empty %s metrics = %#v", key, period)
		}
	}
}

func TestEfficiencyComparisonReportsProgressAndDegradationOnlyWithEnoughData(t *testing.T) {
	rate := func(value float64) EfficiencyRate {
		return EfficiencyRate{Count: int(value * 10), Total: 10, Rate: &value}
	}
	distribution := func(p90 float64) EfficiencyDistribution {
		return EfficiencyDistribution{Sample: 6, Median: &p90, P90: &p90}
	}
	previous := EfficiencyPeriod{
		CompletedWorks: 5, LeadTimeSeconds: distribution(100),
		ReviewFirstPass: rate(0.7), VerifyFirstPass: rate(0.8), FinalDeadEnds: rate(0.2),
	}
	improved := EfficiencyPeriod{
		CompletedWorks: 6, LeadTimeSeconds: distribution(90),
		ReviewFirstPass: rate(0.8), VerifyFirstPass: rate(0.9), FinalDeadEnds: rate(0.1),
	}
	if got := compareEfficiencyPeriods(improved, previous); got != "improved" {
		t.Fatalf("improved comparison = %q", got)
	}
	degraded := EfficiencyPeriod{
		CompletedWorks: 5, LeadTimeSeconds: distribution(120),
		ReviewFirstPass: rate(0.6), VerifyFirstPass: rate(0.7), FinalDeadEnds: rate(0.3),
	}
	if got := compareEfficiencyPeriods(degraded, EfficiencyPeriod{
		CompletedWorks: 6, LeadTimeSeconds: distribution(100),
		ReviewFirstPass: rate(0.7), VerifyFirstPass: rate(0.8), FinalDeadEnds: rate(0.2),
	}); got != "degraded" {
		t.Fatalf("degraded comparison = %q", got)
	}
	improved.CompletedWorks = efficiencyMinimumSample - 1
	if got := compareEfficiencyPeriods(improved, previous); got != "low_data" {
		t.Fatalf("small improved sample = %q", got)
	}
}

func TestEfficiencyDistributionUsesNearestRankP90(t *testing.T) {
	distribution := efficiencyDistribution([]float64{10, 1, 5, 4, 8, 3, 9, 2, 7, 6})
	if distribution.Median == nil || *distribution.Median != 5.5 || distribution.P90 == nil || *distribution.P90 != 9 {
		t.Fatalf("distribution = %#v", distribution)
	}
}

func TestHTTPEfficiencyReturnsBothFixedComparablePeriods(t *testing.T) {
	fixture := newHTTPFixture(t)
	t.Setenv("FACTORY_DATA_HOME", t.TempDir())
	response := fixture.request(http.MethodGet, "/api/v1/metrics/efficiency", "", "", nil)
	requireStatus(t, response, http.StatusOK)
	summary := decodeResponse[EfficiencySummary](t, response)
	if summary.MinimumSample != efficiencyMinimumSample || len(summary.Periods) != 2 ||
		summary.Periods[metricsWindow24Hours].Assessment != "low_data" ||
		summary.Periods[metricsWindow7Days].Assessment != "low_data" {
		t.Fatalf("efficiency response = %#v", summary)
	}

	response = fixture.request(http.MethodGet, "/api/v1/metrics/efficiency?window=all", "", "", nil)
	requireStatus(t, response, http.StatusBadRequest)
	response.Body.Close()
}

func TestEfficiencyFactColumnsAreIndexed(t *testing.T) {
	store := newTestStore(t)
	for _, name := range []string{"tasks_efficiency_created_title", "attempts_efficiency_execution_order"} {
		var count int
		if err := store.db.QueryRow(`SELECT COUNT(*) FROM sqlite_master WHERE type = 'index' AND name = ?`, name).Scan(&count); err != nil {
			t.Fatal(err)
		}
		if count != 1 {
			t.Fatalf("efficiency index %q count = %d", name, count)
		}
	}
}

func seedEfficiencyTask(t *testing.T, store *Store, repositoryID, id, title, state string, createdAt, startedAt, updatedAt time.Time) string {
	t.Helper()
	taskID := "task-" + id
	return seedEfficiencyTaskWithID(t, store, repositoryID, taskID, id, title, state, createdAt, startedAt, updatedAt)
}

func seedEfficiencyTaskWithID(t *testing.T, store *Store, repositoryID, taskID, id, title, state string, createdAt, startedAt, updatedAt time.Time) string {
	t.Helper()
	executionID := "execution-" + id
	if _, err := store.db.Exec(`
		INSERT INTO tasks(id, request_key, title, description, repository_id, timeout_seconds, created_at)
		VALUES (?, ?, ?, 'efficiency fixture', ?, 3600, ?)
	`, taskID, "request-"+id, title, repositoryID, createdAt.UnixMilli()); err != nil {
		t.Fatal(err)
	}
	if _, err := store.db.Exec(`
		INSERT INTO executions(id, task_id, assigned_worker_id, required_runtime, state,
			cancellation_requested, retry_count, created_at, updated_at)
		VALUES (?, ?, 'efficiency-worker', 'codex', ?, 0, 0, ?, ?)
	`, executionID, taskID, state, createdAt.UnixMilli(), updatedAt.UnixMilli()); err != nil {
		t.Fatal(err)
	}
	if _, err := store.db.Exec(`
		INSERT INTO attempts(id, execution_id, worker_id, attempt_number, state, lease_digest,
			lease_expires_at, started_at, completed_at, created_at)
		VALUES (?, ?, 'efficiency-worker', 1, ?, X'00', ?, ?, ?, ?)
	`, "attempt-"+id, executionID, state, updatedAt.UnixMilli(), startedAt.UnixMilli(), updatedAt.UnixMilli(), createdAt.UnixMilli()); err != nil {
		t.Fatal(err)
	}
	return taskID
}

func linkEfficiencySchedule(t *testing.T, store *Store, repositoryID, taskID, suffix, contextText string, now time.Time) {
	t.Helper()
	workflow := createTestWorkflow(t, store, suffix+"-workflow", "Schedule "+suffix, "Inspect pipelines.")
	detail, _, err := store.CreateAutomation(context.Background(), protocol.CreateAutomationRequest{
		RequestKey: suffix + "-automation", Title: "Schedule " + suffix,
		WorkflowID: workflow.Workflow.ID, RepositoryID: repositoryID,
		Context: contextText, TimeoutSeconds: 3600,
		Trigger: protocol.AutomationTrigger{Type: protocol.AutomationTriggerSchedule, Cron: "0 * * * *", Timezone: "UTC"},
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := store.db.Exec(`
		INSERT INTO automation_occurrences(
			id, automation_id, automation_version, automation_title, workflow_revision_id,
			repository_id, repository_identity, context, timeout_seconds, state,
			task_request_key, task_id, task_id_snapshot, created_at, updated_at
		) VALUES (?, ?, ?, ?, ?, ?, 'github.com/example/product', ?, 3600,
			'dispatched', ?, ?, ?, ?, ?)
	`, "occurrence-"+suffix, detail.Automation.ID, detail.Automation.Version, detail.Automation.Title,
		workflow.Workflow.CurrentRevision.ID, repositoryID, contextText,
		"occurrence-task-"+suffix, taskID, taskID,
		now.Add(-80*time.Minute).UnixMilli(), now.Add(-60*time.Minute).UnixMilli()); err != nil {
		t.Fatal(err)
	}
}

func writeJSONLines(t *testing.T, path string, values []any) {
	t.Helper()
	file, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	encoder := json.NewEncoder(file)
	for _, value := range values {
		if err := encoder.Encode(value); err != nil {
			file.Close()
			t.Fatal(err)
		}
	}
	if err := file.Close(); err != nil {
		t.Fatal(err)
	}
}
