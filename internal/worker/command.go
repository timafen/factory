package worker

import (
	"bytes"
	"context"
	"crypto/sha256"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"golang.org/x/sys/unix"
)

var ErrCommandAlreadyRunning = errors.New("an identical worker command is already running")

const commandLockDirectory = "factory-worker-command-locks"

type limitBuffer struct {
	mu        sync.Mutex
	bytes     []byte
	limit     int
	truncated bool
}

func newLimitBuffer(limit int) *limitBuffer {
	return &limitBuffer{limit: limit}
}

func (buffer *limitBuffer) Write(value []byte) (int, error) {
	buffer.mu.Lock()
	defer buffer.mu.Unlock()
	available := buffer.limit - len(buffer.bytes)
	if available > 0 {
		count := len(value)
		if count > available {
			count = available
		}
		buffer.bytes = append(buffer.bytes, value[:count]...)
	}
	if len(value) > available {
		buffer.truncated = true
	}
	return len(value), nil
}

func (buffer *limitBuffer) String() string {
	buffer.mu.Lock()
	defer buffer.mu.Unlock()
	return string(append([]byte(nil), buffer.bytes...))
}

func (buffer *limitBuffer) Bytes() []byte {
	buffer.mu.Lock()
	defer buffer.mu.Unlock()
	return append([]byte(nil), buffer.bytes...)
}

func (buffer *limitBuffer) Truncated() bool {
	buffer.mu.Lock()
	defer buffer.mu.Unlock()
	return buffer.truncated
}

func runCommand(ctx context.Context, executable, directory string, outputLimit int, arguments ...string) ([]byte, []byte, error) {
	lock, err := acquireCommandLock(executable, directory, arguments)
	if err != nil {
		return nil, nil, err
	}
	defer lock.Close()

	command := exec.Command(executable, arguments...)
	command.Dir = directory
	configureNewProcessGroup(command)
	stdout := newLimitBuffer(outputLimit)
	stderr := newLimitBuffer(outputLimit)
	command.Stdout = stdout
	command.Stderr = stderr
	if err := command.Start(); err != nil {
		return nil, nil, err
	}
	pid := command.Process.Pid
	identity, identityErr := processIdentity(pid)
	done := make(chan error, 1)
	go func() {
		done <- command.Wait()
	}()
	select {
	case err := <-done:
		return stdout.Bytes(), stderr.Bytes(), err
	case <-ctx.Done():
		if identityErr == nil {
			_ = stopOwnedProcessGroup(pid, identity, time.Second)
		} else {
			_ = forceStopStartedProcessGroup(pid)
		}
		<-done
		return stdout.Bytes(), stderr.Bytes(), ctx.Err()
	}
}

// acquireCommandLock keeps only one exact command in one canonical directory
// running at a time. Advisory locks are released by the kernel if a worker
// crashes, so a stale lock file never prevents a later retry.
func acquireCommandLock(executable, directory string, arguments []string) (*os.File, error) {
	canonicalDirectory, err := canonicalCommandDirectory(directory)
	if err != nil {
		return nil, err
	}
	keyParts := append([]string{executable, canonicalDirectory}, arguments...)
	digest := sha256.Sum256([]byte(strings.Join(keyParts, "\x00")))
	lockDirectory := filepath.Join(os.TempDir(), commandLockDirectory)
	if err := os.MkdirAll(lockDirectory, 0o700); err != nil {
		return nil, fmt.Errorf("create worker command lock directory: %w", err)
	}
	lock, err := os.OpenFile(filepath.Join(lockDirectory, fmt.Sprintf("%x.lock", digest)), os.O_CREATE|os.O_RDWR, 0o600)
	if err != nil {
		return nil, fmt.Errorf("open worker command lock: %w", err)
	}
	if err := unix.Flock(int(lock.Fd()), unix.LOCK_EX|unix.LOCK_NB); err != nil {
		_ = lock.Close()
		if errors.Is(err, unix.EWOULDBLOCK) || errors.Is(err, unix.EAGAIN) {
			return nil, fmt.Errorf("%w: %s in %s", ErrCommandAlreadyRunning, executable, canonicalDirectory)
		}
		return nil, fmt.Errorf("lock worker command: %w", err)
	}
	return lock, nil
}

func canonicalCommandDirectory(directory string) (string, error) {
	if directory == "" {
		var err error
		directory, err = os.Getwd()
		if err != nil {
			return "", fmt.Errorf("get worker command directory: %w", err)
		}
	}
	absolute, err := filepath.Abs(directory)
	if err != nil {
		return "", fmt.Errorf("make worker command directory absolute: %w", err)
	}
	canonical, err := filepath.EvalSymlinks(absolute)
	if err != nil {
		return "", fmt.Errorf("canonicalize worker command directory: %w", err)
	}
	return canonical, nil
}

func commandFailure(action string, stdout, stderr []byte, err error) error {
	detail := bytes.TrimSpace(stderr)
	if len(detail) == 0 {
		detail = bytes.TrimSpace(stdout)
	}
	if len(detail) == 0 {
		return fmt.Errorf("%s: %w", action, err)
	}
	return fmt.Errorf("%s: %w: %s", action, err, detail)
}
