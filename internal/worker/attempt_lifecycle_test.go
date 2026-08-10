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

	"github.com/owainlewis/factory/internal/protocol"
)

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
		"Server browser: use `/opt/factory-data/bin/factory-worker browser -output <file.png> https://staging-automation.tarser.net/<path>` when visual verification of the approved stand is useful. Other origins are blocked.\n\n" +
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
