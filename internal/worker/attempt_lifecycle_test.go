package worker

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/owainlewis/factory/internal/protocol"
)

func TestLeaseRenewalScheduleDispersesAttempts(t *testing.T) {
	interval := 10 * time.Second
	seen := map[int64]bool{}
	for index := 0; index < 10; index++ {
		delay := leaseRenewalDelay("attempt-"+string(rune('a'+index)), interval, 0)
		if delay < 7*time.Second || delay > interval {
			t.Fatalf("delay %s outside 70-100%% interval", delay)
		}
		seen[int64(delay/(interval/10))] = true
	}
	if len(seen) < 3 {
		t.Fatalf("renewals occupied %d time buckets; want at least 3", len(seen))
	}
	wantStableDelay := leaseRenewalDelay("stable-attempt", interval, 0)
	gotStableDelay := leaseRenewalDelay("stable-attempt", interval, 0)
	if gotStableDelay != wantStableDelay {
		t.Fatal("renewal phase is not stable")
	}
}

func TestLeaseRenewalRetryStaysWithinLeaseBudget(t *testing.T) {
	for retry := 1; retry < 10; retry++ {
		delay := leaseRenewalDelay("retry-attempt", 2*time.Second, retry)
		if delay < 1400*time.Millisecond || delay > 2*time.Second {
			t.Fatalf("retry %d delay %s outside retry interval", retry, delay)
		}
	}
}

func TestLeaseRenewalRetryLeavesTimeForHeartbeatNearExpiry(t *testing.T) {
	delay := leaseRenewalRetryDelay("near-expiry", 2*time.Second, 1,
		1500*time.Millisecond, time.Second)
	if delay > 500*time.Millisecond {
		t.Fatalf("retry delay %s leaves no heartbeat budget before lease expiry", delay)
	}
	if delay != 500*time.Millisecond {
		t.Fatalf("retry delay = %s, want remaining lease budget of 500ms", delay)
	}

	if delay := leaseRenewalRetryDelay("expired-budget", 2*time.Second, 1,
		900*time.Millisecond, time.Second); delay != 0 {
		t.Fatalf("retry delay = %s, want immediate retry", delay)
	}
}

func TestBuildPromptIncludesGrammaticalSafetyInstruction(t *testing.T) {
	claim := protocol.Claim{
		Task: protocol.Task{
			Title:       "Fix the prompt",
			Description: "Keep the change focused.",
		},
		Repository: protocol.Repository{RemoteIdentity: "github.com/owainlewis/factory"},
	}
	value := worktree{Branch: "factory/123456789abc-abcdef123456", BaseBranch: "main"}

	want := "You are running in a Factory managed Git worktree.\n" +
		"Work only on the assigned task and repository. Preserve unrelated changes and do not touch Factory state or unrelated worktrees. " +
		"Do not switch, create, rename, or delete branches or worktrees. Complete and verify the task before returning a concise result.\n\n" +
		"Task title: Fix the prompt\n" +
		"Repository: github.com/owainlewis/factory\n" +
		"Working branch: factory/123456789abc-abcdef123456\n" +
		"Target base branch: main\n\n" +
		"Keep the change focused."

	if got := buildPrompt(claim, value); got != want {
		t.Fatalf("buildPrompt() = %q, want %q", got, want)
	}
}

func TestMaterializeAttachmentsVerifiesAndWritesBeforeRuntime(t *testing.T) {
	content := []byte("screenshot bytes")
	digestBytes := sha256.Sum256(content)
	digest := hex.EncodeToString(digestBytes[:])
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Factory-Lease-Token") != "lease" {
			t.Error("missing lease token")
		}
		w.Header().Set("X-Content-SHA256", digest)
		_, _ = w.Write(content)
	}))
	defer server.Close()
	manager := &Manager{client: newClient(server.URL, server.Client())}
	claim := protocol.Claim{Attempt: protocol.Attempt{ID: "attempt"}, Attachments: []protocol.TaskAttachment{{ID: "attachment", Name: "screen.png", Size: int64(len(content)), SHA256: digest}}}
	worktree := t.TempDir()
	if err := manager.materializeAttachments(context.Background(), claim, "lease", worktree); err != nil {
		t.Fatal(err)
	}
	got, err := os.ReadFile(filepath.Join(worktree, ".factory", "attachments", "attachment-screen.png"))
	if err != nil {
		t.Fatal(err)
	}
	if string(got) != string(content) {
		t.Fatalf("content = %q", got)
	}
}

func TestMaterializeAttachmentsKeepsDuplicateNamesDistinct(t *testing.T) {
	content := []byte("same bytes")
	digestBytes := sha256.Sum256(content)
	digest := hex.EncodeToString(digestBytes[:])
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("X-Content-SHA256", digest)
		_, _ = w.Write(content)
	}))
	defer server.Close()
	manager := &Manager{client: newClient(server.URL, server.Client())}
	claim := protocol.Claim{Attempt: protocol.Attempt{ID: "attempt"}, Attachments: []protocol.TaskAttachment{
		{ID: "first", Name: "screen.png", Size: int64(len(content)), SHA256: digest},
		{ID: "second", Name: "screen.png", Size: int64(len(content)), SHA256: digest},
	}}
	worktree := t.TempDir()
	if err := manager.materializeAttachments(context.Background(), claim, "lease", worktree); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"first-screen.png", "second-screen.png"} {
		if _, err := os.Stat(filepath.Join(worktree, ".factory", "attachments", name)); err != nil {
			t.Errorf("%s: %v", name, err)
		}
	}
}

func TestBuildPromptListsMaterializedAttachments(t *testing.T) {
	claim := protocol.Claim{Task: protocol.Task{Title: "Inspect", Description: "Use evidence"}, Repository: protocol.Repository{RemoteIdentity: "github.com/example/repo"}, Attachments: []protocol.TaskAttachment{{ID: "attachment", Name: "screen.png"}}}
	prompt := buildPrompt(claim, worktree{Branch: "factory/test", BaseBranch: "main"})
	if !strings.Contains(prompt, ".factory/attachments/attachment-screen.png") {
		t.Fatalf("prompt = %q", prompt)
	}
}
