// Package releasebroker owns the privileged, idempotent release boundary.
package releasebroker

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sync"
)

const MaxBodyBytes = 64 << 10

var (
	operationIDPattern = regexp.MustCompile(`^[a-z0-9][a-z0-9-]{0,127}$`)
	commitSHAPattern   = regexp.MustCompile(`^[0-9a-f]{40}([0-9a-f]{24})?$`)
)

type Request struct {
	OperationID string `json:"operation_id"`
	Adapter     string `json:"adapter"`
	CommitSHA   string `json:"commit_sha"`
}

// Response intentionally contains no runner output: a release log can contain
// credentials.  Status is the authoritative durable delivery proof.
type Response struct {
	Status string `json:"status"`
}

type Executor interface {
	Execute(context.Context, string, string) string
}

// DeliveryExecutor is implemented by executors which can propagate the
// immutable operation key to a generation-aware release driver.
type DeliveryExecutor interface {
	ExecuteDelivery(context.Context, string, string, string) string
}

type FXExecutor struct{ Executable string }

func (e FXExecutor) Execute(ctx context.Context, adapter, sha string) string {
	return e.ExecuteDelivery(ctx, adapter, sha, "")
}

func (e FXExecutor) ExecuteDelivery(ctx context.Context, adapter, sha, operationID string) string {
	executable := e.Executable
	if executable == "" {
		executable = "/usr/local/bin/fx"
	}
	args, ok := invocation(adapter, sha)
	if !ok {
		return "failed"
	}
	command := exec.CommandContext(ctx, executable, args...)
	command.Env = []string{
		"LANG=C.UTF-8", "LC_ALL=C.UTF-8",
		"PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
		"FACTORY_DELIVERY_ID=" + operationID,
	}
	err := command.Run()
	if err == nil {
		return "succeeded"
	}
	var exitError *exec.ExitError
	if errors.As(err, &exitError) && exitError.ExitCode() == 8 {
		return "locked"
	}
	if (adapter == "fx-factory-release" || adapter == "tarser-staging-deploy-release") && errors.As(err, &exitError) && exitError.ExitCode() == 6 {
		return "release_failed_rolled_back"
	}
	return "rollback_failed"
}

func invocation(adapter, sha string) ([]string, bool) {
	switch adapter {
	case "fx-factory-release":
		if commitSHAPattern.MatchString(sha) {
			return []string{"factory", "release", sha}, true
		}
	case "fx-factory-rollback":
		if commitSHAPattern.MatchString(sha) {
			return []string{"factory", "rollback"}, true
		}
	case "tarser-staging-deploy-release":
		if commitSHAPattern.MatchString(sha) {
			return []string{"staging", "release", sha}, true
		}
	case "tarser-staging-auto-rollback":
		if commitSHAPattern.MatchString(sha) {
			return []string{"staging", "rollback"}, true
		}
	}
	return nil, false
}

type operation struct {
	Request Request `json:"request"`
	Status  string  `json:"status"`
	PID     int     `json:"pid,omitempty"` // diagnostic only; never recovery input
}

type Broker struct {
	executor Executor
	stateDir string
	mu       sync.Mutex
	active   string
	items    map[string]*operation
}

// New is retained for callers that do not need restart recovery.  Production
// must use NewAt, supplied by the systemd StateDirectory.
func New(executor Executor) *Broker { return newBroker("", executor) }

func NewAt(stateDir string, executor Executor) (*Broker, error) {
	if stateDir == "" || !filepath.IsAbs(stateDir) {
		return nil, errors.New("state directory must be absolute")
	}
	if err := os.MkdirAll(stateDir, 0o700); err != nil {
		return nil, err
	}
	b := newBroker(stateDir, executor)
	entries, err := os.ReadDir(stateDir)
	if err != nil {
		return nil, err
	}
	for _, entry := range entries {
		if entry.IsDir() || filepath.Ext(entry.Name()) != ".json" {
			continue
		}
		var item operation
		data, err := os.ReadFile(filepath.Join(stateDir, entry.Name()))
		if err != nil || json.Unmarshal(data, &item) != nil || !operationIDPattern.MatchString(item.Request.OperationID) {
			continue
		}
		// A broker restart cannot prove an old in-process executor still exists.
		// Fail closed instead of launching it again.
		if item.Status == "launching" || item.Status == "running" {
			item.Status = "failed"
			_ = b.persist(&item)
		}
		b.items[item.Request.OperationID] = &item
	}
	return b, nil
}

func newBroker(stateDir string, executor Executor) *Broker {
	return &Broker{executor: executor, stateDir: stateDir, items: make(map[string]*operation)}
}

