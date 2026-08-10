package controlplane

import (
	"bytes"
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/owainlewis/factory/internal/protocol"
)

func resumeFixture(t *testing.T, base string) (*Store, *PilotConfigStore, *httptest.Server, protocol.Repository, map[string]protocol.Workflow) {
	t.Helper()
	store := newTestStore(t)
	settings := validPilotSettings()
	settings.StoppedPipelines = []string{base}
	pilot, _ := writePilotFixture(t, settings)
	worker, err := store.RegisterWorker(context.Background(), "worker-1", protocol.WorkerRegistration{
		Name: "worker-1", WorkerVersion: "test", RuntimeVersion: "test", Capacity: 2, Health: "healthy",
		Repositories: []protocol.RepositoryRegistration{{Key: "repo", RemoteIdentity: "github.com/example/repo"}},
	})
	if err != nil {
		t.Fatal(err)
	}
	workflows := map[string]protocol.Workflow{}
	for _, stage := range pilotStages {
		detail := createTestWorkflow(t, store, "workflow-"+stage, stage, "do "+stage)
		workflows[stage] = detail.Workflow
	}
	server := httptest.NewServer(NewHandlerWithPilotConfig(store, slog.Default(), NewAutomationService(store, slog.Default()), pilot))
	t.Cleanup(server.Close)
	return store, pilot, server, worker.Repositories[0], workflows
}

func addResumeHistory(t *testing.T, store *Store, repository protocol.Repository, workflows map[string]protocol.Workflow, base string, stages []string, state string) {
	t.Helper()
	for index, stage := range stages {
		workflow := workflows[stage]
		detail, created, err := store.CreateTask(context.Background(), protocol.CreateTaskRequest{
			RequestKey: "history-" + base + stage, Title: "[auto] [" + string(rune('1'+index)) + "/5 " + stage + "] " + base,
			Context: "saved pipeline context", ContextProvided: true,
			WorkerID: "worker-1", RepositoryID: repository.ID, TimeoutSeconds: 60,
			WorkflowRevisionID: workflow.CurrentRevision.ID, WorkflowRevisionIDProvided: true,
		})
		if err != nil || !created {
			t.Fatalf("history %s: created=%v err=%v", stage, created, err)
		}
		if _, err := store.db.Exec(`UPDATE executions SET state=? WHERE task_id=?`, state, detail.Task.ID); err != nil {
			t.Fatal(err)
		}
	}
}

func postResume(t *testing.T, server *httptest.Server, base string) (int, resumeWorkResponse) {
	t.Helper()
	body, _ := json.Marshal(resumeWorkRequest{Title: base})
	response, err := server.Client().Post(server.URL+"/api/v1/works/resume", "application/json", bytes.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	var result resumeWorkResponse
	_ = json.NewDecoder(response.Body).Decode(&result)
	return response.StatusCode, result
}

func TestResumePausedWorkRestartsTerminalFirstStageAndIsIdempotent(t *testing.T) {
	for _, terminal := range []string{"failed", "cancelled"} {
		t.Run(terminal, func(t *testing.T) {
			base := "Возобновить первую стадию " + terminal
			store, pilot, server, repo, workflows := resumeFixture(t, base)
			addResumeHistory(t, store, repo, workflows, base, []string{"Triage"}, terminal)

			status, first := postResume(t, server, base)
			if status != http.StatusOK || first.Stage != "Triage" || !first.Resumed || first.Task.State != "queued" {
				t.Fatalf("first resume = status %d %#v", status, first)
			}
			status, second := postResume(t, server, base)
			if status != http.StatusOK || second.Task.ID != first.Task.ID || second.Resumed {
				t.Fatalf("repeat resume = status %d %#v", status, second)
			}
			page, err := store.Tasks(context.Background(), protocol.TaskPageRequest{Limit: 200})
			if err != nil || len(page.Tasks) != 2 {
				t.Fatalf("tasks after repeat = %#v, %v", page, err)
			}
			settings, err := pilot.Read()
			if err != nil || len(settings.Settings.StoppedPipelines) != 0 {
				t.Fatalf("pause after resume = %#v, %v", settings.Settings.StoppedPipelines, err)
			}
		})
	}
}

func TestResumePausedWorkContinuesAfterReviewWithoutSkippingVerify(t *testing.T) {
	const base = "Продолжить после ревью"
	store, _, server, repo, workflows := resumeFixture(t, base)
	addResumeHistory(t, store, repo, workflows, base, []string{"Triage", "Specification", "Implement + Test", "Review"}, "succeeded")
	status, resumed := postResume(t, server, base)
	if status != http.StatusOK || resumed.Stage != "Verify" || resumed.Task.State != "queued" {
		t.Fatalf("resume after review = status %d %#v", status, resumed)
	}
}

func TestResumePausedWorkOnlyClearsStalePauseForAlreadyActiveTask(t *testing.T) {
	const base = "Уже работает"
	store, pilot, server, repo, workflows := resumeFixture(t, base)
	addResumeHistory(t, store, repo, workflows, base, []string{"Triage", "Specification"}, "succeeded")
	addResumeHistory(t, store, repo, workflows, base, []string{"Implement + Test"}, "running")
	status, resumed := postResume(t, server, base)
	if status != http.StatusOK || resumed.Stage != "Implement + Test" || resumed.Resumed {
		t.Fatalf("active resume = status %d %#v", status, resumed)
	}
	page, err := store.Tasks(context.Background(), protocol.TaskPageRequest{Limit: 200})
	if err != nil || len(page.Tasks) != 3 {
		t.Fatalf("active resume duplicated a task: %#v, %v", page, err)
	}
	settings, err := pilot.Read()
	if err != nil || len(settings.Settings.StoppedPipelines) != 0 {
		t.Fatalf("active pause = %#v, %v", settings.Settings.StoppedPipelines, err)
	}
}
