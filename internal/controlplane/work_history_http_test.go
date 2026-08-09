package controlplane

import (
	"net/http"
	"net/url"
	"strings"
	"testing"

	"github.com/owainlewis/factory/internal/protocol"
)

func TestHTTPWorkHistoryReturnsSafeRussianSummary(t *testing.T) {
	fixture := newHTTPFixture(t)
	worker := registerHTTPWorker(t, fixture, workerA, "factory", "github.com/owainlewis/factory", 1)
	const sensitive = "SECRET agent output must not be returned"
	response := fixture.request(http.MethodPost, "/api/v1/tasks", "application/json", fixture.server.URL, protocol.CreateTaskRequest{
		RequestKey: "history-task", Title: "[auto] [3/5 Implement + Test] История", Description: sensitive,
		WorkerID: workerA, RepositoryID: worker.Repositories[0].ID, TimeoutSeconds: 60,
	})
	requireStatus(t, response, http.StatusCreated)
	task := decodeResponse[protocol.TaskDetail](t, response)

	response = fixture.request(http.MethodGet, "/api/v1/work-history?task_id="+url.QueryEscape(task.Task.ID)+"&task_id=missing", "", "", nil)
	requireStatus(t, response, http.StatusOK)
	body := decodeResponse[struct {
		History []workHistoryEntry `json:"history"`
	}](t, response)
	if len(body.History) != 1 || body.History[0].TaskID != task.Task.ID || body.History[0].Text != "Этап ждёт запуска" {
		t.Fatalf("history = %#v", body.History)
	}
	if strings.Contains(body.History[0].Text, sensitive) {
		t.Fatal("work history exposed task content")
	}
}

func TestHTTPWorkHistoryRejectsUnsafeOrUnboundedQueries(t *testing.T) {
	fixture := newHTTPFixture(t)
	for _, path := range []string{
		"/api/v1/work-history?task_id=../../secret",
		"/api/v1/work-history?unknown=value",
		"/api/v1/work-history?" + strings.Repeat("task_id=x&", maxWorkHistoryTasks+1),
	} {
		response := fixture.request(http.MethodGet, path, "", "", nil)
		requireStatus(t, response, http.StatusBadRequest)
		response.Body.Close()
	}
}
