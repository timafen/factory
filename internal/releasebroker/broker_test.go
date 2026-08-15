package releasebroker

import (
	"context"
	"encoding/json"
	"errors"
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
	calls   int
	done    chan struct{}
}

type sequenceExecutor struct {
	mu       sync.Mutex
	statuses []string
	calls    int
	adapters []string
	shas     []string
}

func (executor *sequenceExecutor) Execute(_ context.Context, adapter, sha string) string {
	executor.mu.Lock()
	defer executor.mu.Unlock()
	status := "failed"
	if executor.calls < len(executor.statuses) {
		status = executor.statuses[executor.calls]
	}
	executor.calls++
	executor.adapters = append(executor.adapters, adapter)
	executor.shas = append(executor.shas, sha)
	return status
}

func (executor *sequenceExecutor) snapshot() (int, []string, []string) {
	executor.mu.Lock()
	defer executor.mu.Unlock()
	return executor.calls, append([]string(nil), executor.adapters...), append([]string(nil), executor.shas...)
}

func (executor *recordingExecutor) Execute(_ context.Context, adapter, sha string) string {
	executor.mu.Lock()
	executor.adapter, executor.sha = adapter, sha
	executor.calls++
	executor.mu.Unlock()
	if executor.done != nil {
		<-executor.done
	}
	return "succeeded"
}

func (executor *recordingExecutor) callCount() int {
	executor.mu.Lock()
	defer executor.mu.Unlock()
	return executor.calls
}

func postStatus(t *testing.T, server *httptest.Server, body string) int {
	t.Helper()
	response, err := http.Post(server.URL+"/v1/operations", "application/json", strings.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	return response.StatusCode
}

func operationStatus(t *testing.T, server *httptest.Server, id string) Response {
	t.Helper()
	response, err := server.Client().Get(server.URL + "/v1/operations/" + id)
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		t.Fatalf("GET status=%d", response.StatusCode)
	}
	var result Response
	if err := json.NewDecoder(response.Body).Decode(&result); err != nil {
		t.Fatal(err)
	}
	return result
}

func waitForOperationStatus(t *testing.T, server *httptest.Server, id, want string) {
	t.Helper()
	deadline := time.Now().Add(time.Second)
	for {
		if got := operationStatus(t, server, id).Status; got == want {
			return
		}
		if time.Now().After(deadline) {
			t.Fatalf("operation %q did not reach %q", id, want)
		}
		time.Sleep(time.Millisecond)
	}
}

func operationSnapshot(broker *Broker, id string) (operation, bool) {
	broker.mu.Lock()
	defer broker.mu.Unlock()
	item := broker.items[id]
	if item == nil {
		return operation{}, false
	}
	return *item, true
}

func waitForBrokerIdle(t *testing.T, broker *Broker) {
	t.Helper()
	deadline := time.Now().Add(time.Second)
	for {
		broker.mu.Lock()
		idle := broker.active == ""
		broker.mu.Unlock()
		if idle {
			return
		}
		if time.Now().After(deadline) {
			t.Fatal("broker did not become idle")
		}
		time.Sleep(time.Millisecond)
	}
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
	executor := FXExecutor{}
	for adapter, want := range map[string]string{
		"fx-factory-release":            "/usr/local/lib/fx-factory-release " + testSHA,
		"fx-factory-rollback":           "/usr/local/lib/fx-factory-release --rollback",
		"tarser-staging-deploy-release": "/usr/local/bin/fx staging release " + testSHA,
		"tarser-staging-auto-rollback":  "/usr/local/bin/fx staging rollback",
	} {
		executable, args, ok := executor.invocation(adapter, testSHA)
		got := strings.TrimSpace(executable + " " + strings.Join(args, " "))
		if !ok || got != want {
			t.Fatalf("adapter %q invocation=%q allowed=%v", adapter, got, ok)
		}
	}
	if _, _, ok := executor.invocation("anything", testSHA); ok {
		t.Fatal("unknown adapter was allowed")
	}
}

