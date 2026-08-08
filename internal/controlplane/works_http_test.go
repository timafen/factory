package controlplane

import (
	"net/http"
	"testing"

	"github.com/owainlewis/factory/internal/protocol"
)

func TestWorksReturnsStructuredStageFromTaskWorkflow(t *testing.T) {
	fixture := newHTTPFixture(t)
	worker := registerTestWorker(t, fixture.store, "works-stage-worker", 1, protocol.RepositoryRegistration{
		Key: "factory", RemoteIdentity: "github.com/example/factory",
	})
	workflow := createTestWorkflow(t, fixture.store, "works-stage-workflow", "Implement + Test", "Implement the task")
	task := createTestTask(t, fixture.store, "works-stage-task", worker.ID, worker.Repositories[0].ID)
	if _, err := fixture.store.db.Exec(`
		UPDATE tasks
		SET workflow_id = ?, workflow_revision_id = ?, workflow_title = ?, workflow_revision_number = ?
		WHERE id = ?
	`, workflow.Workflow.ID, workflow.Workflow.CurrentRevision.ID,
		workflow.Workflow.CurrentRevision.Title, workflow.Workflow.CurrentRevision.RevisionNumber, task.Task.ID); err != nil {
		t.Fatal(err)
	}

	response := fixture.request(http.MethodGet, "/api/v1/works", "", "", nil)
	requireStatus(t, response, http.StatusOK)
	works := decodeResponse[map[string]workMetadata](t, response)
	if works[task.Task.ID].Stage != "Implement + Test" {
		t.Fatalf("stage = %q, want task workflow title", works[task.Task.ID].Stage)
	}
}
