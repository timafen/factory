//go:build darwin || dragonfly || freebsd || linux || netbsd || openbsd || solaris

package worker

import (
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"strconv"
	"syscall"
	"time"

	"golang.org/x/sys/unix"
)

const interruptedTestHelperEnv = "FACTORY_WORKER_INTERRUPTION_HELPER"

// runInterruptedTestHelper is deliberately test-only. It models the process
// which owns fake tools during a test run, including cleanup after interruption.
func runInterruptedTestHelper() {
	root := os.Getenv("FACTORY_WORKER_INTERRUPTION_ROOT")
	var err error
	if root == "" {
		root, err = os.MkdirTemp("", "factory-worker-interrupted-")
	}
	if err != nil {
		os.Exit(2)
	}
	defer os.RemoveAll(root)
	started := filepath.Join(root, "first.started")
	pidFile := filepath.Join(root, "pid")
	pgidFile := filepath.Join(root, "pgid")
	tool := filepath.Join(root, "gh")
	script := "#!/bin/sh\nset -eu\necho $$ > \"$1\"\ntouch \"$2\"\ntrap '' TERM INT HUP\nwhile :; do sleep 1; done\n"
	if err := os.WriteFile(tool, []byte(script), 0700); err != nil {
		os.Exit(2)
	}
	command := exec.Command(tool, pidFile, started)
	configureNewProcessGroup(command)
	if err := command.Start(); err != nil {
		os.Exit(2)
	}
	pgid := command.Process.Pid
	done := waitCommand(command)
	_ = os.WriteFile(pgidFile, []byte(strconv.Itoa(pgid)), 0600)
	_ = os.WriteFile(filepath.Join(root, "root"), []byte(root), 0600)
	_ = os.WriteFile(filepath.Join(root, "ready"), nil, 0600)
	cleanup := func(sig unix.Signal) {
		_ = signalProcessGroup(pgid, sig)
		deadline := time.Now().Add(time.Second)
		for time.Now().Before(deadline) && processGroupAlive(pgid) {
			time.Sleep(20 * time.Millisecond)
		}
		if processGroupAlive(pgid) {
			_ = forceStopStartedProcessGroup(pgid)
		}
		select {
		case <-done:
		case <-time.After(time.Second):
			_ = command.Process.Kill()
			select {
			case <-done:
			case <-time.After(time.Second):
			}
		}
	}
	signals := make(chan os.Signal, 1)
	signal.Notify(signals, syscall.SIGTERM, syscall.SIGINT, syscall.SIGHUP)
	select {
	case sig := <-signals:
		cleanup(signalToUnix(sig))
	case <-done:
	}
}

func signalToUnix(signal os.Signal) unix.Signal { return unix.Signal(signal.(syscall.Signal)) }

func waitCommand(command *exec.Cmd) <-chan struct{} {
	done := make(chan struct{})
	go func() { _ = command.Wait(); close(done) }()
	return done
}
