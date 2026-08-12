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
	"syscall"
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

func secureTestDirectory(t *testing.T, path string) {
	t.Helper()
	if err := os.Chmod(path, 0o700); err != nil {
		t.Fatal(err)
	}
}

func writeTestExecutable(t *testing.T, path, body string) {
	t.Helper()
	if err := os.WriteFile(path, []byte("#!/bin/sh\nset -eu\n"+body), 0o700); err != nil {
		t.Fatal(err)
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
	if got := postStatus(t, server, body); got != http.StatusAccepted {
		t.Fatalf("POST status=%d", got)
	}
	waitForOperationStatus(t, server, "factory-rollback-1", "succeeded")
}

func TestDiskBrokerKeepsImmutableOperationAcrossRestart(t *testing.T) {
	dir := t.TempDir()
	secureTestDirectory(t, dir)
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

func TestTerminalWriteFailureNeverPublishesSuccessOrRepeatsExecutorAfterRestart(t *testing.T) {
	parent := t.TempDir()
	dir := filepath.Join(parent, "state")
	if err := os.Mkdir(dir, 0o700); err != nil {
		t.Fatal(err)
	}
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
	if executor.callCount() != 1 {
		t.Fatalf("executor repeated after ambiguous durability: calls=%d", executor.callCount())
	}
}

func TestTerminalSyncFailuresStayFailClosedAcrossRestart(t *testing.T) {
	for _, test := range []struct {
		name string
		fail func(*Broker)
	}{
		{name: "file sync", fail: func(b *Broker) {
			original := b.syncFile
			failed := false
			b.syncFile = func(file *os.File) error {
				if !failed {
					failed = true
					return errors.New("injected file sync failure")
				}
				return original(file)
			}
		}},
		{name: "file close", fail: func(b *Broker) {
			original := b.closeFile
			failed := false
			b.closeFile = func(file *os.File) error {
				err := original(file)
				if !failed {
					failed = true
					return errors.Join(err, errors.New("injected file close failure"))
				}
				return err
			}
		}},
		{name: "rename", fail: func(b *Broker) {
			original := b.renameFile
			failed := false
			b.renameFile = func(oldPath, newPath string) error {
				if !failed {
					failed = true
					return errors.New("injected rename failure")
				}
				return original(oldPath, newPath)
			}
		}},
		{name: "directory sync", fail: func(b *Broker) {
			original := b.syncDir
			failed := false
			b.syncDir = func(path string) error {
				if !failed {
					failed = true
					return errors.New("injected directory sync failure")
				}
				return original(path)
			}
		}},
	} {
		t.Run(test.name, func(t *testing.T) {
			dir := t.TempDir()
			secureTestDirectory(t, dir)
			blocked := make(chan struct{})
			executor := &recordingExecutor{done: blocked}
			broker, err := NewAt(dir, executor)
			if err != nil {
				t.Fatal(err)
			}
			server := httptest.NewServer(broker.Handler())
			defer server.Close()
			body := `{"operation_id":"delivery-sync-failure","adapter":"fx-factory-release","commit_sha":"` + testSHA + `"}`
			if got := postStatus(t, server, body); got != http.StatusAccepted {
				t.Fatalf("POST status=%d", got)
			}
			waitForOperationStatus(t, server, "delivery-sync-failure", "running")
			test.fail(broker)
			close(blocked)
			waitForBrokerIdle(t, broker)
			if got := operationStatus(t, server, "delivery-sync-failure").Status; got != "running" {
				t.Fatalf("unconfirmed terminal status became visible as %q", got)
			}

			var stored operation
			data, err := os.ReadFile(filepath.Join(dir, "delivery-sync-failure.json"))
			if err != nil || json.Unmarshal(data, &stored) != nil || stored.Status != "running" {
				t.Fatalf("record after failed sync: item=%+v read_error=%v", stored, err)
			}
			restarted, err := NewAt(dir, executor)
			if err != nil {
				t.Fatal(err)
			}
			restartedServer := httptest.NewServer(restarted.Handler())
			defer restartedServer.Close()
			if got := operationStatus(t, restartedServer, "delivery-sync-failure").Status; got != "failed" {
				t.Fatalf("fresh restart status=%q, want failed", got)
			}
			if got := postStatus(t, restartedServer, body); got != http.StatusOK {
				t.Fatalf("duplicate POST status=%d", got)
			}
			if calls := executor.callCount(); calls != 1 {
				t.Fatalf("executor calls=%d, want 1", calls)
			}
		})
	}
}

func TestDiskBrokerRejectsChangedDuplicateInput(t *testing.T) {
	dir := t.TempDir()
	secureTestDirectory(t, dir)
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

func TestDiskBrokerRejectsHostilePreseededStatusAndPermissions(t *testing.T) {
	for _, test := range []struct {
		name  string
		setup func(*testing.T, string)
	}{
		{name: "writable state root", setup: func(t *testing.T, dir string) {
			if err := os.Chmod(dir, 0o755); err != nil {
				t.Fatal(err)
			}
		}},
		{name: "preseeded operation status", setup: func(t *testing.T, dir string) {
			secureTestDirectory(t, dir)
			body := `{"request":{"operation_id":"hostile-1","adapter":"fx-factory-release","commit_sha":"` + testSHA + `"},"status":"succeeded","posts":1}`
			path := filepath.Join(dir, "hostile-1.json")
			if err := os.WriteFile(path, []byte(body), 0o644); err != nil {
				t.Fatal(err)
			}
			if err := os.Chmod(path, 0o644); err != nil {
				t.Fatal(err)
			}
		}},
	} {
		t.Run(test.name, func(t *testing.T) {
			dir := t.TempDir()
			test.setup(t, dir)
			executor := &recordingExecutor{}
			if _, err := NewAt(dir, executor); err == nil {
				t.Fatal("hostile durable state was accepted")
			}
			if executor.callCount() != 0 {
				t.Fatalf("hostile state reached executor: calls=%d", executor.callCount())
			}
		})
	}
}

func TestFXExecutorLaunchGatePersistsRunningBeforeDriverLock(t *testing.T) {
	dir := t.TempDir()
	secureTestDirectory(t, dir)
	lockCounter := filepath.Join(t.TempDir(), "lock-count")
	fx := filepath.Join(t.TempDir(), "fx")
	writeTestExecutable(t, fx, `
printf 'lock\n' >>"`+lockCounter+`"
umask 077
printf 'succeeded\n' >"$FACTORY_DELIVERY_STATE_DIR/$FACTORY_DELIVERY_ID.status"
`)
	broker, err := NewAt(dir, FXExecutor{Executable: fx})
	if err != nil {
		t.Fatal(err)
	}
	originalSync := broker.syncFile
	pidPersisted := make(chan struct{})
	allowRunning := make(chan struct{})
	var syncCalls int
	broker.syncFile = func(file *os.File) error {
		syncCalls++
		if syncCalls == 2 { // initial launching is first; PID persistence is second.
			close(pidPersisted)
			<-allowRunning
		}
		return originalSync(file)
	}
	server := httptest.NewServer(broker.Handler())
	defer server.Close()
	body := `{"operation_id":"gated-lock-1","adapter":"fx-factory-release","commit_sha":"` + testSHA + `"}`
	if got := postStatus(t, server, body); got != http.StatusAccepted {
		t.Fatalf("POST status=%d", got)
	}
	select {
	case <-pidPersisted:
	case <-time.After(time.Second):
		t.Fatal("PID persistence did not reach its durable boundary")
	}
	if _, err := os.Stat(lockCounter); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("driver reached release lock before running was durable: %v", err)
	}
	close(allowRunning)
	waitForOperationStatus(t, server, "gated-lock-1", "succeeded")
	data, err := os.ReadFile(lockCounter)
	if err != nil || strings.Count(string(data), "lock\n") != 1 {
		t.Fatalf("physical lock entries=%q read_error=%v", data, err)
	}
}

func TestFXExecutorKillsLaunchGroupWhenPIDOrRunningPersistenceFails(t *testing.T) {
	for _, phase := range []string{"pid", "running"} {
		t.Run(phase, func(t *testing.T) {
			dir := t.TempDir()
			secureTestDirectory(t, dir)
			lockCounter := filepath.Join(t.TempDir(), "lock-count")
			fx := filepath.Join(t.TempDir(), "fx")
			writeTestExecutable(t, fx, `printf 'lock\n' >>"`+lockCounter+`"`)
			broker, err := NewAt(dir, FXExecutor{Executable: fx})
			if err != nil {
				t.Fatal(err)
			}
			originalSync := broker.syncFile
			var syncCalls int
			broker.syncFile = func(file *os.File) error {
				syncCalls++
				failAt := 2 // initial launching is first, then durable PID.
				if phase == "running" {
					failAt = 3
				}
				if syncCalls == failAt {
					return errors.New("injected " + phase + " persistence failure")
				}
				return originalSync(file)
			}
			server := httptest.NewServer(broker.Handler())
			defer server.Close()
			body := `{"operation_id":"gate-failure-` + phase + `","adapter":"fx-factory-release","commit_sha":"` + testSHA + `"}`
			if got := postStatus(t, server, body); got != http.StatusAccepted {
				t.Fatalf("POST status=%d", got)
			}
			waitForBrokerIdle(t, broker)
			if _, err := os.Stat(lockCounter); !errors.Is(err, os.ErrNotExist) {
				t.Fatalf("failed %s persistence reached the driver lock: %v", phase, err)
			}
			item, ok := operationSnapshot(broker, "gate-failure-"+phase)
			if !ok {
				t.Fatalf("missing operation after %s failure", phase)
			}
			if phase == "pid" {
				if item.PID != 0 {
					t.Fatalf("failed PID write became visible: %+v", item)
				}
				return
			}
			if item.PID <= 0 {
				t.Fatalf("missing persisted PID before running failure: %+v", item)
			}
			deadline := time.Now().Add(time.Second)
			for err := syscall.Kill(item.PID, 0); !errors.Is(err, syscall.ESRCH); err = syscall.Kill(item.PID, 0) {
				if time.Now().After(deadline) {
					t.Fatalf("launch process group leader survived %s persistence failure: %v", phase, err)
				}
				time.Sleep(time.Millisecond)
			}
		})
	}
}

func TestTarserAndUnconfirmedDriverTerminalsFailClosed(t *testing.T) {
	for _, adapter := range []string{"tarser-staging-deploy-release", "fx-factory-release"} {
		t.Run(adapter, func(t *testing.T) {
			dir := t.TempDir()
			secureTestDirectory(t, dir)
			fx := filepath.Join(t.TempDir(), "fx")
			body := "exit 0\n"
			if adapter == "fx-factory-release" {
				// A driver that has only reached running and then loses its
				// terminal write must not let rc=6 publish rollback success.
				body = `umask 077
printf 'running\n' >"$FACTORY_DELIVERY_STATE_DIR/$FACTORY_DELIVERY_ID.status"
exit 6
`
			}
			writeTestExecutable(t, fx, body)
			broker, err := NewAt(dir, FXExecutor{Executable: fx})
			if err != nil {
				t.Fatal(err)
			}
			server := httptest.NewServer(broker.Handler())
			defer server.Close()
			id := "unconfirmed-" + strings.ReplaceAll(adapter, "_", "-")
			bodyJSON := `{"operation_id":"` + id + `","adapter":"` + adapter + `","commit_sha":"` + testSHA + `"}`
			if got := postStatus(t, server, bodyJSON); got != http.StatusAccepted {
				t.Fatalf("POST status=%d", got)
			}
			waitForBrokerIdle(t, broker)
			if got := operationStatus(t, server, id).Status; got != "running" {
				t.Fatalf("unproven %s terminal was published as %q", adapter, got)
			}
			restarted, err := NewAt(dir, FXExecutor{Executable: fx})
			if err != nil {
				t.Fatal(err)
			}
			restartedServer := httptest.NewServer(restarted.Handler())
			defer restartedServer.Close()
			if got := operationStatus(t, restartedServer, id).Status; got != "failed" {
				t.Fatalf("fresh broker status=%q, want failed", got)
			}
		})
	}
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
