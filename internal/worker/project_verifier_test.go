package worker

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	"github.com/owainlewis/factory/internal/protocol"
)

func TestVerifyProjectBindsReportToRemoteMainHeadAndPublishesExactPolicy(t *testing.T) {
	root := t.TempDir()
	remote := filepath.Join(root, "remote.git")
	repository := filepath.Join(root, "repository")
	runVerifierGit(t, "init", "--bare", remote)
	runVerifierGit(t, "init", repository)
	runVerifierGit(t, "-C", repository, "config", "user.email", "factory@example.com")
	runVerifierGit(t, "-C", repository, "config", "user.name", "Factory Test")
	if err := os.WriteFile(filepath.Join(repository, "README.md"), []byte("verified\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	runVerifierGit(t, "-C", repository, "add", "README.md")
	runVerifierGit(t, "-C", repository, "commit", "-m", "verified")
	runVerifierGit(t, "-C", repository, "branch", "-M", "main")
	runVerifierGit(t, "-C", repository, "remote", "add", "origin", remote)
	runVerifierGit(t, "-C", repository, "push", "-u", "origin", "main")
	sha := strings.TrimSpace(runVerifierGit(t, "-C", repository, "rev-parse", "HEAD"))

	var published protocol.ProjectVerificationRequest
	server := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		switch request.Method + " " + request.URL.Path {
		case "GET /api/v1/projects/project-1":
			_ = json.NewEncoder(response).Encode(protocol.Project{
				ID: "project-1", RemoteIdentity: "file://" + filepath.ToSlash(remote), MainBranch: "main",
			})
		default:
			if request.Method != http.MethodPost || !strings.Contains(request.URL.Path, "/verification") {
				http.NotFound(response, request)
				return
			}
			if err := json.NewDecoder(request.Body).Decode(&published); err != nil {
				t.Fatal(err)
			}
			response.WriteHeader(http.StatusNoContent)
		}
	}))
	defer server.Close()

	dataDirectory := filepath.Join(root, "worker-data")
	if err := os.MkdirAll(dataDirectory, 0o700); err != nil {
		t.Fatal(err)
	}
	config := Config{Server: server.URL, Name: "verifier", Runtime: protocol.RuntimeCodex, MaxConcurrent: 1, DataDirectory: dataDirectory, Repositories: map[string]RepositoryConfig{"factory": {Path: repository}}}
	reportPath := filepath.Join(root, "report.json")
	writeVerifierReport(t, reportPath, projectCheckReport{CommitSHA: sha, Checks: map[string]bool{"secret-scan": true, "static-typecheck": true, "tests": true, "build": true}, WebHosts: []string{"factory.timafen.com"}})
	if err := VerifyProject(context.Background(), config, ProjectVerificationOptions{ProjectID: "project-1", RepositoryKey: "factory", ReportPath: reportPath}); err != nil {
		t.Fatal(err)
	}
	if published.MainBranch != "main" || published.BranchHeadSHA != sha || published.CommitSHA != sha || len(published.WebHosts) != 1 || published.WebHosts[0] != "factory.timafen.com" {
		t.Fatalf("published verification = %+v", published)
	}

	writeVerifierReport(t, reportPath, projectCheckReport{CommitSHA: strings.Repeat("b", 40), Checks: map[string]bool{"secret-scan": true, "static-typecheck": true, "tests": true, "build": true}, WebHosts: []string{"factory.timafen.com"}})
	if err := VerifyProject(context.Background(), config, ProjectVerificationOptions{ProjectID: "project-1", RepositoryKey: "factory", ReportPath: reportPath}); err == nil || !strings.Contains(err.Error(), "not the configured main branch head") {
		t.Fatalf("off-branch report error = %v", err)
	}
}

func runVerifierGit(t *testing.T, arguments ...string) string {
	t.Helper()
	output, err := exec.Command("git", arguments...).CombinedOutput()
	if err != nil {
		t.Fatalf("git %v: %v: %s", arguments, err, output)
	}
	return string(output)
}

func writeVerifierReport(t *testing.T, path string, report projectCheckReport) {
	t.Helper()
	body, err := json.Marshal(report)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, body, 0o600); err != nil {
		t.Fatal(err)
	}
}
