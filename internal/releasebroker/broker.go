// Package releasebroker owns the privileged, idempotent release boundary.
package releasebroker

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
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

// PIDDeliveryExecutor reports the real child PID after it has started but
// before the broker calls the operation running.  PID is diagnostic only: a
// restarted broker still fails an uncertain operation closed rather than
// trying to adopt or restart that process.
type PIDDeliveryExecutor interface {
	ExecuteDeliveryWithPID(context.Context, string, string, string, func(int) bool) string
}

type FXExecutor struct {
	Executable               string
	FactoryReleaseExecutable string
}

func (e FXExecutor) Execute(ctx context.Context, adapter, sha string) string {
	return e.ExecuteDelivery(ctx, adapter, sha, "")
}

func (e FXExecutor) ExecuteDelivery(ctx context.Context, adapter, sha, operationID string) string {
	return e.ExecuteDeliveryWithPID(ctx, adapter, sha, operationID, func(int) bool { return true })
}

func (e FXExecutor) ExecuteDeliveryWithPID(ctx context.Context, adapter, sha, operationID string, started func(int) bool) string {
	executable, args, ok := e.invocation(adapter, sha)
	if !ok {
		return "failed"
	}
	command := exec.CommandContext(ctx, executable, args...)
	command.Env = []string{
		"LANG=C.UTF-8", "LC_ALL=C.UTF-8",
		"PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
		"FACTORY_DELIVERY_ID=" + operationID,
	}
	if err := command.Start(); err != nil {
		return "rollback_failed"
	}
	if started != nil && !started(command.Process.Pid) {
		_ = command.Process.Kill()
		_ = command.Wait()
		return "failed"
	}
	err := command.Wait()
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

func (e FXExecutor) invocation(adapter, sha string) (string, []string, bool) {
	if !commitSHAPattern.MatchString(sha) {
		return "", nil, false
	}
	if adapter == "fx-factory-release" || adapter == "fx-factory-rollback" {
		executable := e.FactoryReleaseExecutable
		if executable == "" {
			executable = "/usr/local/lib/fx-factory-release"
		}
		if adapter == "fx-factory-release" {
			return executable, []string{sha}, true
		}
		return executable, []string{"--rollback"}, true
	}
	executable := e.Executable
	if executable == "" {
		executable = "/usr/local/bin/fx"
	}
	args, ok := invocation(adapter, sha)
	return executable, args, ok
}

func invocation(adapter, sha string) ([]string, bool) {
	switch adapter {
	case "fx-factory-release":
		if commitSHAPattern.MatchString(sha) {
			return []string{sha}, true
		}
	case "fx-factory-rollback":
		if commitSHAPattern.MatchString(sha) {
			return []string{"--rollback"}, true
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
	FormatVersion int     `json:"format_version,omitempty"`
	Request       Request `json:"request"`
	Status        string  `json:"status"`
	// Posts is an audit counter at the real privileged boundary.  It lets
	// recovery diagnostics distinguish one accepted operation from its safe,
	// same-identity retry without trusting an in-process client counter.
	Posts int `json:"posts"`
	PID   int `json:"pid,omitempty"` // diagnostic only; never recovery input
}

type terminalMarker struct {
	Status string `json:"status"`
}

type Broker struct {
	executor Executor
	stateDir string
	// persistTerminal is a test seam for a failed final state write.
	persistTerminal func(*operation) error
	syncFile        func(*os.File) error
	rename          func(string, string) error
	syncDir         func(string) error
	mu              sync.Mutex
	active          string
	draining        bool
	items           map[string]*operation
	brokerReplaced  func() (bool, error)
	restartBroker   func() error
}

// WithBrokerRestart asks systemd to replace this process after a Factory
// release has durably committed an updated broker executable.
func WithBrokerRestart(installedExecutable, unit string) func(*Broker) {
	return func(b *Broker) {
		b.brokerReplaced = func() (bool, error) {
			running, err := os.Stat("/proc/self/exe")
			if err != nil {
				return false, err
			}
			installed, err := os.Stat(installedExecutable)
			if err != nil {
				return false, err
			}
			return !os.SameFile(running, installed), nil
		}
		b.restartBroker = func() error {
			return exec.Command("/usr/bin/systemctl", "restart", unit).Run()
		}
	}
}

func (b *Broker) saveTerminal(item *operation) error {
	if b.persistTerminal != nil {
		return b.persistTerminal(item)
	}
	return b.persist(item)
}

// New is retained for callers that do not need restart recovery.  Production
// must use NewAt, supplied by the systemd StateDirectory.
func New(executor Executor) *Broker { return newBroker("", executor) }

func NewAt(stateDir string, executor Executor, options ...func(*Broker)) (*Broker, error) {
	if stateDir == "" || !filepath.IsAbs(stateDir) {
		return nil, errors.New("state directory must be absolute")
	}
	if err := os.MkdirAll(stateDir, 0o700); err != nil {
		return nil, err
	}
	b := newBroker(stateDir, executor)
	for _, option := range options {
		option(b)
	}
	entries, err := os.ReadDir(stateDir)
	if err != nil {
		return nil, err
	}
	markers := make(map[string]string)
	for _, entry := range entries {
		if entry.IsDir() || filepath.Ext(entry.Name()) != ".commit" {
			continue
		}
		var marker terminalMarker
		data, err := os.ReadFile(filepath.Join(stateDir, entry.Name()))
		if err != nil || json.Unmarshal(data, &marker) != nil || (marker.Status != "pending" && marker.Status != "committed") {
			return nil, fmt.Errorf("invalid terminal marker %q", entry.Name())
		}
		markers[strings.TrimSuffix(entry.Name(), ".commit")] = marker.Status
	}
	for _, entry := range entries {
		if filepath.Ext(entry.Name()) != ".json" {
			continue
		}
		if entry.IsDir() || !entry.Type().IsRegular() {
			return nil, fmt.Errorf("operation state %q is not a regular file", entry.Name())
		}
		var item operation
		data, err := os.ReadFile(filepath.Join(stateDir, entry.Name()))
		if err != nil {
			return nil, fmt.Errorf("read operation state %q: %w", entry.Name(), err)
		}
		if err := json.Unmarshal(data, &item); err != nil {
			return nil, fmt.Errorf("decode operation state %q: %w", entry.Name(), err)
		}
		if !valid(item.Request) || entry.Name() != item.Request.OperationID+".json" ||
			(item.FormatVersion != 0 && item.FormatVersion != 1) ||
			!validPersistedStatus(item.Status) || item.Posts < 1 || item.PID < 0 {
			// Losing an accepted operation can make a repeated POST execute the
			// same physical release again.  Refuse to start instead of treating a
			// malformed durable record as if the operation never existed.
			return nil, fmt.Errorf("invalid operation state %q", entry.Name())
		}
		// A broker restart cannot prove an old in-process executor still exists.
		// Fail closed instead of launching it again.
		if item.Status == "launching" || item.Status == "running" {
			updated := item
			updated.Status = "failed"
			if err := b.persist(&updated); err != nil {
				// Do not publish a terminal recovery result which the next
				// restart cannot observe.  Refusing to start also prevents any
				// caller from mistaking an in-memory result for durable proof.
				return nil, err
			}
			item = updated
		}
		if item.FormatVersion == 1 && isTerminal(item.Status) && markers[item.Request.OperationID] != "committed" {
			// A terminal record without a separately fsynced commit marker may
			// have crossed rename but not the directory durability boundary.
			// Keep recovery fail-closed even if the record says succeeded.
			item.Status = "failed"
		}
		b.items[item.Request.OperationID] = &item
	}
	return b, nil
}

func validPersistedStatus(status string) bool {
	switch status {
	case "launching", "running", "succeeded", "locked", "release_failed_rolled_back", "rollback_failed", "failed":
		return true
	default:
		return false
	}
}

func isTerminal(status string) bool {
	return status == "succeeded" || status == "locked" || status == "release_failed_rolled_back" || status == "rollback_failed" || status == "failed"
}

func (b *Broker) writeTerminalMarker(operationID, status string, create bool) error {
	if b.stateDir == "" {
		return nil
	}
	data, err := json.Marshal(terminalMarker{Status: status})
	if err != nil {
		return err
	}
	markerPath := filepath.Join(b.stateDir, operationID+".commit")
	if !create {
		file, err := os.OpenFile(markerPath, os.O_WRONLY|os.O_TRUNC, 0o600)
		if err != nil {
			return err
		}
		if _, err = file.Write(data); err == nil {
			err = b.syncFile(file)
		}
		if closeErr := file.Close(); err == nil {
			err = closeErr
		}
		return err
	}
	temporary, err := os.CreateTemp(b.stateDir, ".commit-")
	if err != nil {
		return err
	}
	temporaryName := temporary.Name()
	defer os.Remove(temporaryName)
	if _, err = temporary.Write(data); err == nil {
		err = temporary.Chmod(0o600)
	}
	if err == nil {
		err = b.syncFile(temporary)
	}
	if closeErr := temporary.Close(); err == nil {
		err = closeErr
	}
	if err != nil {
		return err
	}
	if err := b.rename(temporaryName, markerPath); err != nil {
		return err
	}
	return b.syncDir(b.stateDir)
}

func newBroker(stateDir string, executor Executor) *Broker {
	return &Broker{
		executor: executor, stateDir: stateDir, items: make(map[string]*operation),
		syncFile: func(file *os.File) error { return file.Sync() },
		rename:   os.Rename,
		syncDir: func(path string) error {
			directory, err := os.Open(path)
			if err != nil {
				return err
			}
			defer directory.Close()
			return directory.Sync()
		},
	}
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
	if err == nil {
		err = b.syncFile(temporary)
	}
	if closeErr := temporary.Close(); err == nil {
		err = closeErr
	}
	if err != nil {
		return err
	}
	if err := b.rename(name, filepath.Join(b.stateDir, item.Request.OperationID+".json")); err != nil {
		return err
	}
	return b.syncDir(b.stateDir)
}

func valid(input Request) bool {
	return operationIDPattern.MatchString(input.OperationID) && commitSHAPattern.MatchString(input.CommitSHA) && func() bool { _, ok := invocation(input.Adapter, input.CommitSHA); return ok }()
}

func deliveryTarget(adapter string) (string, bool) {
	switch adapter {
	case "fx-factory-release", "fx-factory-rollback":
		return "factory", true
	case "tarser-staging-deploy-release", "tarser-staging-auto-rollback":
		return "tarser-staging", true
	default:
		return "", false
	}
}

// canJoinLockedOperation is deliberately narrower than Request equality.  A
// lock (rc=8) did not accept a physical release, so Pilot may retry the same
// delivery id with the newer main SHA.  Its adapter and derived project target
// remain immutable; otherwise a retry could turn one release into a rollback.
func canJoinLockedOperation(existing, retry Request) bool {
	existingTarget, existingOK := deliveryTarget(existing.Adapter)
	retryTarget, retryOK := deliveryTarget(retry.Adapter)
	return existingOK && retryOK &&
		existing.OperationID == retry.OperationID &&
		existing.Adapter == retry.Adapter &&
		existingTarget == retryTarget
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
		if b.draining {
			if existing.Request != input {
				b.mu.Unlock()
				http.Error(w, "broker is restarting", http.StatusServiceUnavailable)
				return
			}
			status := existing.Status
			b.mu.Unlock()
			writeJSON(w, http.StatusOK, Response{Status: status})
			return
		}
		// A lock did not accept a release.  Pilot may therefore safely attach a
		// later merge to the still-reserved generation and retry its same id
		// with the newest commit snapshot before the next executor launch.  The
		// adapter and target are not mutable at that boundary.
		lockedRetry := existing.Status == "locked" && b.active == ""
		if existing.Request != input && (!lockedRetry || !canJoinLockedOperation(existing.Request, input)) {
			b.mu.Unlock()
			http.Error(w, "operation identity already has different immutable input", http.StatusConflict)
			return
		}
		// rc=8 is a reservation failure, not a terminal delivery.  It is
		// explicitly safe to re-enter the executor with the same immutable
		// operation id once the privileged release lock is available again.
		if lockedRetry {
			// Persist the allowed newer SHA and the new launch as one operation
			// record.  A failed write leaves both the in-memory and durable
			// identity unchanged for the next safe retry.
			updated := *existing
			updated.FormatVersion = 1
			updated.Request = input
			updated.Status = "launching"
			updated.PID = 0
			updated.Posts++
			if err := b.persist(&updated); err != nil {
				b.mu.Unlock()
				http.Error(w, "cannot persist operation", http.StatusServiceUnavailable)
				return
			}
			*existing = updated
			b.active = input.OperationID
			b.mu.Unlock()
			go b.execute(existing)
			writeJSON(w, http.StatusAccepted, Response{Status: "launching"})
			return
		}
		updated := *existing
		updated.Posts++
		if err := b.persist(&updated); err != nil {
			b.mu.Unlock()
			http.Error(w, "cannot persist operation", http.StatusServiceUnavailable)
			return
		}
		*existing = updated
		status := existing.Status
		b.mu.Unlock()
		writeJSON(w, http.StatusOK, Response{Status: status})
		return
	}
	if b.draining {
		b.mu.Unlock()
		http.Error(w, "broker is restarting", http.StatusServiceUnavailable)
		return
	}
	if b.active != "" {
		b.mu.Unlock()
		http.Error(w, "another privileged operation is running", http.StatusConflict)
		return
	}
	item := &operation{FormatVersion: 1, Request: input, Status: "launching", Posts: 1}
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
	request := item.Request
	b.mu.Unlock()
	status := "failed"
	if delivery, ok := b.executor.(PIDDeliveryExecutor); ok {
		status = delivery.ExecuteDeliveryWithPID(context.Background(), request.Adapter, request.CommitSHA, request.OperationID,
			func(pid int) bool { return b.runnerStarted(item, pid) })
	} else if !b.runnerStarted(item, 0) {
		return
	} else if delivery, ok := b.executor.(DeliveryExecutor); ok {
		status = delivery.ExecuteDelivery(context.Background(), request.Adapter, request.CommitSHA, request.OperationID)
	} else {
		status = b.executor.Execute(context.Background(), request.Adapter, request.CommitSHA)
	}
	switch status {
	case "succeeded", "locked", "release_failed_rolled_back", "rollback_failed", "failed":
	default:
		status = "failed"
	}
	b.mu.Lock()
	// A terminal response is delivery proof.  Publish it only after the same
	// value is durably represented by the operation record.  If persistence
	// fails, retain the prior non-terminal state: callers must not create a
	// receipt from an outcome which a fresh broker cannot confirm.
	updated := *item
	updated.Status = status
	committed := false
	if err := b.writeTerminalMarker(item.Request.OperationID, "pending", true); err == nil {
		if err := b.saveTerminal(&updated); err == nil && b.writeTerminalMarker(item.Request.OperationID, "committed", false) == nil {
			*item = updated
			committed = true
		}
	}
	if b.active == item.Request.OperationID {
		b.active = ""
	}
	// Once a committed Factory release has replaced this executable, reject
	// every new operation before releasing the mutex.  systemd will replace this
	// process next; accepting a driver in between would let that restart kill it.
	restart := false
	if committed && request.Adapter == "fx-factory-release" && b.brokerReplaced != nil && b.restartBroker != nil {
		replaced, err := b.brokerReplaced()
		if err != nil {
			log.Printf("release broker: cannot determine whether broker changed: %v", err)
		} else if replaced {
			b.draining = true
			restart = true
		}
	}
	b.mu.Unlock()
	// Restarting earlier would kill the release driver in this broker's cgroup.
	// A draining broker remains closed until systemd takes over, even if restart
	// itself reports an error.
	if restart {
		if err := b.restartBroker(); err != nil {
			log.Printf("release broker: cannot restart updated broker: %v", err)
		}
	}
}

// runnerStarted creates the real durable boundaries after the wrapper starts:
// PID first, then running.  Neither transition relies on PID during recovery.
func (b *Broker) runnerStarted(item *operation, pid int) bool {
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.active != item.Request.OperationID || item.Status != "launching" {
		return false
	}
	updated := *item
	updated.PID = pid
	if err := b.persist(&updated); err != nil {
		b.active = ""
		return false
	}
	*item = updated
	updated.Status = "running"
	if err := b.persist(&updated); err != nil {
		b.active = ""
		return false
	}
	*item = updated
	return true
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
