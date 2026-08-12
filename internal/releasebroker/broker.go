// Package releasebroker owns the privileged, idempotent release boundary.
package releasebroker

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"syscall"
	"time"
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

// DurableStatusExecutor is the release-driver proof boundary.  Exit status is
// not enough to claim a completed delivery: the driver must have stored its
// own generation-specific terminal status below the broker-owned directory.
type DurableStatusExecutor interface {
	DurableDeliveryStatus(operationID string) (string, bool)
}

type FXExecutor struct {
	Executable       string
	DeliveryStateDir string
}

func (e FXExecutor) Execute(ctx context.Context, adapter, sha string) string {
	return e.ExecuteDelivery(ctx, adapter, sha, "")
}

func (e FXExecutor) ExecuteDelivery(ctx context.Context, adapter, sha, operationID string) string {
	return e.ExecuteDeliveryWithPID(ctx, adapter, sha, operationID, func(int) bool { return true })
}

func (e FXExecutor) ExecuteDeliveryWithPID(ctx context.Context, adapter, sha, operationID string, started func(int) bool) string {
	executable := e.Executable
	if executable == "" {
		executable = "/usr/local/bin/fx"
	}
	args, ok := invocation(adapter, sha)
	if !ok {
		return "failed"
	}
	if e.DeliveryStateDir != "" {
		if err := validateSecureDirectory(e.DeliveryStateDir); err != nil {
			return "failed"
		}
	}
	// The shell is deliberately only a small exec gate.  It joins a dedicated
	// process group and cannot exec the real driver until the broker has
	// durably recorded both its PID and running status.  This removes the
	// start-before-persist race in which a child could grab the release lock.
	gateRead, gateWrite, err := os.Pipe()
	if err != nil {
		return "rollback_failed"
	}
	defer gateWrite.Close()
	commandArgs := append([]string{"-c", `IFS= read -r _ <&3 || exit 125; exec "$@"`, "factory-release-gate", executable}, args...)
	command := exec.CommandContext(ctx, "/bin/sh", commandArgs...)
	command.ExtraFiles = []*os.File{gateRead}
	command.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	command.Env = []string{
		"LANG=C.UTF-8", "LC_ALL=C.UTF-8",
		"PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
		"FACTORY_DELIVERY_ID=" + operationID,
	}
	if e.DeliveryStateDir != "" {
		command.Env = append(command.Env, "FACTORY_DELIVERY_STATE_DIR="+e.DeliveryStateDir)
	}
	if err := command.Start(); err != nil {
		_ = gateRead.Close()
		return "rollback_failed"
	}
	_ = gateRead.Close()
	if started != nil && !started(command.Process.Pid) {
		_ = gateWrite.Close()
		stopAndReapProcessGroup(command)
		return "failed"
	}
	if _, err := io.WriteString(gateWrite, "go\n"); err != nil {
		_ = gateWrite.Close()
		stopAndReapProcessGroup(command)
		return "failed"
	}
	_ = gateWrite.Close()
	err = command.Wait()
	if adapter == "tarser-staging-deploy-release" || adapter == "tarser-staging-auto-rollback" {
		// Tarser has no generation-aware durable driver status contract yet.
		// Its exit code is therefore never a completion proof.
		var exitError *exec.ExitError
		if errors.As(err, &exitError) && exitError.ExitCode() == 8 {
			return "locked"
		}
		return "failed"
	}
	if err == nil {
		return "succeeded"
	}
	var exitError *exec.ExitError
	if errors.As(err, &exitError) && exitError.ExitCode() == 8 {
		return "locked"
	}
	if adapter == "fx-factory-release" && errors.As(err, &exitError) && exitError.ExitCode() == 6 {
		return "release_failed_rolled_back"
	}
	return "rollback_failed"
}

// stopAndReapProcessGroup terminates every process that could have inherited
// the launch gate.  A failed PID/running persistence callback must never
// leave a delayed shell or helper able to reach the privileged release lock.
func stopAndReapProcessGroup(command *exec.Cmd) {
	if command == nil || command.Process == nil {
		return
	}
	pid := command.Process.Pid
	_ = syscall.Kill(-pid, syscall.SIGTERM)
	done := make(chan error, 1)
	go func() { done <- command.Wait() }()
	select {
	case <-done:
		// A background helper may have outlived the shell.  It is still in the
		// dedicated group, so make the cleanup terminal before returning.
		_ = syscall.Kill(-pid, syscall.SIGKILL)
	case <-time.After(2 * time.Second):
		_ = syscall.Kill(-pid, syscall.SIGKILL)
		<-done
	}
}

