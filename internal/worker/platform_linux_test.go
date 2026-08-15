//go:build linux

package worker

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestLinuxProcessIdentitySurvivesExec(t *testing.T) {
	ready := filepath.Join(t.TempDir(), "ready")
	proceed := filepath.Join(t.TempDir(), "proceed")
	command := exec.Command(
		"/bin/sh", "-c",
		`printf ready > "$1"; while [ ! -e "$2" ]; do sleep 0.01; done; exec sleep 30`,
		"factory-identity-test", ready, proceed,
	)
	configureNewProcessGroup(command)
	if err := command.Start(); err != nil {
		t.Fatal(err)
	}
	defer func() {
		_ = command.Process.Kill()
		_ = command.Wait()
	}()

	waitFor(t, 3*time.Second, func() bool {
		_, err := os.Stat(ready)
		return err == nil
	})
	before, err := processIdentity(command.Process.Pid)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(proceed, []byte("go"), 0o600); err != nil {
		t.Fatal(err)
	}
	waitFor(t, 3*time.Second, func() bool {
		body, readErr := os.ReadFile(fmt.Sprintf("/proc/%d/comm", command.Process.Pid))
		return readErr == nil && strings.TrimSpace(string(body)) == "sleep"
	})
	after, err := processIdentity(command.Process.Pid)
	if err != nil {
		t.Fatal(err)
	}
	if before != after {
		t.Fatalf("Linux process identity changed across exec: before=%q after=%q", before, after)
	}
}

func TestLinuxVerifyProcessIdentityAcceptsLegacyValue(t *testing.T) {
	command := exec.Command("sleep", "30")
	if err := command.Start(); err != nil {
		t.Fatal(err)
	}
	defer func() {
		_ = command.Process.Kill()
		_ = command.Wait()
	}()

	legacy, err := legacyProcessIdentity(command.Process.Pid)
	if err != nil {
		t.Fatal(err)
	}
	if err := verifyProcessIdentity(command.Process.Pid, legacy); err != nil {
		t.Fatalf("legacy process identity was not accepted during upgrade: %v", err)
	}
}
