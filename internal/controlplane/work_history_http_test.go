package controlplane

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/url"
	"strings"
	"testing"

	"github.com/owainlewis/factory/internal/protocol"
)

func TestHTTPWorkHistoryReturnsOnlyHumanReadableSafeSummaries(t *testing.T) {
	fixture := newHTTPFixture(t)
	worker := registerHTTPWorker(t, fixture, workerA, "factory", "github.com/owainlewis/factory", 1)
	completed := createTestTask(t, fixture.store, "history-completed", workerA, worker.Repositories[0].ID)
	claim := claimTestTask(t, fixture.store, workerA, "history-claim", tokenA)
	queued := createTestTask(t, fixture.store, "history-queued", workerA, worker.Repositories[0].ID)
	if claim.Task.ID != completed.Task.ID {
		t.Fatalf("claimed task = %q; want %q", claim.Task.ID, completed.Task.ID)
	}

	const sensitiveOutput = "SECRET-OUTPUT-MUST-STAY-HIDDEN"
	const sensitiveContext = "SECRET-CONTEXT-MUST-STAY-HIDDEN"
	if err := fixture.store.AppendEvents(context.Background(), claim.Attempt.ID, protocol.EventBatchRequest{
		LeaseToken: tokenA,
		Events: []protocol.AttemptEvent{{
			Sequence: 0,
			Kind:     "output",
			Payload:  json.RawMessage(`{"output":"` + sensitiveOutput + `","context":"` + sensitiveContext + `"}`),
		}},
	}); err != nil {
		t.Fatal(err)
	}
	if _, err := fixture.store.CompleteAttempt(context.Background(), claim.Attempt.ID, protocol.CompleteAttemptRequest{
		LeaseToken: tokenA,
		State:      "failed",
		Result:     sensitiveOutput,
		Error:      sensitiveContext,
	}); err != nil {
		t.Fatal(err)
	}

	query := url.Values{"task_id": {queued.Task.ID, claim.Task.ID}}
	response := fixture.request(http.MethodGet, "/api/v1/work-history?"+query.Encode(), "", "", nil)
	requireStatus(t, response, http.StatusOK)
	body, err := io.ReadAll(response.Body)
	response.Body.Close()
	if err != nil {
		t.Fatal(err)
	}
	for _, forbidden := range []string{
		sensitiveOutput, sensitiveContext, `"output"`, `"prompt"`, `"context"`, `"result"`, `"error"`, `"payload"`,
	} {
		if strings.Contains(string(body), forbidden) {
			t.Fatalf("work history exposed forbidden data %q: %s", forbidden, body)
		}
	}
	var payload struct {
		History []workHistoryEntry `json:"history"`
	}
	if err := json.Unmarshal(body, &payload); err != nil {
		t.Fatal(err)
	}
	if len(payload.History) != 2 ||
		payload.History[0] != (workHistoryEntry{TaskID: queued.Task.ID, Text: "Ожидает начала работы."}) ||
		payload.History[1] != (workHistoryEntry{TaskID: claim.Task.ID, Text: "Попытка 1: завершилась неудачно."}) {
		t.Fatalf("history = %#v", payload.History)
	}
}

func TestHTTPWorkHistoryRequiresValidTaskIDs(t *testing.T) {
	fixture := newHTTPFixture(t)
	for _, path := range []string{
		"/api/v1/work-history",
		"/api/v1/work-history?task_id=one&task_id=one",
	} {
		response := fixture.request(http.MethodGet, path, "", "", nil)
		requireStatus(t, response, http.StatusBadRequest)
		response.Body.Close()
	}
}