func (b *Broker) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("POST /v1/operations", b.start)
	mux.HandleFunc("GET /v1/operations/{operation_id}", b.status)
	return mux
}

func (b *Broker) persist(item *operation) error {
	if b.stateDir == "" {
		return nil
	}
	data, err := json.Marshal(item)
	if err != nil {
		return err
	}
	temporary, err := os.CreateTemp(b.stateDir, ".operation-")
	if err != nil {
		return err
	}
	name := temporary.Name()
	defer os.Remove(name)
	if _, err = temporary.Write(data); err == nil {
		err = temporary.Chmod(0o600)
	}
	if closeErr := temporary.Close(); err == nil {
		err = closeErr
	}
	if err != nil {
		return err
	}
	return os.Rename(name, filepath.Join(b.stateDir, item.Request.OperationID+".json"))
}

func valid(input Request) bool {
	return operationIDPattern.MatchString(input.OperationID) && commitSHAPattern.MatchString(input.CommitSHA) && func() bool { _, ok := invocation(input.Adapter, input.CommitSHA); return ok }()
}

func (b *Broker) start(w http.ResponseWriter, r *http.Request) {
	r.Body = http.MaxBytesReader(w, r.Body, MaxBodyBytes)
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	var input Request
	if err := decoder.Decode(&input); err != nil || !valid(input) {
		http.Error(w, "invalid operation identity or adapter", http.StatusBadRequest)
		return
	}
	b.mu.Lock()
	if existing := b.items[input.OperationID]; existing != nil {
		if existing.Request != input {
			b.mu.Unlock()
			http.Error(w, "operation identity already has different immutable input", http.StatusConflict)
			return
		}
		// rc=8 is a reservation failure, not a terminal delivery.  It is
		// explicitly safe to re-enter the executor with the same immutable
		// operation id once the privileged release lock is available again.
		if existing.Status == "locked" && b.active == "" {
			existing.Status = "launching"
			if err := b.persist(existing); err != nil {
				b.mu.Unlock()
				http.Error(w, "cannot persist operation", http.StatusServiceUnavailable)
				return
			}
			b.active = input.OperationID
			b.mu.Unlock()
			go b.execute(existing)
			writeJSON(w, http.StatusAccepted, Response{Status: "launching"})
			return
		}
		status := existing.Status
		b.mu.Unlock()
		writeJSON(w, http.StatusOK, Response{Status: status})
		return
	}
	if b.active != "" {
		b.mu.Unlock()
		http.Error(w, "another privileged operation is running", http.StatusConflict)
		return
	}
	item := &operation{Request: input, Status: "launching"}
	// The wrapper status is durable before any external executor can run.
	if err := b.persist(item); err != nil {
		b.mu.Unlock()
		http.Error(w, "cannot persist operation", http.StatusServiceUnavailable)
		return
	}
	b.items[input.OperationID], b.active = item, input.OperationID
	b.mu.Unlock()
	go b.execute(item)
	writeJSON(w, http.StatusAccepted, Response{Status: "launching"})
}

func (b *Broker) execute(item *operation) {
	b.mu.Lock()
	item.Status = "running"
	if err := b.persist(item); err != nil {
		item.Status = "failed"
		_ = b.persist(item)
		b.active = ""
		b.mu.Unlock()
		return
	}
	b.mu.Unlock()
	status := "failed"
	if delivery, ok := b.executor.(DeliveryExecutor); ok {
		status = delivery.ExecuteDelivery(context.Background(), item.Request.Adapter, item.Request.CommitSHA, item.Request.OperationID)
	} else {
		status = b.executor.Execute(context.Background(), item.Request.Adapter, item.Request.CommitSHA)
	}
	switch status {
	case "succeeded", "locked", "release_failed_rolled_back", "rollback_failed", "failed":
	default:
		status = "failed"
	}
	b.mu.Lock()
	item.Status = status
	_ = b.persist(item)
	if b.active == item.Request.OperationID {
		b.active = ""
	}
	b.mu.Unlock()
}

func (b *Broker) status(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("operation_id")
	if !operationIDPattern.MatchString(id) {
		http.Error(w, "invalid operation identity", http.StatusBadRequest)
		return
	}
	b.mu.Lock()
	item := b.items[id]
	if item == nil {
		b.mu.Unlock()
		http.Error(w, "operation not found", http.StatusNotFound)
		return
	}
	status := item.Status
	b.mu.Unlock()
	writeJSON(w, http.StatusOK, Response{Status: status})
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}