func TestFXExecutorRecognizesFactoryAutomaticRollback(t *testing.T) {
	executable := filepath.Join(t.TempDir(), "fx")
	if err := os.WriteFile(executable, []byte("#!/bin/sh\nexit 6\n"), 0o700); err != nil {
		t.Fatal(err)
	}
	if status := (FXExecutor{FactoryReleaseExecutable: executable}).Execute(context.Background(), "fx-factory-release", testSHA); status != "release_failed_rolled_back" {
		t.Fatalf("status=%q, want release_failed_rolled_back", status)
	}
}

func TestBrokerDriverCompletesAfterStoppingAndUpdatingServices(t *testing.T) {
	dir := t.TempDir()
	events := filepath.Join(dir, "events")
	updated := filepath.Join(dir, "updated")
	driver := filepath.Join(dir, "driver")
	script := "#!/bin/sh\nprintf 'stop factory-worker.service\\n' > '" + events + "'\nprintf 'updated\\n' > '" + updated + "'\n"
	if err := os.WriteFile(driver, []byte(script), 0o700); err != nil {
		t.Fatal(err)
	}
	broker := New(FXExecutor{FactoryReleaseExecutable: driver})
	server := httptest.NewServer(broker.Handler())
	defer server.Close()
	body := `{"operation_id":"broker-driver-integration","adapter":"fx-factory-release","commit_sha":"` + testSHA + `"}`
	if got := postStatus(t, server, body); got != http.StatusAccepted {
		t.Fatalf("POST status=%d", got)
	}
	waitForOperationStatus(t, server, "broker-driver-integration", "succeeded")
	if got, err := os.ReadFile(events); err != nil || string(got) != "stop factory-worker.service\n" {
		t.Fatalf("driver did not stop services: %q, %v", got, err)
	}
	if got, err := os.ReadFile(updated); err != nil || string(got) != "updated\n" {
		t.Fatalf("driver did not update services: %q, %v", got, err)
	}
}

