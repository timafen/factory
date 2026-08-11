package controlplane

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
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
	return httptest.NewServer(NewHandlerWithWorkerBootstrapCredential(store, slog.New(slog.NewTextHandler(io.Discard, nil)), testWorkerBootstrapCredential))
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

func registerProjectWorkerHTTP(t *testing.T, server *httptest.Server, workerID string, registration protocol.WorkerRegistration) string {
	t.Helper()
	body, err := json.Marshal(registration)
	if err != nil {
		t.Fatal(err)
	}
	request, err := http.NewRequest(http.MethodPut, server.URL+"/api/v1/workers/"+workerID, bytes.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set(protocol.WorkerBootstrapCredentialHeader, testWorkerBootstrapCredential)
	response, err := server.Client().Do(request)
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		responseBody, _ := io.ReadAll(response.Body)
		t.Fatalf("register worker %s status=%d body=%s", workerID, response.StatusCode, responseBody)
	}
	credential := response.Header.Get(protocol.WorkerCredentialHeader)
	if credential == "" {
		t.Fatalf("registration did not issue a credential for %s", workerID)
	}
	return credential
}

func postProjectVerification(t *testing.T, server *httptest.Server, endpoint, credential string, verification protocol.ProjectVerificationRequest) *http.Response {
	t.Helper()
	body, err := json.Marshal(verification)
	if err != nil {
		t.Fatal(err)
	}
	request, err := http.NewRequest(http.MethodPost, endpoint, bytes.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	request.Header.Set("Content-Type", "application/json")
	if credential != "" {
		request.Header.Set(protocol.WorkerCredentialHeader, credential)
	}
	response, err := server.Client().Do(request)
	if err != nil {
		t.Fatal(err)
	}
	return response
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

func TestWorkerCredentialIssuanceRejectsProxiedRegistrationBeforeMutation(t *testing.T) {
	store := newTestStore(t)
	project := createFactoryProject(t, store)
	server := httptest.NewServer(NewHandlerWithWorkerBootstrapCredential(store, slog.New(slog.NewTextHandler(io.Discard, nil)), testWorkerBootstrapCredential))
	defer server.Close()
	body, err := json.Marshal(projectWorkerRegistration("proxied-worker", project))
	if err != nil {
		t.Fatal(err)
	}
	request, err := http.NewRequest(http.MethodPut, server.URL+"/api/v1/workers/proxied-worker", bytes.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Forwarded-For", "203.0.113.10")
	response, err := server.Client().Do(request)
	if err != nil {
		t.Fatal(err)
	}
	response.Body.Close()
	if response.StatusCode != http.StatusForbidden || response.Header.Get(protocol.WorkerCredentialHeader) != "" {
		t.Fatalf("proxied registration status=%d credential=%q", response.StatusCode, response.Header.Get(protocol.WorkerCredentialHeader))
	}
	if _, err := store.Worker(context.Background(), "proxied-worker"); !errors.Is(err, ErrNotFound) {
		t.Fatalf("proxied registration mutated worker state: %v", err)
	}
}

func TestWorkerCredentialRotationRecoversAfterRegistrationResponseIsLost(t *testing.T) {
	store := newTestStore(t)
	server := httptest.NewServer(NewHandlerWithWorkerBootstrapCredential(store, slog.New(slog.NewTextHandler(io.Discard, nil)), testWorkerBootstrapCredential))
	defer server.Close()
	registration := protocol.WorkerRegistration{
		Name: "retrying-worker", Runtime: protocol.RuntimeCodex, RuntimeVersion: "test",
		Capacity: 1, Health: "healthy", CapacityHandoffVersion: 1,
	}

	// The first response is deliberately treated as lost: its credential is
	// never persisted by the worker.
	lostCredential := registerProjectWorkerHTTP(t, server, "retrying-worker", registration)
	retryCredential := registerProjectWorkerHTTP(t, server, "retrying-worker", registration)
	if retryCredential == lostCredential {
		t.Fatal("registration retry did not rotate the lost credential")
	}
	if err := store.AuthenticateWorkerCredential(context.Background(), "retrying-worker", lostCredential); errorCode(err) != "worker_authentication_failed" {
		t.Fatalf("lost credential remained valid: %v", err)
	}
	if err := store.AuthenticateWorkerCredential(context.Background(), "retrying-worker", retryCredential); err != nil {
		t.Fatalf("credential returned by retry is unusable: %v", err)
	}
	confirmed, err := store.RefreshWorkerCredential(context.Background(), "retrying-worker", retryCredential)
	if err != nil || confirmed != "" {
		t.Fatalf("persisted credential was rotated instead of confirmed: credential=%q err=%v", confirmed, err)
	}
}

func TestHostileLocalReregistrationCannotRotateCredentialOrForgeVerification(t *testing.T) {
	store := newTestStore(t)
	project := createFactoryProject(t, store)
	server := httptest.NewServer(NewHandlerWithWorkerBootstrapCredential(store, slog.New(slog.NewTextHandler(io.Discard, nil)), testWorkerBootstrapCredential))
	defer server.Close()
	registration := projectWorkerRegistration("protected-worker", project)
	credential := registerProjectWorkerHTTP(t, server, "protected-worker", registration)

	body, err := json.Marshal(registration)
	if err != nil {
		t.Fatal(err)
	}
	hostile, err := http.NewRequest(http.MethodPut, server.URL+"/api/v1/workers/protected-worker", bytes.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	hostile.Header.Set("Content-Type", "application/json")
	response, err := server.Client().Do(hostile)
	if err != nil {
		t.Fatal(err)
	}
	response.Body.Close()
	if response.StatusCode != http.StatusUnauthorized || response.Header.Get(protocol.WorkerCredentialHeader) != "" {
		t.Fatalf("hostile registration status=%d credential=%q", response.StatusCode, response.Header.Get(protocol.WorkerCredentialHeader))
	}
	if err := store.AuthenticateWorkerCredential(context.Background(), "protected-worker", credential); err != nil {
		t.Fatalf("hostile registration invalidated the legitimate credential: %v", err)
	}

	verification := protocol.ProjectVerificationRequest{
		Environment: "staging", MainBranch: "main", BranchHeadSHA: projectSHA, CommitSHA: projectSHA,
		Checks: map[string]bool{"secret-scan": true, "static-typecheck": true, "tests": true, "build": true},
	}
	endpoint := server.URL + "/api/v1/workers/protected-worker/projects/" + project.ID + "/verification"
	response = postProjectVerification(t, server, endpoint, "", verification)
	response.Body.Close()
	if response.StatusCode != http.StatusUnauthorized {
		t.Fatalf("forged verification status=%d", response.StatusCode)
	}
	readiness, err := store.ProjectReadiness(context.Background(), project.ID, "staging")
	if err != nil || readiness.Ready {
		t.Fatalf("hostile sequence changed readiness: %+v err=%v", readiness, err)
	}
}

func TestProjectHTTPCannotForgeReadiness(t *testing.T) {
	store := newTestStore(t)
	project := createFactoryProject(t, store)
	registerReadyProjectWorker(t, store, project)
	provisionTestProjectSecrets(t, store, project, "GITHUB_TOKEN=value\n")
	server := httptest.NewServer(NewHandlerWithWorkerBootstrapCredential(store, slog.New(slog.NewTextHandler(io.Discard, nil)), testWorkerBootstrapCredential))
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
	server := httptest.NewServer(NewHandlerWithWorkerBootstrapCredential(store, slog.New(slog.NewTextHandler(io.Discard, nil)), testWorkerBootstrapCredential))
	defer server.Close()
	credential := registerProjectWorkerHTTP(t, server, "project-ready-worker", projectWorkerRegistration("project-ready-worker", project))
	foreignCredential := registerProjectWorkerHTTP(t, server, "other-project-worker", projectWorkerRegistration("other-project-worker", project))

	verification := protocol.ProjectVerificationRequest{
		Environment: "staging", MainBranch: "main", BranchHeadSHA: projectSHA, CommitSHA: projectSHA,
		Checks:   map[string]bool{"secret-scan": true, "static-typecheck": true, "tests": true, "build": true},
		WebHosts: []string{"factory.timafen.com"},
	}
	endpoint := server.URL + "/api/v1/workers/project-ready-worker/projects/" + project.ID + "/verification"
	for name, candidateCredential := range map[string]string{
		"missing credential": "",
		"foreign credential": foreignCredential,
	} {
		t.Run(name, func(t *testing.T) {
			response := postProjectVerification(t, server, endpoint, candidateCredential, verification)
			response.Body.Close()
			if response.StatusCode != http.StatusUnauthorized {
				t.Fatalf("untrusted verification status=%d", response.StatusCode)
			}
			readiness, err := store.ProjectReadiness(context.Background(), project.ID, "staging")
			if err != nil || readiness.Ready {
				t.Fatalf("untrusted verification changed readiness: %+v err=%v", readiness, err)
			}
		})
	}
	for _, mutate := range []func(*protocol.ProjectVerificationRequest){
		func(value *protocol.ProjectVerificationRequest) { value.MainBranch = "missing" },
		func(value *protocol.ProjectVerificationRequest) { value.BranchHeadSHA = strings.Repeat("b", 40) },
		func(value *protocol.ProjectVerificationRequest) { value.WebHosts = []string{"example.com"} },
	} {
		candidate := verification
		candidate.WebHosts = append([]string(nil), verification.WebHosts...)
		mutate(&candidate)
		response := postProjectVerification(t, server, endpoint, credential, candidate)
		response.Body.Close()
		if response.StatusCode < http.StatusBadRequest {
			t.Fatalf("invalid verification accepted: %+v status=%d", candidate, response.StatusCode)
		}
	}
	response := postProjectVerification(t, server, endpoint, credential, verification)
	response.Body.Close()
	if response.StatusCode != http.StatusNoContent {
		t.Fatalf("trusted worker verification status=%d", response.StatusCode)
	}
	readiness, err := store.ProjectReadiness(context.Background(), project.ID, "staging")
	if err != nil || !readiness.Ready {
		t.Fatalf("worker verification did not open readiness: %+v err=%v", readiness, err)
	}
}
