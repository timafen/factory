package releasebroker

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

const testSHA = "0123456789abcdef0123456789abcdef01234567"

type recordingExecutor struct {
	mu      sync.Mutex
	adapter string
	sha     string
	done    chan struct{}
}

type sequenceExecutor struct {
	mu       sync.Mutex
	statuses []string
	calls    int
}

func (executor *sequenceExecutor) Execute(_ context.Context, _, _ string) string {
	executor.mu.Lock()
	defer executor.mu.Unlock()
	status := executor.statuses[executor.calls]
	executor.calls++
	return status
}

func (executor *recordingExecutor) Execute(_ context.Context, adapter, sha string) string {
	executor.mu.Lock()
	executor.adapter, executor.sha = adapter, sha
	executor.mu.Unlock()
	if executor.done != nil {
		<-executor.done
	}
	return "succeeded"
}

func TestBrokerAcceptsOnlyFixedAdapterInputsAndIsIdempotent(t *testing.T) {
	executor := &recordingExecutor{done: make(chan struct{})}
	server := httptest.NewServer(New(executor).Handler())
	defer server.Close()
	body := `{"operation_id":"project-release-1","adapter":"tarser-staging-deploy-release","commit_sha":"` + testSHA + `"}`
	request := func(value string) *http.Response {
		response, err := http.Post(server.URL+"/v1/operations", "application/json", strings.NewReader(value))
		if err != nil {
			t.Fatal(err)
		}
		return response
	}
	first := request(body)
	if first.StatusCode != http.StatusAccepted {
		t.Fatalf("first status=%d", first.StatusCode)
	}
	_ = first.Body.Close()
	duplicate := request(body)
	if duplicate.StatusCode != http.StatusOK {
		t.Fatalf("duplicate status=%d", duplicate.StatusCode)
	}
	_ = duplicate.Body.Close()
	for _, bad := range []string{
		`{"operation_id":"shell","adapter":"sh -c anything","commit_sha":"` + testSHA + `"}`,
		`{"operation_id":"bad-sha","adapter":"fx-factory-release","commit_sha":"main"}`,
		`{"operation_id":"extra","adapter":"fx-factory-release","commit_sha":"` + testSHA + `","command":"id"}`,
	} {
		response := request(bad)
		if response.StatusCode != http.StatusBadRequest {
			t.Fatalf("unsafe request status=%d", response.StatusCode)
		}
		_ = response.Body.Close()
	}
	close(executor.done)
}

func TestFXExecutorMapsEveryAdapterToFixedArgv(t *testing.T) {
	for adapter, want := range map[string]string{
		"fx-factory-release":            "factory release " + testSHA,
		"fx-factory-rollback":           "factory rollback",
		"tarser-staging-deploy-release": "staging release " + testSHA,
		"tarser-staging-auto-rollback":  "staging rollback",
	} {
		args, ok := invocation(adapter, testSHA)
		if !ok || strings.Join(args, " ") != want {
			t.Fatalf("adapter %q argv=%q allowed=%v", adapter, args, ok)
		}
	}
	if _, ok := invocation("anything", testSHA); ok {
		t.Fatal("unknown adapter was allowed")
	}
}

func TestFXExecutorRecognizesFactoryAutomaticRollback(t *testing.T) {
	executable := filepath.Join(t.TempDir(), "fx")
	if err := os.WriteFile(executable, []byte("#!/bin/sh\nexit 6\n"), 0o700); err != nil {
		t.Fatal(err)
	}
	if status := (FXExecutor{Executable: executable}).Execute(context.Background(), "fx-factory-release", testSHA); status != "release_failed_rolled_back" {
		t.Fatalf("status=%q, want release_failed_rolled_back", status)
	}
}

