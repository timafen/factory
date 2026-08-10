package controlplane

import (
	"bytes"
	"context"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/owainlewis/factory/internal/protocol"
)

func TestPipelinePatrolProvisionUsesExistingScheduleAndPreservesRuns(t *testing.T) {
	if !stringsContain(PipelinePatrolInstruction, "wait 120 seconds") || stringsContain(PipelinePatrolInstruction, "wait 600 seconds") {
		t.Fatalf("patrol instruction does not enforce the 120-second wait: %q", PipelinePatrolInstruction)
	}
	now := time.Date(2026, 8, 1, 7, 0, 0, 0, time.UTC)
	store, detail := createScheduleAutomationFixture(t, &now, true)

	service := newAutomationService(store, slog.Default(), fakeGitHubIssueLister{})
	server := httptest.NewServer(NewHandlerWithAutomation(store, slog.Default(), service))
	defer server.Close()
	request, err := http.NewRequest(http.MethodPost, server.URL+"/api/v1/automations/"+detail.Automation.ID+"/pipeline-patrol", bytes.NewReader([]byte(`{}`)))
	if err != nil {
		t.Fatal(err)
	}
	request.Header.Set("Content-Type", "application/json")
	response, err := server.Client().Do(request)
	if err != nil {
		t.Fatal(err)
	}
	requireStatus(t, response, http.StatusOK)
	provisioned := decodeResponse[protocol.AutomationDetail](t, response)
	if !provisioned.Automation.Enabled || provisioned.Automation.NextDueAt == nil ||
		provisioned.Automation.Trigger.Cron != detail.Automation.Trigger.Cron ||
		provisioned.Automation.Trigger.Timezone != detail.Automation.Trigger.Timezone {
		t.Fatalf("provisioned schedule = %#v", provisioned.Automation)
	}
	if !stringsContain(provisioned.Automation.Context, PipelinePatrolInstruction) {
		t.Fatalf("patrol context = %q", provisioned.Automation.Context)
	}
	if provisioned.Automation.Version != detail.Automation.Version+1 {
		t.Fatalf("provisioned version = %d, want %d", provisioned.Automation.Version, detail.Automation.Version+1)
	}
	replayed, err := store.ProvisionPipelinePatrol(context.Background(), detail.Automation.ID)
	if err != nil || replayed.Automation.Context != provisioned.Automation.Context || replayed.Automation.Version != provisioned.Automation.Version {
		t.Fatalf("replayed provision = %#v, error %v", replayed.Automation, err)
	}

	now = *provisioned.Automation.NextDueAt
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
	current, err := store.Automation(context.Background(), detail.Automation.ID)
	if err != nil {
		t.Fatal(err)
	}
	if len(current.Occurrences) != 1 || current.Occurrences[0].Task == nil {
		t.Fatalf("durable patrol runs = %#v", current.Occurrences)
	}
}

func TestPipelinePatrolProvisionDoesNotInventSchedule(t *testing.T) {
	store := newTestStore(t)
	_, err := store.ProvisionPipelinePatrol(context.Background(), "")
	assertErrorCode(t, err, "pipeline_patrol_automation_required")
}

func TestPipelinePatrolProvisionMakesPriorVersionStale(t *testing.T) {
	now := time.Date(2026, 8, 1, 7, 0, 0, 0, time.UTC)
	store, detail := createScheduleAutomationFixture(t, &now, false)
	provisioned, err := store.ProvisionPipelinePatrol(context.Background(), detail.Automation.ID)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := store.SetAutomationEnabled(context.Background(), detail.Automation.ID, false, false); err != nil {
		t.Fatal(err)
	}
	_, err = store.UpdateAutomation(context.Background(), detail.Automation.ID, protocol.UpdateAutomationRequest{
		ExpectedVersion: detail.Automation.Version,
		Title:           detail.Automation.Title,
		WorkflowID:      detail.Automation.WorkflowID,
		Context:         detail.Automation.Context,
		TimeoutSeconds:  detail.Automation.TimeoutSeconds,
		Trigger:         detail.Automation.Trigger,
	})
	assertErrorCode(t, err, "automation_version_conflict")
	current, err := store.Automation(context.Background(), detail.Automation.ID)
	if err != nil {
		t.Fatal(err)
	}
	if current.Automation.Version != provisioned.Automation.Version || !stringsContain(current.Automation.Context, PipelinePatrolInstruction) {
		t.Fatalf("Automation after stale update = %#v", current.Automation)
	}
}

