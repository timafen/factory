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
	replayed, err := store.ProvisionPipelinePatrol(context.Background(), detail.Automation.ID)
	if err != nil || replayed.Automation.Context != provisioned.Automation.Context {
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
