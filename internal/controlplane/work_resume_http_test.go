package controlplane

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"

	"github.com/owainlewis/factory/internal/protocol"
)

func resumeFixture(t *testing.T, base string) (*Store, *PilotConfigStore, *httptest.Server, protocol.Repository, map[string]protocol.Workflow) {
	t.Helper()
	dataHome := t.TempDir()
	t.Setenv("FACTORY_DATA_HOME", dataHome)
	if err := os.MkdirAll(filepath.Join(dataHome, "pilot", "verdicts"), 0o700); err != nil {
		t.Fatal(err)
	}
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

func writeResumeWork(t *testing.T, base string, metadata resumeWorkMetadata) {
	t.Helper()
	data, err := json.Marshal(map[string]resumeWorkMetadata{base: metadata})
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(worksPath(), data, 0o600); err != nil {
		t.Fatal(err)
	}
}

func writeResumeVerdict(t *testing.T, taskID, action string) {
	t.Helper()
	data, err := json.Marshal(map[string]string{"action": action})
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(verdictsDir(), taskID+".json"), data, 0o600); err != nil {
		t.Fatal(err)
	}
}

func addResumeHistory(t *testing.T, store *Store, repository protocol.Repository, workflows map[string]protocol.Workflow, base string, stages []string, state string) map[string]protocol.Task {
	t.Helper()
	history := make(map[string]protocol.Task, len(stages))
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
		history[stage] = detail.Task
	}
	return history
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

func TestResumePausedWorkRestartsFailedFirstEffectiveStageAndIsIdempotent(t *testing.T) {
	for _, terminal := range []string{"failed", "cancelled"} {
		t.Run(terminal, func(t *testing.T) {
			base := "Возобновить первую обязательную стадию " + terminal
			store, pilot, server, repo, workflows := resumeFixture(t, base)
			writeResumeWork(t, base, resumeWorkMetadata{
				StartStage: "Implement + Test",
				Skipped:    []string{"Triage", "Specification"},
			})
			addResumeHistory(t, store, repo, workflows, base, []string{"Implement + Test"}, terminal)

			status, first := postResume(t, server, base)
			if status != http.StatusOK || first.Stage != "Implement + Test" || !first.Resumed || first.Task.State != "queued" {
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

func TestResumePausedWorkUsesVerdictActionForReviewAndVerify(t *testing.T) {
	all := []string{"Triage", "Specification", "Implement + Test", "Review", "Verify"}
	for _, tc := range []struct {
		name       string
		stages     []string
		verdicts   map[string]string
		wantStatus int
		wantStage  string
	}{
		{
			name:   "review stop returns to implementation",
			stages: all[:4], verdicts: map[string]string{"Review": "stop"},
			wantStatus: http.StatusOK, wantStage: "Implement + Test",
		},
		{
			name:   "verify stop returns to implementation",
			stages: all, verdicts: map[string]string{"Review": "advance", "Verify": "stop"},
			wantStatus: http.StatusOK, wantStage: "Implement + Test",
		},
		{
			name:   "review advance proceeds to verify",
			stages: all[:4], verdicts: map[string]string{"Review": "advance"},
			wantStatus: http.StatusOK, wantStage: "Verify",
		},
		{
			name:   "verify advance completes pipeline",
			stages: all, verdicts: map[string]string{"Review": "advance", "Verify": "advance"},
			wantStatus: http.StatusConflict,
		},
	} {
		t.Run(tc.name, func(t *testing.T) {
			base := "Вердикт " + tc.name
			store, _, server, repo, workflows := resumeFixture(t, base)
			history := addResumeHistory(t, store, repo, workflows, base, tc.stages, "succeeded")
			for stage, action := range tc.verdicts {
				writeResumeVerdict(t, history[stage].ID, action)
			}
			status, resumed := postResume(t, server, base)
			if status != tc.wantStatus || (tc.wantStage != "" && resumed.Stage != tc.wantStage) {
				t.Fatalf("resume = status %d %#v, want status %d stage %q", status, resumed, tc.wantStatus, tc.wantStage)
			}
		})
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

func TestResumePausedWorkRetryAfterSettingsWriteFailureDoesNotDuplicateTask(t *testing.T) {
	const base = "Повтор после ошибки записи"
	store, pilot, server, repo, workflows := resumeFixture(t, base)
	addResumeHistory(t, store, repo, workflows, base, []string{"Triage"}, "failed")

	pilot.writeTemp = func(*os.File, []byte) (int, error) { return 0, errors.New("disk unavailable") }
	status, _ := postResume(t, server, base)
	if status != http.StatusServiceUnavailable {
		t.Fatalf("resume with write failure status = %d, want %d", status, http.StatusServiceUnavailable)
	}
	page, err := store.Tasks(context.Background(), protocol.TaskPageRequest{Limit: 200})
	if err != nil || len(page.Tasks) != 2 {
		t.Fatalf("tasks after failed write = %#v, %v", page, err)
	}
	var createdID string
	if err := store.db.QueryRow(`SELECT id FROM tasks WHERE request_key LIKE 'resume:%'`).Scan(&createdID); err != nil {
		t.Fatal(err)
	}

	pilot.writeTemp = nil
	status, retried := postResume(t, server, base)
	if status != http.StatusOK || retried.Resumed || retried.Task.ID != createdID {
		t.Fatalf("retry = status %d %#v, want existing task %s", status, retried, createdID)
	}
	page, err = store.Tasks(context.Background(), protocol.TaskPageRequest{Limit: 200})
	if err != nil || len(page.Tasks) != 2 {
		t.Fatalf("retry duplicated task: %#v, %v", page, err)
	}
}
