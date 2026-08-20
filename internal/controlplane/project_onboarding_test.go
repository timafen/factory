package controlplane

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"reflect"
	"testing"
	"time"

	"github.com/owainlewis/factory/internal/protocol"
)

func TestProjectOnboardingPersistenceRoundTripIsDisabledAndInert(t *testing.T) {
	store := newTestStore(t)
	repository, _, err := store.CreateManagedRepository(context.Background(), protocol.CreateManagedRepositoryRequest{RemoteIdentity: "github.com/timafen/tarser-operations"})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := store.SetManagedRepositoryEnabled(context.Background(), repository.ID, false); err != nil {
		t.Fatal(err)
	}
	checkedAt := time.Date(2026, 8, 19, 9, 30, 0, 0, time.UTC)
	service := NewProjectOnboardingService(t.TempDir(), store)
	service.now = func() time.Time { return checkedAt }
	input := validProjectOnboardingInput()
	input.Commands.Install.Argv = []string{"composer", "install", "--no-interaction"}
	input.Commands.Build.Argv = []string{"npm", "run", "build"}

	saved, err := service.Put(context.Background(), repository.ID, input)
	if err != nil {
		t.Fatal(err)
	}
	reloaded, err := service.Get(context.Background(), repository.ID)
	if err != nil {
		t.Fatal(err)
	}
	if saved.Enabled || reloaded.Enabled || !reflect.DeepEqual(reloaded.ProjectOnboardingInput, input) {
		t.Fatalf("round trip saved=%#v reloaded=%#v", saved, reloaded)
	}
	if reloaded.ReadinessState != "" || reloaded.LastPreflightReceipt != nil || reloaded.LastTrialReceipt != nil || len(reloaded.DiscoveredInstructionFiles) != 0 {
		t.Fatalf("server-owned execution fields were set: %#v", reloaded)
	}
	managed, err := store.ManagedRepository(context.Background(), repository.ID)
	if err != nil || managed.Enabled {
		t.Fatalf("repository routing changed: %#v, err %v", managed, err)
	}
}

func TestProjectOnboardingRejectsSaveWhileRoutingEnabledWithoutChangingRouting(t *testing.T) {
	store := newTestStore(t)
	repository, _, err := store.CreateManagedRepository(context.Background(), protocol.CreateManagedRepositoryRequest{RemoteIdentity: "github.com/timafen/assistant"})
	if err != nil {
		t.Fatal(err)
	}
	service := NewProjectOnboardingService(t.TempDir(), store)
	if _, err := service.Put(context.Background(), repository.ID, validProjectOnboardingInput()); !serviceErrorCode(err, "onboarding_routing_enabled") {
		t.Fatalf("save with routing enabled error = %v", err)
	}
	managed, err := store.ManagedRepository(context.Background(), repository.ID)
	if err != nil || !managed.Enabled {
		t.Fatalf("repository routing changed: %#v, err %v", managed, err)
	}
}

