package worker

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/owainlewis/factory/internal/protocol"
)

func TestConcurrentClaudeHealthChecksWaitForIdenticalProbe(t *testing.T) {
	gitExecutable, claudeExecutable, githubExecutable, state := newHealthTestExecutables(t, claudeWaitScript)
	results := make(chan health, 2)
	go func() {
		results <- checkHealth(context.Background(), gitExecutable, protocol.RuntimeClaudeCode, claudeExecutable, githubExecutable, nil)
	}()
	waitForFile(t, state.ready)
	go func() {
		results <- checkHealth(context.Background(), gitExecutable, protocol.RuntimeClaudeCode, claudeExecutable, githubExecutable, nil)
	}()

	time.Sleep(3 * healthCommandRetryDelay)
	if err := os.WriteFile(state.release, []byte("release"), 0o600); err != nil {
		t.Fatalf("release first Claude probe: %v", err)
	}
	for index := 0; index < 2; index++ {
		select {
		case result := <-results:
			if result.State != "healthy" || result.Error != nil {
				t.Fatalf("health result = %#v, want healthy", result)
			}
			if result.RuntimeVersion != "Claude Code 1.0" {
				t.Fatalf("runtime version = %q", result.RuntimeVersion)
			}
		case <-time.After(2 * time.Second):
			t.Fatal("concurrent health checks did not finish")
		}
	}
	if starts := countHealthTestStarts(t, state.starts); starts != 2 {
		t.Fatalf("Claude version process starts = %d, want 2", starts)
	}
	if _, err := os.Stat(state.overlap); !os.IsNotExist(err) {
		t.Fatalf("identical Claude probes overlapped; marker error = %v", err)
	}
}

func TestClaudeHealthCheckPreservesCommandFailure(t *testing.T) {
	gitExecutable, claudeExecutable, githubExecutable, state := newHealthTestExecutables(t, claudeFailureScript)
	result := checkHealth(context.Background(), gitExecutable, protocol.RuntimeClaudeCode, claudeExecutable, githubExecutable, nil)
	if result.State != "unhealthy" || result.Error == nil {
		t.Fatalf("health result = %#v, want unhealthy command failure", result)
	}
	if starts := countHealthTestStarts(t, state.starts); starts != 1 {
		t.Fatalf("failed Claude process starts = %d, want 1", starts)
	}
}

func TestClaudeHealthCheckLockWaitHonorsTimeout(t *testing.T) {
	gitExecutable, claudeExecutable, githubExecutable, state := newHealthTestExecutables(t, claudeWaitScript)
	firstDone := make(chan health, 1)
	go func() {
		firstDone <- checkHealth(context.Background(), gitExecutable, protocol.RuntimeClaudeCode, claudeExecutable, githubExecutable, nil)
	}()
	waitForFile(t, state.ready)

	ctx, cancel := context.WithTimeout(context.Background(), 4*healthCommandRetryDelay)
	started := time.Now()
	result := checkHealth(ctx, gitExecutable, protocol.RuntimeClaudeCode, claudeExecutable, githubExecutable, nil)
	cancel()
	if result.State != "unhealthy" || result.Error == nil {
		t.Fatalf("timed out health result = %#v, want unhealthy", result)
	}
	if elapsed := time.Since(started); elapsed > time.Second {
		t.Fatalf("lock wait took %v, want at most 1s", elapsed)
	}
	if starts := countHealthTestStarts(t, state.starts); starts != 1 {
		t.Fatalf("Claude version process starts before release = %d, want 1", starts)
	}

	if err := os.WriteFile(state.release, []byte("release"), 0o600); err != nil {
		t.Fatalf("release first Claude probe: %v", err)
	}
	select {
	case first := <-firstDone:
		if first.State != "healthy" || first.Error != nil {
			t.Fatalf("first health result = %#v, want healthy", first)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("first health check did not finish after release")
	}
}

type healthTestState struct {
	ready   string
	release string
	starts  string
	overlap string
}

const claudeWaitScript = `
if [ "$1" = "--version" ]; then
  if ! mkdir "$active" 2>/dev/null; then
    : > "$overlap"
    exit 91
  fi
  echo start >> "$starts"
  : > "$ready"
  while [ ! -e "$release" ]; do sleep 0.01; done
  rmdir "$active"
  echo 'Claude Code 1.0'
  exit 0
fi
if [ "$1" = "auth" ]; then
  echo '{"loggedIn":true}'
  exit 0
fi
exit 2
`

const claudeFailureScript = `
if [ "$1" = "--version" ]; then
  echo start >> "$starts"
  exit 7
fi
exit 2
`

func newHealthTestExecutables(t *testing.T, claudeBody string) (string, string, string, healthTestState) {
	t.Helper()
	directory := t.TempDir()
	state := healthTestState{
		ready:   filepath.Join(directory, "ready"),
		release: filepath.Join(directory, "release"),
		starts:  filepath.Join(directory, "starts"),
		overlap: filepath.Join(directory, "overlap"),
	}
	t.Cleanup(func() { _ = os.WriteFile(state.release, []byte("release"), 0o600) })
	gitExecutable := writeHealthTestExecutable(t, directory, "git", `
if [ "$1" = "--version" ]; then echo 'git version 2.0'; exit 0; fi
exit 2
`)
	claudeExecutable := writeHealthTestExecutable(t, directory, "claude", fmt.Sprintf(
		"active=%q\nready=%q\nrelease=%q\nstarts=%q\noverlap=%q\n%s",
		filepath.Join(directory, "active"), state.ready, state.release, state.starts, state.overlap, claudeBody,
	))
	githubExecutable := writeHealthTestExecutable(t, directory, "gh", `exit 0`)
	return gitExecutable, claudeExecutable, githubExecutable, state
}

func writeHealthTestExecutable(t *testing.T, directory, name, body string) string {
	t.Helper()
	path := filepath.Join(directory, name)
	if err := os.WriteFile(path, []byte("#!/bin/sh\n"+body+"\n"), 0o700); err != nil {
		t.Fatalf("write fake %s executable: %v", name, err)
	}
	return path
}

func countHealthTestStarts(t *testing.T, path string) int {
	t.Helper()
	content, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read process starts: %v", err)
	}
	return len(strings.Fields(string(content)))
}