// DurableDeliveryStatus reads only a root-owned, private driver status.  The
// broker supplies this directory itself, so a factory-server Unix-socket
// client has no path through which it can pre-seed a completed operation.
func (e FXExecutor) DurableDeliveryStatus(operationID string) (string, bool) {
	if e.DeliveryStateDir == "" || !operationIDPattern.MatchString(operationID) {
		return "", false
	}
	if err := validateSecureDirectory(e.DeliveryStateDir); err != nil {
		return "", false
	}
	path := filepath.Join(e.DeliveryStateDir, operationID+".status")
	if err := validateSecureFile(path); err != nil {
		return "", false
	}
	data, err := os.ReadFile(path)
	if err != nil || len(data) > 128 {
		return "", false
	}
	status := strings.TrimSpace(string(data))
	switch status {
	case "launching", "running", "locked", "succeeded", "failed", "release_failed_rolled_back", "rollback_failed":
		return status, true
	default:
		return "", false
	}
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
	// Posts is an audit counter at the real privileged boundary.  It lets
	// recovery diagnostics distinguish one accepted operation from its safe,
	// same-identity retry without trusting an in-process client counter.
	Posts int `json:"posts"`
	PID   int `json:"pid,omitempty"` // diagnostic only; never recovery input
}

type Broker struct {
	executor   Executor
	stateDir   string
	syncFile   func(*os.File) error
	closeFile  func(*os.File) error
	renameFile func(string, string) error
	syncDir    func(string) error
	mu         sync.Mutex
	active     string
	items      map[string]*operation
}

// New is retained for callers that do not need restart recovery.  Production
// must use NewAt, supplied by the systemd StateDirectory.
func New(executor Executor) *Broker { return newBroker("", executor) }

func NewAt(stateDir string, executor Executor) (*Broker, error) {
	if stateDir == "" || !filepath.IsAbs(stateDir) {
		return nil, errors.New("state directory must be absolute")
	}
	if err := prepareSecureDirectory(stateDir); err != nil {
		return nil, err
	}
	// A real FX executor gets a status directory below the root-only broker
	// state root.  It is intentionally not configurable by POST input or the
	// factory-server process that can reach the Unix socket.
	switch value := executor.(type) {
	case FXExecutor:
		if value.DeliveryStateDir == "" {
			value.DeliveryStateDir = filepath.Join(stateDir, "driver-status")
		}
		if filepath.Clean(value.DeliveryStateDir) != filepath.Join(stateDir, "driver-status") {
			return nil, errors.New("driver status directory must be inside broker state")
		}
		if err := prepareSecureDirectory(value.DeliveryStateDir); err != nil {
			return nil, err
		}
		executor = value
	case *FXExecutor:
		if value == nil {
			return nil, errors.New("missing FX executor")
		}
		if value.DeliveryStateDir == "" {
			value.DeliveryStateDir = filepath.Join(stateDir, "driver-status")
		}
		if filepath.Clean(value.DeliveryStateDir) != filepath.Join(stateDir, "driver-status") {
			return nil, errors.New("driver status directory must be inside broker state")
		}
		if err := prepareSecureDirectory(value.DeliveryStateDir); err != nil {
			return nil, err
		}
	}
	b := newBroker(stateDir, executor)
	entries, err := os.ReadDir(stateDir)
	if err != nil {
		return nil, err
	}
	for _, entry := range entries {
		if filepath.Ext(entry.Name()) != ".json" {
			continue
		}
		if entry.IsDir() {
			return nil, fmt.Errorf("unsafe operation status %q: not a file", entry.Name())
		}
		path := filepath.Join(stateDir, entry.Name())
		if err := validateSecureFile(path); err != nil {
			return nil, fmt.Errorf("unsafe operation status %q: %w", entry.Name(), err)
		}
		var item operation
		data, err := os.ReadFile(path)
		if err != nil || json.Unmarshal(data, &item) != nil || !valid(item.Request) ||
			filepath.Base(item.Request.OperationID+".json") != entry.Name() {
			return nil, fmt.Errorf("invalid operation status %q", entry.Name())
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
		b.items[item.Request.OperationID] = &item
	}
	return b, nil
}

// prepareSecureDirectory accepts a fresh path, but rejects an existing
// writable/preseeded one.  StateDirectory normally creates it for root; the
// explicit validation keeps a manual launch from silently trusting a socket
// client's directory or symlink.
func prepareSecureDirectory(path string) error {
	info, err := os.Lstat(path)
	if errors.Is(err, os.ErrNotExist) {
		if err := os.MkdirAll(path, 0o700); err != nil {
			return err
		}
		if err := os.Chmod(path, 0o700); err != nil {
			return err
		}
		info, err = os.Lstat(path)
	}
	if err != nil {
		return err
	}
	if info.Mode()&os.ModeSymlink != 0 || !info.IsDir() {
		return errors.New("state path is not a real directory")
	}
	return validateSecureDirectory(path)
}

func validateSecureDirectory(path string) error {
	info, err := os.Lstat(path)
	if err != nil {
		return err
	}
	if info.Mode()&os.ModeSymlink != 0 || !info.IsDir() {
		return errors.New("not a real directory")
	}
	if info.Mode().Perm() != 0o700 {
		return fmt.Errorf("directory mode %04o is not 0700", info.Mode().Perm())
	}
	return validateSecureOwner(info)
}

func validateSecureFile(path string) error {
	info, err := os.Lstat(path)
	if err != nil {
		return err
	}
	if info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
		return errors.New("not a regular file")
	}
	if info.Mode().Perm() != 0o600 {
		return fmt.Errorf("file mode %04o is not 0600", info.Mode().Perm())
	}
	return validateSecureOwner(info)
}