func TestProjectOnboardingHTTPGetPutAndRejectsServerOwnedFields(t *testing.T) {
	store := newTestStore(t)
	repository, _, err := store.CreateManagedRepository(context.Background(), protocol.CreateManagedRepositoryRequest{RemoteIdentity: "github.com/timafen/tarser-operations"})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := store.SetManagedRepositoryEnabled(context.Background(), repository.ID, false); err != nil {
		t.Fatal(err)
	}
	service := NewProjectOnboardingService(t.TempDir(), store)
	mux := http.NewServeMux()
	registerProjectOnboardingRoutes(mux, service)

	input := validProjectOnboardingInput()
	body, err := json.Marshal(input)
	if err != nil {
		t.Fatal(err)
	}
	response := serveOnboarding(t, mux, http.MethodPut, "/api/v1/repositories/"+repository.ID+"/onboarding", body, "")
	if response.Code != http.StatusOK {
		t.Fatalf("PUT status = %d, body %s", response.Code, response.Body.String())
	}
	response = serveOnboarding(t, mux, http.MethodGet, "/api/v1/repositories/"+repository.ID+"/onboarding", nil, "")
	if response.Code != http.StatusOK {
		t.Fatalf("GET status = %d, body %s", response.Code, response.Body.String())
	}
	var card ProjectOnboardingCard
	if err := json.NewDecoder(response.Body).Decode(&card); err != nil || card.Enabled || !reflect.DeepEqual(card.ProjectOnboardingInput, input) {
		t.Fatalf("GET card = %#v, err %v", card, err)
	}

	for _, injected := range []string{`"unknown":"value"`, `"enabled":true`, `"readiness_state":"READY"`, `"last_preflight_receipt":{}`} {
		candidate := append([]byte(nil), body[:len(body)-1]...)
		candidate = append(candidate, []byte(","+injected+"}")...)
		response = serveOnboarding(t, mux, http.MethodPut, "/api/v1/repositories/"+repository.ID+"/onboarding", candidate, "")
		if response.Code != http.StatusBadRequest {
			t.Fatalf("server-owned field %s status = %d, body %s", injected, response.Code, response.Body.String())
		}
	}
}

func TestProjectOnboardingMutationUsesExistingSameOriginBoundary(t *testing.T) {
	store := newTestStore(t)
	repository, _, err := store.CreateManagedRepository(context.Background(), protocol.CreateManagedRepositoryRequest{RemoteIdentity: "github.com/timafen/timstruck_laravel"})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := store.SetManagedRepositoryEnabled(context.Background(), repository.ID, false); err != nil {
		t.Fatal(err)
	}
	mux := http.NewServeMux()
	service := NewProjectOnboardingService(t.TempDir(), store)
	registerProjectOnboardingRoutes(mux, service)
	body, _ := json.Marshal(validProjectOnboardingInput())
	response := serveOnboarding(t, mux, http.MethodPut, "/api/v1/repositories/"+repository.ID+"/onboarding", body, "https://attacker.example")
	if response.Code != http.StatusForbidden {
		t.Fatalf("cross-origin mutation status = %d, body %s", response.Code, response.Body.String())
	}
	if _, err := service.Get(context.Background(), repository.ID); err != ErrNotFound {
		t.Fatalf("rejected mutation persisted a card: %v", err)
	}
}

func serveOnboarding(t *testing.T, handler http.Handler, method, path string, body []byte, origin string) *httptest.ResponseRecorder {
	t.Helper()
	request := httptest.NewRequest(method, path, bytes.NewReader(body))
	request.Host = "localhost"
	request.RemoteAddr = "127.0.0.1:12345"
	if method == http.MethodPut {
		request.Header.Set("Content-Type", "application/json")
	}
	if origin != "" {
		request.Header.Set("Origin", origin)
	}
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	return response
}

func validProjectOnboardingInput() ProjectOnboardingInput {
	return ProjectOnboardingInput{
		ProjectID: "tarser", Name: "Tarser", DefaultBranch: "main",
		AllowedPaths: []string{"docs"}, RequiredInstructionFiles: []string{"AGENTS.md"},
		Commands:       ProjectOnboardingCommands{WorkingDirectory: "src", Test: ProjectOnboardingCommand{Argv: []string{"git", "diff", "--check"}}},
		TimeoutSeconds: 120,
		Runtime:        ProjectOnboardingRuntime{OS: "linux", Architecture: "amd64", Toolchain: "git", ToolchainVersion: "2"},
		Environment:    ProjectOnboardingEnvironment{Network: "NONE", Secrets: "NONE"},
		Policy:         ProjectOnboardingPolicy{Write: "NONE", PullRequest: "DISABLED", Release: "DISABLED"},
	}
}

func serviceErrorCode(err error, code string) bool {
	service, ok := err.(*ServiceError)
	return ok && service.Code == code
}
