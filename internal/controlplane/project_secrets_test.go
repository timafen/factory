package controlplane

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/owainlewis/factory/internal/protocol"
)

func provisionTestProjectSecrets(t *testing.T, store *Store, project protocol.Project, body string) string {
	t.Helper()
	store.projectSecretRoot = t.TempDir()
	store.projectSecretOwnerUID = uint32(os.Getuid())
	store.projectSecretGroupID = func(string) (uint32, error) { return uint32(os.Getgid()), nil }
	directory := filepath.Join(store.projectSecretRoot, project.ID)
	if err := os.MkdirAll(directory, 0o750); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(directory, "staging.env")
	if err := os.WriteFile(path, []byte(body), 0o640); err != nil {
		t.Fatal(err)
	}
	return path
}

func allPassingGates() protocol.ProjectGateResultRequest {
	return protocol.ProjectGateResultRequest{CommitSHA: projectSHA, BranchAccess: true, ExecutorReady: true, Checks: map[string]bool{"secret-scan": true, "static-typecheck": true, "tests": true, "build": true}}
}

func TestProjectReadinessRequiresSecretsAndEveryGateOnOneSHA(t *testing.T) {
	store := newTestStore(t)
	project := createFactoryProject(t, store)
	if err := store.RecordProjectGateResults(context.Background(), project.ID, allPassingGates()); err != nil {
		t.Fatal(err)
	}
	path := provisionTestProjectSecrets(t, store, project, "GITHUB_TOKEN=super-secret-value\n")
	readiness, err := store.ProjectReadiness(context.Background(), project.ID, "staging")
	if err != nil || !readiness.Ready {
		t.Fatalf("ready = %+v, %v", readiness, err)
	}
	body, _ := json.Marshal(readiness)
	if strings.Contains(string(body), "super-secret-value") {
		t.Fatal("secret value leaked in readiness JSON")
	}
	if _, err := store.db.Exec(`UPDATE project_gate_results SET commit_sha=? WHERE project_id=? AND gate='build'`, strings.Repeat("b", 40), project.ID); err != nil {
		t.Fatal(err)
	}
	readiness, err = store.ProjectReadiness(context.Background(), project.ID, "staging")
	if err != nil || readiness.Ready {
		t.Fatalf("mixed SHA readiness = %+v, %v", readiness, err)
	}
	if err := store.requireProjectRoutingReady(context.Background(), project.RepositoryID); errorCode(err) != "project_not_ready" {
		t.Fatalf("routing error = %v", err)
	}
	if err := os.Chmod(path, 0o644); err != nil {
		t.Fatal(err)
	}
	statuses, err := store.ResolveProjectSecrets(project, "staging")
	if err == nil || len(statuses) != 1 || statuses[0].Name != "GITHUB_TOKEN" {
		t.Fatalf("unsafe secret file = %+v, %v", statuses, err)
	}
}

func TestProjectReadinessExpiresFailClosed(t *testing.T) {
	store := newTestStore(t)
	now := time.Date(2026, 8, 10, 12, 0, 0, 0, time.UTC)
	store.now = func() time.Time { return now }
	project := createFactoryProject(t, store)
	provisionTestProjectSecrets(t, store, project, "GITHUB_TOKEN=value\n")
	if err := store.RecordProjectGateResults(context.Background(), project.ID, allPassingGates()); err != nil {
		t.Fatal(err)
	}
	now = now.Add(25 * time.Hour)
	readiness, err := store.ProjectReadiness(context.Background(), project.ID, "staging")
	if err != nil || readiness.Ready {
		t.Fatalf("stale readiness = %+v, %v", readiness, err)
	}
}