func TestPipelinePatrolProvisionReplacesLegacyWaitWithoutLosingContext(t *testing.T) {
	now := time.Date(2026, 8, 1, 7, 0, 0, 0, time.UTC)
	store, detail := createScheduleAutomationFixture(t, &now, false)
	legacyContext := "Keep the owner guardrail.\n\n" + legacyPipelinePatrolInstruction + "\n\nKeep the audit note."
	updated, err := store.UpdateAutomation(context.Background(), detail.Automation.ID, protocol.UpdateAutomationRequest{
		ExpectedVersion: detail.Automation.Version,
		Title:           detail.Automation.Title,
		WorkflowID:      detail.Automation.WorkflowID,
		Context:         legacyContext,
		TimeoutSeconds:  detail.Automation.TimeoutSeconds,
		Trigger:         detail.Automation.Trigger,
	})
	if err != nil {
		t.Fatal(err)
	}

	provisioned, err := store.ProvisionPipelinePatrol(context.Background(), detail.Automation.ID)
	if err != nil {
		t.Fatal(err)
	}
	wantContext := "Keep the owner guardrail.\n\n" + PipelinePatrolInstruction + "\n\nKeep the audit note."
	if provisioned.Automation.Context != wantContext || stringsContain(provisioned.Automation.Context, legacyPipelinePatrolInstruction) {
		t.Fatalf("updated patrol context = %q", provisioned.Automation.Context)
	}
	if provisioned.Automation.Version != updated.Automation.Version+1 {
		t.Fatalf("updated version = %d, want %d", provisioned.Automation.Version, updated.Automation.Version+1)
	}
	replayed, err := store.ProvisionPipelinePatrol(context.Background(), detail.Automation.ID)
	if err != nil || replayed.Automation.Context != wantContext || replayed.Automation.Version != provisioned.Automation.Version {
		t.Fatalf("replayed provision = %#v, error %v", replayed.Automation, err)
	}
}

func TestPipelinePatrolProvisionEnforcesContextByteLimit(t *testing.T) {
	for _, test := range []struct {
		name      string
		finalSize int
		wantError bool
	}{
		{name: "exact limit", finalSize: protocol.MaxAutomationContextBytes},
		{name: "one byte over", finalSize: protocol.MaxAutomationContextBytes + 1, wantError: true},
	} {
		t.Run(test.name, func(t *testing.T) {
			now := time.Date(2026, 8, 1, 7, 0, 0, 0, time.UTC)
			store, detail := createScheduleAutomationFixture(t, &now, false)
			prefixSize := test.finalSize - len([]byte(PipelinePatrolInstruction)) - len("\n\n")
			updated, err := store.UpdateAutomation(context.Background(), detail.Automation.ID, protocol.UpdateAutomationRequest{
				ExpectedVersion: detail.Automation.Version,
				Title:           detail.Automation.Title,
				WorkflowID:      detail.Automation.WorkflowID,
				Context:         string(bytes.Repeat([]byte("x"), prefixSize)),
				TimeoutSeconds:  detail.Automation.TimeoutSeconds,
				Trigger:         detail.Automation.Trigger,
			})
			if err != nil {
				t.Fatal(err)
			}
			provisioned, err := store.ProvisionPipelinePatrol(context.Background(), detail.Automation.ID)
			if test.wantError {
				assertErrorCode(t, err, "invalid_automation_context")
				current, loadErr := store.Automation(context.Background(), detail.Automation.ID)
				if loadErr != nil {
					t.Fatal(loadErr)
				}
				if current.Automation.Version != updated.Automation.Version || current.Automation.Enabled {
					t.Fatalf("rejected provision mutated Automation = %#v", current.Automation)
				}
				return
			}
			if err != nil {
				t.Fatal(err)
			}
			if len([]byte(provisioned.Automation.Context)) != protocol.MaxAutomationContextBytes {
				t.Fatalf("provisioned context size = %d", len([]byte(provisioned.Automation.Context)))
			}
		})
	}
}
