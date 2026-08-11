package worker

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestRunCommandSkipsConcurrentDuplicate(t *testing.T) {
	directory := t.TempDir()
	alias := filepath.Join(t.TempDir(), "same-directory")
	if err := os.Symlink(directory, alias); err != nil {
		t.Fatalf("create directory alias: %v", err)
	}
	ready := filepath.Join(directory, "ready")
	firstDone := make(chan error, 1)
	go func() {
		_, _, err := testCommand(context.Background(), directory, "wait", ready)
		firstDone <- err
	}()
	waitForFile(t, ready)

	_, _, err := testCommand(context.Background(), alias, "wait", ready)
	if !errors.Is(err, ErrCommandAlreadyRunning) {
		t.Fatalf("duplicate command error = %v, want ErrCommandAlreadyRunning", err)
	}
	if err := <-firstDone; err != nil {
		t.Fatalf("first command: %v", err)
	}
}

func TestRunCommandAllowsRepeatAfterCompletion(t *testing.T) {
	directory := t.TempDir()
	ready := filepath.Join(directory, "ready")
	if _, _, err := testCommand(context.Background(), directory, "wait", ready); err != nil {
		t.Fatalf("first command: %v", err)
	}
	if _, _, err := testCommand(context.Background(), directory, "wait", ready); err != nil {
		t.Fatalf("repeat after completion: %v", err)
	}
}

func TestRunCommandAllowsDifferentCommandsInParallel(t *testing.T) {
	directory := t.TempDir()
	firstReady := filepath.Join(directory, "first-ready")
	secondReady := filepath.Join(directory, "second-ready")
	firstDone := make(chan error, 1)
	secondDone := make(chan error, 1)
	go func() {
		_, _, err := testCommand(context.Background(), directory, "wait", firstReady)
		firstDone <- err
	}()
	waitForFile(t, firstReady)
	go func() {
		_, _, err := testCommand(context.Background(), directory, "wait", secondReady)
		secondDone <- err
	}()
	waitForFile(t, secondReady)
	if err := <-firstDone; err != nil {
		t.Fatalf("first command: %v", err)
	}
	if err := <-secondDone; err != nil {
		t.Fatalf("second command: %v", err)
	}
}

func TestRunCommandReleasesLockAfterFailure(t *testing.T) {
	directory := t.TempDir()
	if _, _, err := testCommand(context.Background(), directory, "fail"); err == nil || errors.Is(err, ErrCommandAlreadyRunning) {
		t.Fatalf("failed command error = %v, want process failure", err)
	}
	if _, _, err := testCommand(context.Background(), directory, "fail"); err == nil || errors.Is(err, ErrCommandAlreadyRunning) {
		t.Fatalf("retry after failure error = %v, want process failure", err)
	}
}

func testCommand(ctx context.Context, directory string, arguments ...string) ([]byte, []byte, error) {
	return runCommand(ctx, os.Args[0], directory, 1024, append([]string{"-test.run=TestWorkerCommandHelper", "--"}, arguments...)...)
}

func TestWorkerCommandHelper(t *testing.T) {
	separator := -1
	for index, argument := range os.Args {
		if argument == "--" {
			separator = index
			break
		}
	}
	if separator == -1 || separator+1 >= len(os.Args) {
		return
	}
	action := os.Args[separator+1]
	if action == "wait" {
		if separator+2 >= len(os.Args) {
			os.Exit(2)
		}
		if err := os.WriteFile(os.Args[separator+2], []byte("ready"), 0o600); err != nil {
			os.Exit(2)
		}
		time.Sleep(150 * time.Millisecond)
		os.Exit(0)
	}
	if action == "fail" {
		os.Exit(7)
	}
}

func waitForFile(t *testing.T, path string) {
	t.Helper()
	deadline := time.Now().Add(time.Second)
	for time.Now().Before(deadline) {
		if _, err := os.Stat(path); err == nil {
			return
		}
		time.Sleep(5 * time.Millisecond)
	}
	t.Fatalf("timed out waiting for %s", path)
}