func TestBrokerStatusDoesNotExposeExecutorOutput(t *testing.T) {
	executor := &recordingExecutor{}
	server := httptest.NewServer(New(executor).Handler())
	defer server.Close()
	body := `{"operation_id":"factory-rollback-1","adapter":"fx-factory-rollback","commit_sha":"` + testSHA + `"}`
	response, err := http.Post(server.URL+"/v1/operations", "application/json", strings.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	_ = response.Body.Close()
	var result Response
	for i := 0; i < 100; i++ {
		statusResponse, getErr := http.Get(server.URL + "/v1/operations/factory-rollback-1")
		if getErr != nil {
			t.Fatal(getErr)
		}
		if err := json.NewDecoder(statusResponse.Body).Decode(&result); err != nil {
			t.Fatal(err)
		}
		_ = statusResponse.Body.Close()
		if result.Status != "running" {
			break
		}
	}
	if result.Status != "succeeded" {
		t.Fatalf("status=%q", result.Status)
	}
}

func TestDiskBrokerKeepsImmutableOperationAcrossRestart(t *testing.T) {
	dir := t.TempDir()
	blocked := make(chan struct{})
	executor := &recordingExecutor{done: blocked}
	broker, err := NewAt(dir, executor)
	if err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(broker.Handler())
	defer server.Close()
	body := `{"operation_id":"delivery-1","adapter":"fx-factory-release","commit_sha":"` + testSHA + `"}`
	response, err := http.Post(server.URL+"/v1/operations", "application/json", strings.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	_ = response.Body.Close()
	if _, err := os.Stat(filepath.Join(dir, "delivery-1.json")); err != nil {
		t.Fatal(err)
	}
	// A restart cannot safely infer whether an old runner is still alive.  It
	// records failure rather than executing the release a second time.
	restarted, err := NewAt(dir, &recordingExecutor{})
	if err != nil {
		t.Fatal(err)
	}
	item := restarted.items["delivery-1"]
	if item == nil || item.Status != "failed" {
		t.Fatalf("recovered item=%+v", item)
	}
	close(blocked)
	for i := 0; i < 100 && broker.items["delivery-1"].Status != "succeeded"; i++ {
		time.Sleep(time.Millisecond)
	}
}

func TestDiskBrokerRejectsChangedDuplicateInput(t *testing.T) {
	dir := t.TempDir()
	broker, err := NewAt(dir, &recordingExecutor{done: make(chan struct{})})
	if err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(broker.Handler())
	defer server.Close()
	post := func(body string) int {
		response, err := http.Post(server.URL+"/v1/operations", "application/json", strings.NewReader(body))
		if err != nil {
			t.Fatal(err)
		}
		defer response.Body.Close()
		return response.StatusCode
	}
	body := `{"operation_id":"delivery-2","adapter":"fx-factory-release","commit_sha":"` + testSHA + `"}`
	if got := post(body); got != http.StatusAccepted {
		t.Fatalf("first=%d", got)
	}
	if got := post(`{"operation_id":"delivery-2","adapter":"fx-factory-rollback","commit_sha":"` + testSHA + `"}`); got != http.StatusConflict {
		t.Fatalf("changed=%d", got)
	}
}

func TestLockedOperationRetriesOnceButTerminalOperationDoesNot(t *testing.T) {
	executor := &sequenceExecutor{statuses: []string{"locked", "succeeded"}}
	broker := New(executor)
	server := httptest.NewServer(broker.Handler())
	defer server.Close()
	body := `{"operation_id":"lock-retry-1","adapter":"fx-factory-release","commit_sha":"` + testSHA + `"}`
	post := func() int {
		response, err := http.Post(server.URL+"/v1/operations", "application/json", strings.NewReader(body))
		if err != nil {
			t.Fatal(err)
		}
		defer response.Body.Close()
		return response.StatusCode
	}
	if got := post(); got != http.StatusAccepted {
		t.Fatalf("first=%d", got)
	}
	for i := 0; i < 100 && broker.items["lock-retry-1"].Status != "locked"; i++ {
		time.Sleep(time.Millisecond)
	}
	if got := post(); got != http.StatusAccepted {
		t.Fatalf("retry=%d", got)
	}
	for i := 0; i < 100 && broker.items["lock-retry-1"].Status != "succeeded"; i++ {
		time.Sleep(time.Millisecond)
	}
	if got := post(); got != http.StatusOK {
		t.Fatalf("terminal duplicate=%d", got)
	}
	executor.mu.Lock()
	defer executor.mu.Unlock()
	if executor.calls != 2 {
		t.Fatalf("physical executions=%d, want 2 (locked + retry)", executor.calls)
	}
}
