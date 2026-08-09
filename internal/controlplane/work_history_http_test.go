package controlplane

import (
	"net/http"
	"net/url"
	"strings"
	"testing"

	"github.com/owainlewis/factory/internal/protocol"
)

func TestHTTPWorkHistoryUsesPlainStatusWithoutTaskOutput(t *testing.T) {
	fixture := newHTTPFixture(t)
	worker := registerTestWorker(t, fixture.store, workerA, 1, protocol.RepositoryRegistration{
		Key: "factory", RemoteIdentity: "github.com/owainlewis/factory",
	})
	task := createTestTask(t, fixture.store, "plain-work-history", worker.ID, worker.Repositories[0].ID)

	response := fixture.request(http.MethodGet, "/api/v1/work-history?task_id="+url.QueryEscape(task.Task.ID), "", "", nil)
	requireStatus(t, response, http.StatusOK)
	body := decodeResponse[struct {
		History []workHistoryEntry `json:"history"`
	}](t, response)
	if len(body.History) != 1 || body.History[0] != (workHistoryEntry{TaskID: task.Task.ID, Text: "ждёт исполнителя"}) {
		t.Fatalf("history = %#v", body.History)
	}
	encoded := strings.Join([]string{body.History[0].TaskID, body.History[0].Text}, " ")
	if strings.Contains(encoded, task.Context) || strings.Contains(encoded, task.ResolvedPrompt) {
		t.Fatalf("work history leaked technical task content: %q", encoded)
	}
}

func TestHTTPWorkHistoryRequiresTaskIDs(t *testing.T) {
	fixture := newHTTPFixture(t)
	response := fixture.request(http.MethodGet, "/api/v1/work-history", "", "", nil)
	requireStatus(t, response, http.StatusBadRequest)
}