func validateSecureOwner(info os.FileInfo) error {
	stat, ok := info.Sys().(*syscall.Stat_t)
	if !ok {
		return errors.New("cannot inspect owner")
	}
	if stat.Uid != uint32(os.Geteuid()) {
		return fmt.Errorf("owner uid %d does not match broker uid %d", stat.Uid, os.Geteuid())
	}
	return nil
}

func newBroker(stateDir string, executor Executor) *Broker {
	return &Broker{
		executor: executor, stateDir: stateDir, items: make(map[string]*operation),
		syncFile: (*os.File).Sync, closeFile: (*os.File).Close,
		renameFile: os.Rename, syncDir: syncDirectory,
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
	if err := validateSecureDirectory(b.stateDir); err != nil {
		return err
	}
	data, err := json.Marshal(item)
	if err != nil {
		return err
	}
	target := filepath.Join(b.stateDir, item.Request.OperationID+".json")
	if _, err := os.Lstat(target); err == nil {
		if err := validateSecureFile(target); err != nil {
			return err
		}
	} else if !errors.Is(err, os.ErrNotExist) {
		return err
	}
	previous, previousErr := os.ReadFile(target)
	if previousErr != nil && !errors.Is(previousErr, os.ErrNotExist) {
		return previousErr
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
	if closeErr := b.closeFile(temporary); err == nil {
		err = closeErr
	}
	if err != nil {
		return err
	}
	if err := b.renameFile(name, target); err != nil {
		return err
	}
	if err := b.syncDir(b.stateDir); err != nil {
		// Rename durability is ambiguous after a directory sync error. Restore
		// the last known durable record before returning so neither this broker
		// nor a fresh one can consume an unconfirmed terminal result.
		if restoreErr := b.restore(target, previous, previousErr == nil); restoreErr != nil {
			return errors.Join(err, restoreErr)
		}
		return err
	}
	return nil
}

func (b *Broker) restore(target string, previous []byte, existed bool) error {
	if !existed {
		if err := os.Remove(target); err != nil && !errors.Is(err, os.ErrNotExist) {
			return err
		}
		return b.syncDir(b.stateDir)
	}
	temporary, err := os.CreateTemp(b.stateDir, ".operation-restore-")
	if err != nil {
		return err
	}
	name := temporary.Name()
	defer os.Remove(name)
	if _, err = temporary.Write(previous); err == nil {
		err = temporary.Chmod(0o600)
	}
	if err == nil {
		err = b.syncFile(temporary)
	}
	if closeErr := b.closeFile(temporary); err == nil {
		err = closeErr
	}
	if err != nil {
		return err
	}
	if err = b.renameFile(name, target); err != nil {
		return err
	}
	return b.syncDir(b.stateDir)
}

func syncDirectory(path string) error {
	directory, err := os.Open(path)
	if err != nil {
		return err
	}
	if err = directory.Sync(); err != nil {
		_ = directory.Close()
		return err
	}
	return directory.Close()
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
	item := &operation{Request: input, Status: "launching", Posts: 1}
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
	if !b.terminalStatusProven(item, status) {
		// A release driver can finish with a non-zero code after its final
		// status write has failed.  Leaving the prior running record visible is
		// safer than publishing a rollback/failed terminal result that is not
		// backed by the driver.  A fresh broker later turns this uncertain
		// operation into durable failed without retrying the executor.
		b.mu.Lock()
		if b.active == item.Request.OperationID {
			b.active = ""
		}
		b.mu.Unlock()
		return
	}
	b.mu.Lock()
	// A terminal response is delivery proof.  Publish it only after the same
	// value is durably represented by the operation record.  If persistence
	// fails, retain the prior non-terminal state: callers must not create a
	// receipt from an outcome which a fresh broker cannot confirm.
	updated := *item
	updated.Status = status
	if err := b.persist(&updated); err == nil {
		*item = updated
	}
	if b.active == item.Request.OperationID {
		b.active = ""
	}
	b.mu.Unlock()
}

func (b *Broker) terminalStatusProven(item *operation, status string) bool {
	if status == "locked" {
		return true
	}
	prover, ok := b.executor.(DurableStatusExecutor)
	if !ok {
		// Test and in-memory executors represent their terminal callback
		// directly.  The production FX executor always implements the proof
		// interface and cannot take this compatibility path.
		return true
	}
	proof, ok := prover.DurableDeliveryStatus(item.Request.OperationID)
	if !ok {
		return false
	}
	switch status {
	case "succeeded":
		return proof == "succeeded"
	case "failed", "release_failed_rolled_back", "rollback_failed":
		// The Factory driver records one conservative failure value before it
		// exits; the broker may add rollback detail only after that durable
		// proof exists.  Future drivers may store the precise terminal value.
		return proof == "failed" || proof == status
	default:
		return false
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
