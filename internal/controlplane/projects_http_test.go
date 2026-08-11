package controlplane

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/owainlewis/factory/internal/protocol"
)

func projectHTTPServer(t *testing.T) *httptest.Server {
	t.Helper()
	store := newTestStore(t)
	return httptest.NewServer(NewHandler(store, slog.New(slog.NewTextHandler(io.Discard, nil))))
}

func postProjectJSON(t *testing.T, server *httptest.Server, body any) (*http.Response, []byte) {
	t.Helper()
	encoded, err := json.Marshal(body)
	if err != nil {
		t.Fatal(err)
	}
	request, err := http.NewRequest(http.MethodPost, server.URL+"/api/v1/projects", bytes.NewReader(encoded))
	if err != nil {
		t.Fatal(err)
	}
	request.Header.Set("Content-Type", "application/json")
	response, err := server.Client().Do(request)
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	responseBody, err := io.ReadAll(response.Body)
	if err != nil {
		t.Fatal(err)
	}
	return response, responseBody
}

func TestProjectHTTPContractRejectsClientExecutorAndCommandFields(t *testing.T) {
	server := projectHTTPServer(t)
	defer server.Close()
	response, body := postProjectJSON(t, server, factoryProjectRequest())
	if response.StatusCode != http.StatusCreated {
		t.Fatalf("create status=%d body=%s", response.StatusCode, body)
	}
	if !bytes.Contains(body, []byte(`"executor_group":"factory"`)) || bytes.Contains(body, []byte("super-secret-value")) {
		t.Fatalf("unsafe response: %s", body)
	}

	var raw map[string]any
	encoded, _ := json.Marshal(factoryProjectRequest())
	_ = json.Unmarshal(encoded, &raw)
	for _, field := range []string{"executor_group", "command"} {
		raw[field] = "root"
		response, body = postProjectJSON(t, server, raw)
		if response.StatusCode != http.StatusBadRequest || !strings.Contains(string(body), "malformed_json") {
			t.Fatalf("field %s accepted: status=%d body=%s", field, response.StatusCode, body)
		}
		delete(raw, field)
	}
}

func TestProjectHTTPCannotForgeReadiness(t *testing.T) {
	store := newTestStore(t)
	project := createFactoryProject(t, store)
	registerReadyProjectWorker(t, store, project)
	provisionTestProjectSecrets(t, store, project, "GITHUB_TOKEN=value\n")
	server := httptest.NewServer(NewHandler(store, slog.New(slog.NewTextHandler(io.Discard, nil))))
	defer server.Close()

	forged := []byte(`{"commit_sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","branch_access":true,"executor_ready":true,"checks":{"secret-scan":true,"static-typecheck":true,"tests":true,"build":true}}`)
	request, err := http.NewRequest(http.MethodPut, server.URL+"/api/v1/projects/"+project.ID+"/gate-results", bytes.NewReader(forged))
	if err != nil {
		t.Fatal(err)
	}
	request.Header.Set("Content-Type", "application/json")
	response, err := server.Client().Do(request)
	if err != nil {
		t.Fatal(err)
	}
	response.Body.Close()
	if response.StatusCode < http.StatusBadRequest {
		t.Fatalf("untrusted readiness endpoint accepted forged results: status=%d", response.StatusCode)
	}

	readiness, err := store.ProjectReadiness(context.Background(), project.ID, "staging")
	if err != nil {
		t.Fatal(err)
	}
	if readiness.Ready {
		t.Fatalf("client-forged fields opened readiness: %+v", readiness)
	}
	releaseBody := []byte(`{"commit_sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}`)
	response, err = server.Client().Post(server.URL+"/api/v1/projects/"+project.ID+"/environments/staging/release", "application/json", bytes.NewReader(releaseBody))
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusConflict {
		body, _ := io.ReadAll(response.Body)
		t.Fatalf("forged readiness did not leave release closed: status=%d body=%s", response.StatusCode, body)
	}
}

func TestWorkerVerificationOpensReadinessOnlyForExistingMainBranchHeadAndExactHosts(t *testing.T) {
	store := newTestStore(t)
	project := createFactoryProject(t, store)
	registerReadyProjectWorker(t, store, project)
	provisionTestProjectSecrets(t, store, project, "GITHUB_TOKEN=value\n")
	server := httptest.NewServer(NewHandler(store, slog.New(slog.NewTextHandler(io.Discard, nil))))
	defer server.Close()

	verification := protocol.ProjectVerificationRequest{
		Environment: "staging", MainBranch: "main", BranchHeadSHA: projectSHA, CommitSHA: projectSHA,
		Checks:   map[string]bool{"secret-scan": true, "static-typecheck": true, "tests": true, "build": true},
		WebHosts: []string{"factory.timafen.com"},
	}
	endpoint := server.URL + "/api/v1/workers/project-ready-worker/projects/" + project.ID + "/verification"
	for _, mutate := range []func(*protocol.ProjectVerificationRequest){
		func(value *protocol.ProjectVerificationRequest) { value.MainBranch = "missing" },
		func(value *protocol.ProjectVerificationRequest) { value.BranchHeadSHA = strings.Repeat("b", 40) },
		func(value *protocol.ProjectVerificationRequest) { value.WebHosts = []string{"example.com"} },
	} {
		candidate := verification
		candidate.WebHosts = append([]string(nil), verification.WebHosts...)
		mutate(&candidate)
		body, _ := json.Marshal(candidate)
		response, err := server.Client().Post(endpoint, "application/json", bytes.NewReader(body))
		if err != nil {
			t.Fatal(err)
		}
		response.Body.Close()
		if response.StatusCode < http.StatusBadRequest {
			t.Fatalf("invalid verification accepted: %+v status=%d", candidate, response.StatusCode)
		}
	}
	body, _ := json.Marshal(verification)
	response, err := server.Client().Post(endpoint, "application/json", bytes.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	response.Body.Close()
	if response.StatusCode != http.StatusNoContent {
		t.Fatalf("trusted worker verification status=%d", response.StatusCode)
	}
	readiness, err := store.ProjectReadiness(context.Background(), project.ID, "staging")
	if err != nil || !readiness.Ready {
		t.Fatalf("worker verification did not open readiness: %+v err=%v", readiness, err)
	}
}