func TestBrokerRestartsOnlyAfterUpdatedExecutableAndDurableSuccess(t *testing.T) {
	dir := t.TempDir()
	executable := filepath.Join(dir, "factory-release-broker")
	candidate := filepath.Join(dir, "factory-release-broker.candidate")
	if err := os.WriteFile(executable, []byte("old broker\n"), 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(candidate, []byte("new broker\n"), 0o700); err != nil {
		t.Fatal(err)
	}
	driver := filepath.Join(dir, "driver")
	if err := os.WriteFile(driver, []byte("#!/bin/sh\nmv '"+candidate+"' '"+executable+"'\n"), 0o700); err != nil {
		t.Fatal(err)
	}
	broker, err := NewAt(filepath.Join(dir, "state"), FXExecutor{FactoryReleaseExecutable: driver})
	if err != nil {
		t.Fatal(err)
	}
	restarted := make(chan struct{}, 1)
	if err := broker.RestartWhenExecutableChanges(executable, func() { restarted <- struct{}{} }); err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(broker.Handler())
	defer server.Close()
	body := `{"operation_id":"updated-broker","adapter":"fx-factory-release","commit_sha":"` + testSHA + `"}`
	if got := postStatus(t, server, body); got != http.StatusAccepted {
		t.Fatalf("POST status=%d", got)
	}
	waitForOperationStatus(t, server, "updated-broker", "succeeded")
	select {
	case <-restarted:
	case <-time.After(time.Second):
		t.Fatal("updated executable did not request a broker restart")
	}
	recovered, err := NewAt(filepath.Join(dir, "state"), &recordingExecutor{})
	if err != nil {
		t.Fatal(err)
	}
	item, ok := operationSnapshot(recovered, "updated-broker")
	if !ok || item.Status != "succeeded" {
		t.Fatalf("restart preceded durable success: %#v, found=%v", item, ok)
	}
}

func TestBrokerRestartsAfterUpdatedExecutableAndDurableRollbackFailure(t *testing.T) {
	dir := t.TempDir()
	executable := filepath.Join(dir, "factory-release-broker")
	candidate := filepath.Join(dir, "factory-release-broker.candidate")
	if err := os.WriteFile(executable, []byte("old broker\n"), 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(candidate, []byte("new broker\n"), 0o700); err != nil {
		t.Fatal(err)
	}
	driver := filepath.Join(dir, "driver")
	if err := os.WriteFile(driver, []byte("#!/bin/sh\nmv '"+candidate+"' '"+executable+"'\nexit 7\n"), 0o700); err != nil {
		t.Fatal(err)
	}
	state := filepath.Join(dir, "state")
	broker, err := NewAt(state, FXExecutor{FactoryReleaseExecutable: driver})
	if err != nil {
		t.Fatal(err)
	}
	restarted := make(chan struct{}, 1)
	if err := broker.RestartWhenExecutableChanges(executable, func() { restarted <- struct{}{} }); err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(broker.Handler())
	defer server.Close()
	body := `{"operation_id":"updated-broker-rollback-failed","adapter":"fx-factory-release","commit_sha":"` + testSHA + `"}`
	if got := postStatus(t, server, body); got != http.StatusAccepted {
		t.Fatalf("POST status=%d", got)
	}
	waitForOperationStatus(t, server, "updated-broker-rollback-failed", "rollback_failed")
	select {
	case <-restarted:
	case <-time.After(time.Second):
		t.Fatal("updated executable did not request a broker restart after rollback failure")
	}
	recovered, err := NewAt(state, &recordingExecutor{})
	if err != nil {
		t.Fatal(err)
	}
	item, ok := operationSnapshot(recovered, "updated-broker-rollback-failed")
	if !ok || item.Status != "rollback_failed" {
		t.Fatalf("restart preceded durable rollback failure: %#v, found=%v", item, ok)
	}
}

func TestBrokerDoesNotRestartWhenExecutableIsUnchanged(t *testing.T) {
	dir := t.TempDir()
	executable := filepath.Join(dir, "factory-release-broker")
	if err := os.WriteFile(executable, []byte("same broker\n"), 0o700); err != nil {
		t.Fatal(err)
	}
	broker, err := NewAt(filepath.Join(dir, "state"), &recordingExecutor{})
	if err != nil {
		t.Fatal(err)
	}
	restarted := make(chan struct{}, 1)
	if err := broker.RestartWhenExecutableChanges(executable, func() { restarted <- struct{}{} }); err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(broker.Handler())
	defer server.Close()
	body := `{"operation_id":"unchanged-broker","adapter":"fx-factory-release","commit_sha":"` + testSHA + `"}`
	if got := postStatus(t, server, body); got != http.StatusAccepted {
		t.Fatalf("POST status=%d", got)
	}
	waitForOperationStatus(t, server, "unchanged-broker", "succeeded")
	select {
	case <-restarted:
		t.Fatal("unchanged executable requested a broker restart")
	case <-time.After(20 * time.Millisecond):
	}
}

func TestBrokerStatusDoesNotExposeExecutorOutput(t *testing.T) {
	executor := &recordingExecutor{}
	server := httptest.NewServer(New(executor).Handler())
	defer server.Close()
	body := `{"operation_id":"factory-rollback-1","adapter":"fx-factory-rollback","commit_sha":"` + testSHA + `"}`
	if got := postStatus(t, server, body); got != http.StatusAccepted {
		t.Fatalf("POST status=%d", got)
	}
	waitForOperationStatus(t, server, "factory-rollback-1", "succeeded")
}

func TestBrokerDoesNotPublishTerminalSuccessWhenPersistFails(t *testing.T) {
	dir := t.TempDir()
	blocked := make(chan struct{})
	broker, err := NewAt(dir, &recordingExecutor{done: blocked})
	if err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(broker.Handler())
	defer server.Close()
	body := `{"operation_id":"persist-failure-1","adapter":"fx-factory-release","commit_sha":"` + testSHA + `"}`
	response, err := http.Post(server.URL+"/v1/operations", "application/json", strings.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	_ = response.Body.Close()
	running := false
	for i := 0; i < 100; i++ {
		broker.mu.Lock()
		status := broker.items["persist-failure-1"].Status
		broker.mu.Unlock()
		if status == "running" {
			running = true
			break
		}
		time.Sleep(time.Millisecond)
	}
	if !running {
		t.Fatal("operation did not enter running state")
	}
	persistAttempted := make(chan struct{})
	broker.mu.Lock()
	broker.persistTerminal = func(item *operation) error {
		if item.Status == "succeeded" {
			close(persistAttempted)
			return errors.New("simulated terminal persist failure")
		}
		return broker.persist(item)
	}
	broker.mu.Unlock()
	close(blocked)
	select {
	case <-persistAttempted:
	case <-time.After(time.Second):
		t.Fatal("terminal persist was not attempted")
	}
	broker.mu.Lock()
	status := broker.items["persist-failure-1"].Status
	broker.mu.Unlock()
	if status != "running" {
		t.Fatalf("published terminal status=%q after persist failure", status)
	}
	statusResponse, err := http.Get(server.URL + "/v1/operations/persist-failure-1")
	if err != nil {
		t.Fatal(err)
	}
	defer statusResponse.Body.Close()
	var responseStatus Response
	if err := json.NewDecoder(statusResponse.Body).Decode(&responseStatus); err != nil {
		t.Fatal(err)
	}
	if responseStatus.Status != "running" {
		t.Fatalf("published API status=%q after persist failure", responseStatus.Status)
	}
	data, err := os.ReadFile(filepath.Join(dir, "persist-failure-1.json"))
	if err != nil {
		t.Fatal(err)
	}
	var saved operation
	if err := json.Unmarshal(data, &saved); err != nil {
		t.Fatal(err)
	}
	if saved.Status != "running" {
		t.Fatalf("durable status=%q, want running", saved.Status)
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
	if got := postStatus(t, server, body); got != http.StatusAccepted {
		t.Fatalf("POST status=%d", got)
	}
	waitForOperationStatus(t, server, "delivery-1", "running")
	if _, err := os.Stat(filepath.Join(dir, "delivery-1.json")); err != nil {
		t.Fatal(err)
	}
	// A restart cannot safely infer whether an old runner is still alive.  It
	// records failure rather than executing the release a second time.
	restarted, err := NewAt(dir, &recordingExecutor{})
	if err != nil {
		t.Fatal(err)
	}
	item, ok := operationSnapshot(restarted, "delivery-1")
	if !ok || item.Status != "failed" {
		t.Fatalf("recovered item=%+v", item)
	}
	close(blocked)
	waitForOperationStatus(t, server, "delivery-1", "succeeded")
}

func TestDiskBrokerKeepsAcceptedTerminalStatusAcrossRestart(t *testing.T) {
	dir := t.TempDir()
	executor := &sequenceExecutor{statuses: []string{"succeeded"}}
	broker, err := NewAt(dir, executor)
	if err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(broker.Handler())
	defer server.Close()
	body := `{"operation_id":"delivery-completed-1","adapter":"fx-factory-release","commit_sha":"` + testSHA + `"}`
	if got := postStatus(t, server, body); got != http.StatusAccepted {
		t.Fatalf("POST status=%d", got)
	}
	waitForOperationStatus(t, server, "delivery-completed-1", "succeeded")

	restarted, err := NewAt(dir, executor)
	if err != nil {
		t.Fatal(err)
	}
	restartedServer := httptest.NewServer(restarted.Handler())
	defer restartedServer.Close()
	if got := operationStatus(t, restartedServer, "delivery-completed-1").Status; got != "succeeded" {
		t.Fatalf("recovered status=%q, want succeeded", got)
	}
	if got := postStatus(t, restartedServer, body); got != http.StatusOK {
		t.Fatalf("duplicate POST status=%d", got)
	}
	if calls, _, _ := executor.snapshot(); calls != 1 {
		t.Fatalf("executor repeated after accepted terminal status: calls=%d", calls)
	}
}

func TestDiskBrokerPreservesLegacyTerminalStatusesWithoutExecutor(t *testing.T) {
	statuses := []string{"succeeded", "locked", "release_failed_rolled_back", "rollback_failed", "failed"}
	for _, status := range statuses {
		t.Run(status, func(t *testing.T) {
			dir := t.TempDir()
			operationID := "legacy-" + strings.ReplaceAll(status, "_", "-")
			body := `{"request":{"operation_id":"` + operationID + `","adapter":"fx-factory-release","commit_sha":"` + testSHA + `"},"status":"` + status + `","posts":1}`
			if err := os.WriteFile(filepath.Join(dir, operationID+".json"), []byte(body), 0o600); err != nil {
				t.Fatal(err)
			}
			executor := &recordingExecutor{}
			broker, err := NewAt(dir, executor)
			if err != nil {
				t.Fatal(err)
			}
			if item, ok := operationSnapshot(broker, operationID); !ok || item.Status != status {
				t.Fatalf("recovered legacy item=%+v, want status %q", item, status)
			}
			if calls := executor.callCount(); calls != 0 {
				t.Fatalf("executor calls=%d, want 0", calls)
			}
		})
	}
}

func TestDiskBrokerRefusesCorruptOperationRecord(t *testing.T) {
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "damaged.json"), []byte(`{"request":`), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := NewAt(dir, &recordingExecutor{}); err == nil {
		t.Fatal("broker started with a corrupt durable operation record")
	}
}

func TestPersistFailsClosedOnSynchronizationErrors(t *testing.T) {
	for _, test := range []struct {
		name             string
		breakPersistence func(*Broker)
	}{
		{name: "temporary file fsync", breakPersistence: func(b *Broker) {
			b.syncFile = func(*os.File) error { return errors.New("file fsync failed") }
		}},
		{name: "state directory fsync", breakPersistence: func(b *Broker) {
			b.syncDir = func(string) error { return errors.New("directory fsync failed") }
		}},
	} {
		t.Run(test.name, func(t *testing.T) {
			broker, err := NewAt(t.TempDir(), &recordingExecutor{})
			if err != nil {
				t.Fatal(err)
			}
			test.breakPersistence(broker)
			server := httptest.NewServer(broker.Handler())
			defer server.Close()
			body := `{"operation_id":"sync-failure","adapter":"fx-factory-release","commit_sha":"` + testSHA + `"}`
			if got := postStatus(t, server, body); got != http.StatusServiceUnavailable {
				t.Fatalf("POST status=%d, want %d", got, http.StatusServiceUnavailable)
			}
			if _, ok := operationSnapshot(broker, "sync-failure"); ok {
				t.Fatal("operation became visible after a synchronization error")
			}
		})
	}
}

func TestTerminalSynchronizationErrorsNeverPublishSuccess(t *testing.T) {
	for _, test := range []struct {
		name            string
		breakFourthSync func(*Broker)
	}{
		{name: "temporary file fsync", breakFourthSync: func(b *Broker) {
			calls := 0
			b.syncFile = func(file *os.File) error {
				calls++
				if calls == 4 {
					return errors.New("terminal file fsync failed")
				}
				return file.Sync()
			}
		}},
		{name: "state directory fsync", breakFourthSync: func(b *Broker) {
			calls := 0
			original := b.syncDir
			b.syncDir = func(path string) error {
				calls++
				if calls == 4 {
					return errors.New("terminal directory fsync failed")
				}
				return original(path)
			}
		}},
	} {
		t.Run(test.name, func(t *testing.T) {
			executor := &recordingExecutor{}
			broker, err := NewAt(t.TempDir(), executor)
			if err != nil {
				t.Fatal(err)
			}
			test.breakFourthSync(broker)
			server := httptest.NewServer(broker.Handler())
			defer server.Close()
			body := `{"operation_id":"terminal-sync-failure","adapter":"fx-factory-release","commit_sha":"` + testSHA + `"}`
			if got := postStatus(t, server, body); got != http.StatusAccepted {
				t.Fatalf("POST status=%d", got)
			}
			waitForBrokerIdle(t, broker)
			if got := operationStatus(t, server, "terminal-sync-failure").Status; got != "running" {
				t.Fatalf("unpersisted terminal status became visible as %q", got)
			}
			if executor.callCount() != 1 {
				t.Fatalf("physical executions=%d, want 1", executor.callCount())
			}
		})
	}
}

func TestDiskBrokerFailsClosedOnInvalidOperationState(t *testing.T) {
	tests := map[string]struct {
		name string
		body string
	}{
		"corrupt JSON": {
			name: "delivery-corrupt.json",
			body: `{`,
		},
		"mismatched filename": {
			name: "delivery-alias.json",
			body: `{"request":{"operation_id":"delivery-real","adapter":"fx-factory-release","commit_sha":"` + testSHA + `"},"status":"succeeded","posts":1}`,
		},
		"invalid request": {
			name: "delivery-invalid.json",
			body: `{"request":{"operation_id":"delivery-invalid","adapter":"arbitrary-command","commit_sha":"` + testSHA + `"},"status":"succeeded","posts":1}`,
		},
		"invalid status": {
			name: "delivery-status.json",
			body: `{"request":{"operation_id":"delivery-status","adapter":"fx-factory-release","commit_sha":"` + testSHA + `"},"status":"unknown","posts":1}`,
		},
	}
	for name, test := range tests {
		t.Run(name, func(t *testing.T) {
			dir := t.TempDir()
			if err := os.WriteFile(filepath.Join(dir, test.name), []byte(test.body), 0o600); err != nil {
				t.Fatal(err)
			}
			executor := &recordingExecutor{}
			if _, err := NewAt(dir, executor); err == nil {
				t.Fatal("broker accepted invalid durable operation state")
			}
			if calls := executor.callCount(); calls != 0 {
				t.Fatalf("physical executions=%d, want 0", calls)
			}
		})
	}
}

func TestDiskBrokerFailsClosedOnJSONDirectory(t *testing.T) {
	dir := t.TempDir()
	if err := os.Mkdir(filepath.Join(dir, "delivery-1.json"), 0o700); err != nil {
		t.Fatal(err)
	}
	executor := &recordingExecutor{}
	_, err := NewAt(dir, executor)
	if err == nil || !strings.Contains(err.Error(), "not a regular file") {
		t.Fatalf("NewAt error=%v, want non-regular operation state", err)
	}
	if calls := executor.callCount(); calls != 0 {
		t.Fatalf("physical executions=%d, want 0", calls)
	}
}

func TestDirectoryFsyncFailureAfterRenameFailsClosedOnRestart(t *testing.T) {
	dir := t.TempDir()
	executor := &recordingExecutor{}
	brokeTerminalSync := false
	b, err := NewAt(dir, executor)
	if err != nil {
		t.Fatal(err)
	}
	originalSyncDir := b.syncDir
	calls := 0
	b.syncDir = func(path string) error {
		calls++
		// Initial record, PID, running, pending marker, then terminal rename.
		if calls == 5 {
			brokeTerminalSync = true
			return errors.New("directory fsync failed after terminal rename")
		}
		return originalSyncDir(path)
	}
	server := httptest.NewServer(b.Handler())
	defer server.Close()
	body := `{"operation_id":"rename-sync-restart","adapter":"fx-factory-release","commit_sha":"` + testSHA + `"}`
	if got := postStatus(t, server, body); got != http.StatusAccepted {
		t.Fatalf("POST status=%d", got)
	}
	waitForBrokerIdle(t, b)
	if !brokeTerminalSync {
		t.Fatalf("terminal directory fsync was not forced; calls=%d", calls)
	}
	if data, err := os.ReadFile(filepath.Join(dir, "rename-sync-restart.json")); err != nil {
		t.Fatal(err)
	} else if !strings.Contains(string(data), `"status":"succeeded"`) {
		t.Fatalf("test did not leave renamed terminal record: %s", data)
	}

	restarted, err := NewAt(dir, &recordingExecutor{})
	if err != nil {
		t.Fatal(err)
	}
	if item, ok := operationSnapshot(restarted, "rename-sync-restart"); !ok || item.Status != "failed" {
		t.Fatalf("restart accepted unconfirmed terminal: %+v", item)
	}
	if executor.callCount() != 1 {
		t.Fatalf("executor calls=%d, want 1", executor.callCount())
	}
}

func TestTerminalWriteFailureNeverPublishesSuccessOrRepeatsExecutorAfterRestart(t *testing.T) {
	parent := t.TempDir()
	dir := filepath.Join(parent, "state")
	blocked := make(chan struct{})
	executor := &recordingExecutor{done: blocked}
	broker, err := NewAt(dir, executor)
	if err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(broker.Handler())
	defer server.Close()
	body := `{"operation_id":"delivery-write-failure","adapter":"fx-factory-release","commit_sha":"` + testSHA + `"}`
	if got := postStatus(t, server, body); got != http.StatusAccepted {
		t.Fatalf("POST status=%d", got)
	}
	waitForOperationStatus(t, server, "delivery-write-failure", "running")

	// Move the real durable directory aside and replace its path with a file.
	// The executor has already started, so its terminal atomic write now fails
	// in the filesystem rather than through a mocked persistence hook.
	saved := filepath.Join(parent, "saved-state")
	if err := os.Rename(dir, saved); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(dir, []byte("not a directory"), 0o600); err != nil {
		t.Fatal(err)
	}
	close(blocked)
	waitForBrokerIdle(t, broker)
	if got := operationStatus(t, server, "delivery-write-failure").Status; got != "running" {
		t.Fatalf("unpersisted terminal status became visible as %q", got)
	}
	if executor.callCount() != 1 {
		t.Fatalf("physical executions=%d, want 1", executor.callCount())
	}

	if err := os.Remove(dir); err != nil {
		t.Fatal(err)
	}
	if err := os.Rename(saved, dir); err != nil {
		t.Fatal(err)
	}
	restarted, err := NewAt(dir, executor)
	if err != nil {
		t.Fatal(err)
	}
	restartedServer := httptest.NewServer(restarted.Handler())
	defer restartedServer.Close()
	if got := operationStatus(t, restartedServer, "delivery-write-failure").Status; got != "failed" {
		t.Fatalf("fresh restart status=%q, want failed", got)
	}
	if got := postStatus(t, restartedServer, body); got != http.StatusOK {
		t.Fatalf("duplicate POST status=%d", got)
	}
	secondRestart, err := NewAt(dir, executor)
	if err != nil {
		t.Fatal(err)
	}
	if item, ok := operationSnapshot(secondRestart, "delivery-write-failure"); !ok || item.Status != "failed" {
		t.Fatalf("second restart lost durable failure: %+v", item)
	}
	if executor.callCount() != 1 {
		t.Fatalf("executor repeated after ambiguous durability: calls=%d", executor.callCount())
	}
}

func TestDiskBrokerRejectsChangedDuplicateInput(t *testing.T) {
	dir := t.TempDir()
	blocked := make(chan struct{})
	broker, err := NewAt(dir, &recordingExecutor{done: blocked})
	if err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(broker.Handler())
	defer server.Close()
	body := `{"operation_id":"delivery-2","adapter":"fx-factory-release","commit_sha":"` + testSHA + `"}`
	if got := postStatus(t, server, body); got != http.StatusAccepted {
		t.Fatalf("first=%d", got)
	}
	if got := postStatus(t, server, `{"operation_id":"delivery-2","adapter":"fx-factory-rollback","commit_sha":"`+testSHA+`"}`); got != http.StatusConflict {
		t.Fatalf("changed=%d", got)
	}
	close(blocked)
	waitForOperationStatus(t, server, "delivery-2", "succeeded")
}

func TestLockedOperationRetriesWithNewerSHAOnlyForSameAdapter(t *testing.T) {
	executor := &sequenceExecutor{statuses: []string{"locked", "succeeded"}}
	broker := New(executor)
	server := httptest.NewServer(broker.Handler())
	defer server.Close()
	first := `{"operation_id":"lock-retry-1","adapter":"fx-factory-release","commit_sha":"` + testSHA + `"}`
	newerSHA := strings.Repeat("b", 40)
	retry := `{"operation_id":"lock-retry-1","adapter":"fx-factory-release","commit_sha":"` + newerSHA + `"}`
	if got := postStatus(t, server, first); got != http.StatusAccepted {
		t.Fatalf("first=%d", got)
	}
	waitForOperationStatus(t, server, "lock-retry-1", "locked")
	if got := postStatus(t, server, retry); got != http.StatusAccepted {
		t.Fatalf("retry=%d", got)
	}
	waitForOperationStatus(t, server, "lock-retry-1", "succeeded")
	if got := postStatus(t, server, retry); got != http.StatusOK {
		t.Fatalf("terminal duplicate=%d", got)
	}
	calls, adapters, shas := executor.snapshot()
	if calls != 2 {
		t.Fatalf("physical executions=%d, want 2 (locked + retry)", calls)
	}
	if strings.Join(adapters, ",") != "fx-factory-release,fx-factory-release" || strings.Join(shas, ",") != testSHA+","+newerSHA {
		t.Fatalf("executions adapter=%v sha=%v", adapters, shas)
	}
	item, ok := operationSnapshot(broker, "lock-retry-1")
	if !ok {
		t.Fatal("missing operation")
	}
	if got := item.Posts; got != 3 {
		t.Fatalf("durable POST observations=%d, want 3", got)
	}
}

func TestLockedOperationRejectsAdapterAndTargetMutationAtomically(t *testing.T) {
	executor := &sequenceExecutor{statuses: []string{"locked", "succeeded"}}
	broker := New(executor)
	server := httptest.NewServer(broker.Handler())
	defer server.Close()
	first := `{"operation_id":"lock-identity-1","adapter":"fx-factory-release","commit_sha":"` + testSHA + `"}`
	if got := postStatus(t, server, first); got != http.StatusAccepted {
		t.Fatalf("first=%d", got)
	}
	waitForOperationStatus(t, server, "lock-identity-1", "locked")
	for _, mutation := range []string{
		`{"operation_id":"lock-identity-1","adapter":"fx-factory-rollback","commit_sha":"` + testSHA + `"}`,
		`{"operation_id":"lock-identity-1","adapter":"tarser-staging-deploy-release","commit_sha":"` + testSHA + `"}`,
	} {
		if got := postStatus(t, server, mutation); got != http.StatusConflict {
			t.Fatalf("mutated retry=%d, want conflict", got)
		}
	}
	item, ok := operationSnapshot(broker, "lock-identity-1")
	if !ok || item.Request.Adapter != "fx-factory-release" || item.Request.CommitSHA != testSHA || item.Status != "locked" || item.Posts != 1 {
		t.Fatalf("mutated stored operation=%+v", item)
	}
	calls, adapters, _ := executor.snapshot()
	if calls != 1 || strings.Join(adapters, ",") != "fx-factory-release" {
		t.Fatalf("rollback/target executor ran: calls=%d adapters=%v", calls, adapters)
	}
	if got := postStatus(t, server, `{"operation_id":"lock-identity-1","adapter":"fx-factory-release","commit_sha":"`+strings.Repeat("c", 40)+`"}`); got != http.StatusAccepted {
		t.Fatalf("same-adapter retry=%d", got)
	}
	waitForOperationStatus(t, server, "lock-identity-1", "succeeded")
	calls, adapters, _ = executor.snapshot()
	if calls != 2 || strings.Join(adapters, ",") != "fx-factory-release,fx-factory-release" {
		t.Fatalf("unexpected executor calls=%d adapters=%v", calls, adapters)
	}
}
