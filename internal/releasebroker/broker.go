// Package releasebroker owns the privileged, idempotent release boundary.
package releasebroker

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
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
	Reason string `json:"reason,omitempty"`
}

type AcceptanceRequest struct {
	OperationID string `json:"operation_id"`
	CommitSHA   string `json:"commit_sha"`
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
	Posts            int    `json:"posts"`
	PID              int    `json:"pid,omitempty"` // diagnostic only; never recovery input
	AcceptanceStatus string `json:"acceptance_status,omitempty"`
	AcceptanceReason string `json:"acceptance_reason,omitempty"`
}

type terminalMarker struct {
	Status string `json:"status"`
}

type Broker struct {
	executor Executor
	stateDir string
	// persistTerminal is a test seam for a failed final state write.
	persistTerminal      func(*operation) error
	syncFile             func(*os.File) error
	rename               func(string, string) error
	syncDir              func(string) error
	mu                   sync.Mutex
	active               string
	items                map[string]*operation
	executablePath       string
	executableHash       [sha256.Size]byte
	restart              func()
	acceptanceExecutable string
}

// RestartWhenExecutableChanges asks the broker to leave its current process
// only after a terminal operation has been durably committed. The service
// manager can then start the executable which the release installed in place
// of the running image without interrupting the delivery receipt.
func (b *Broker) RestartWhenExecutableChanges(path string, restart func()) error {
	if !filepath.IsAbs(path) || restart == nil {
		return errors.New("restart executable path and handler are required")
	}
	body, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	b.mu.Lock()
	b.executablePath = path
	b.executableHash = sha256.Sum256(body)
	b.restart = restart
	b.mu.Unlock()
	return nil
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
		// A checker is an external process too.  After a broker restart we cannot
		// prove that a checker recorded as running is still the one we started.
		// Keep the release closed until a new explicit remediation cycle.
		if item.AcceptanceStatus == "running" {
			item.AcceptanceStatus = "failed"
			item.AcceptanceReason = "acceptance_interrupted"
			if err := b.persist(&item); err != nil {
				return nil, err
			}
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
	mux.HandleFunc("POST /v1/operations/{operation_id}/acceptance", b.acceptance)
	mux.HandleFunc("GET /v1/operations/{operation_id}/acceptance", b.acceptance)
	return mux
}

// ConfigureAcceptance limits live checks to one root-owned executable.
func (b *Broker) ConfigureAcceptance(path string) error {
	if path != "" && !filepath.IsAbs(path) {
		return errors.New("acceptance executable must be absolute")
	}
	b.mu.Lock()
	b.acceptanceExecutable = path
	b.mu.Unlock()
	return nil
}

func (b *Broker) acceptance(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("operation_id")
	b.mu.Lock()
	item := b.items[id]
	if item == nil || item.Status != "succeeded" {
		b.mu.Unlock()
		http.Error(w, "released operation not found", http.StatusConflict)
		return
	}
	if r.Method == "GET" {
		status, reason := item.AcceptanceStatus, item.AcceptanceReason
		b.mu.Unlock()
		if status == "" {
			status = "pending"
		}
		writeJSON(w, http.StatusOK, Response{Status: status, Reason: reason})
		return
	}
	r.Body = http.MaxBytesReader(w, r.Body, MaxBodyBytes)
	var input AcceptanceRequest
	if err := json.NewDecoder(r.Body).Decode(&input); err != nil || input.OperationID != id || input.CommitSHA != item.Request.CommitSHA {
		b.mu.Unlock()
		http.Error(w, "immutable acceptance identity conflict", http.StatusConflict)
		return
	}
	if item.AcceptanceStatus == "passed" || item.AcceptanceStatus == "failed" {
		status, reason := item.AcceptanceStatus, item.AcceptanceReason
		b.mu.Unlock()
		writeJSON(w, http.StatusOK, Response{Status: status, Reason: reason})
		return
	}
	if item.AcceptanceStatus == "running" {
		b.mu.Unlock()
		writeJSON(w, http.StatusOK, Response{Status: "running"})
		return
	}
	if b.acceptanceExecutable == "" {
		// Never let an unconfigured broker turn a release into a verified one.
		item.AcceptanceStatus = "failed"
		item.AcceptanceReason = "acceptance_not_configured"
		if err := b.persist(item); err != nil {
			b.mu.Unlock()
			http.Error(w, "cannot persist acceptance", http.StatusServiceUnavailable)
			return
		}
		b.mu.Unlock()
		writeJSON(w, http.StatusOK, Response{Status: "failed", Reason: "acceptance_not_configured"})
		return
	}
	item.AcceptanceStatus = "running"
	if err := b.persist(item); err != nil {
		b.mu.Unlock()
		http.Error(w, "cannot persist acceptance", http.StatusServiceUnavailable)
		return
	}
	executable := b.acceptanceExecutable
	sha := item.Request.CommitSHA
	b.mu.Unlock()
	// A live check may take a while.  Publish its durable boundary and return
	// immediately so duplicate POSTs can observe running instead of tying up
	// the only request that could report it.
	go b.runAcceptance(id, executable, sha)
	writeJSON(w, http.StatusOK, Response{Status: "running"})
}

func (b *Broker) runAcceptance(id, executable, sha string) {
	output, err := exec.Command(executable, "--generation-id", id, "--commit-sha", sha).Output()
	status, reason := "failed", "acceptance_execution_failed"
	var result Response
	if err == nil && json.Unmarshal(output, &result) == nil && (result.Status == "passed" || result.Status == "failed") {
		status, reason = result.Status, result.Reason
	}
	b.mu.Lock()
	item := b.items[id]
	if item == nil || item.AcceptanceStatus != "running" {
		b.mu.Unlock()
		return
	}
	updated := *item
	updated.AcceptanceStatus, updated.AcceptanceReason = status, reason
	persistErr := b.persist(&updated)
	if persistErr == nil {
		*item = updated
	}
	b.mu.Unlock()
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
	terminalCommitted := false
	if err := b.writeTerminalMarker(item.Request.OperationID, "pending", true); err == nil {
		if err := b.saveTerminal(&updated); err == nil && b.writeTerminalMarker(item.Request.OperationID, "committed", false) == nil {
			*item = updated
			terminalCommitted = true
		}
	}
	if b.active == item.Request.OperationID {
		b.active = ""
	}
	restart := b.restart
	if !terminalCommitted || !b.executableChanged() {
		restart = nil
	} else {
		// At most one terminal operation may request this process restart.
		b.restart = nil
	}
	b.mu.Unlock()
	if restart != nil {
		restart()
	}
}

// executableChanged is called with b.mu held. A read failure must not recycle
// a healthy broker: the next successful release can try the comparison again.
func (b *Broker) executableChanged() bool {
	if b.executablePath == "" || b.restart == nil {
		return false
	}
	body, err := os.ReadFile(b.executablePath)
	return err == nil && sha256.Sum256(body) != b.executableHash
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
