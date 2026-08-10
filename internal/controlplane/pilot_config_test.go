package controlplane

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"

	"github.com/owainlewis/factory/internal/protocol"
)

func validPilotSettings() protocol.PilotSettings {
	stages := make([]protocol.PilotStage, 0, len(pilotStages))
	costs := map[string]float64{}
	for _, stage := range pilotStages {
		stages = append(stages, protocol.PilotStage{Workflow: stage, Workers: protocol.PilotStageWorkers{Low: "worker-1", Medium: "worker-1", High: "worker-1"}})
		costs[stage] = 1
	}
	return protocol.PilotSettings{
		Note: "keep this", Enabled: true, PollSeconds: 10, TimeoutSeconds: 60, AutoMerge: true, AutoAnswer: true,
		MaxStageAttempts: 2, AllowAnyWorker: false, AllowedWorkers: []string{"worker-1"}, MaxParallelSubtasks: 2, MaxParallelWorks: 4,
		DayCapUSD: 20, DeployStagingCmd: "deploy staging", DeployFactoryCmd: "deploy factory", OwnerChatURL: "https://example.test/chat", OwnerUIURL: "https://example.test/ui",
		Stages: stages, SkipStagesForLow: []string{}, StoppedPipelines: []string{}, StageBaseUSD: costs,
		ComplexityFactor: map[string]float64{"low": 1, "medium": 2, "high": 3}, WorkCapUSD: map[string]float64{"low": 2, "medium": 4, "high": 8},
		NtfyTopic: "factory", NtfyServer: "https://ntfy.sh", NtfyOwnerTopic: "owner",
		BrainChain: []protocol.PilotBrain{{CLI: "codex", Model: "gpt", Provider: "openai", Note: "preserve"}},
	}
}

func writePilotFixture(t *testing.T, settings protocol.PilotSettings) (*PilotConfigStore, string) {
	t.Helper()
	path := filepath.Join(t.TempDir(), "config.json")
	body, err := json.Marshal(settings)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, body, 0o600); err != nil {
		t.Fatal(err)
	}
	return NewPilotConfigStore(path), path
}

func TestPilotConfigStorePreservesNotesAndRejectsConflict(t *testing.T) {
	store, path := writePilotFixture(t, validPilotSettings())
	first, err := store.Read()
	if err != nil {
		t.Fatal(err)
	}
	first.Settings.PollSeconds = 15
	saved, err := store.Write(first.Version, first.Settings)
	if err != nil {
		t.Fatal(err)
	}
	if saved.Version == first.Version || saved.Settings.Note != "keep this" || saved.Settings.BrainChain[0].Note != "preserve" || saved.Settings.DeployFactoryCmd != "deploy factory" {
		t.Fatalf("saved response = %#v", saved)
	}
	before, _ := os.ReadFile(path)
	if _, err := store.Write(first.Version, first.Settings); err == nil {
		t.Fatal("stale version was accepted")
	}
	after, _ := os.ReadFile(path)
	if string(after) != string(before) {
		t.Fatal("conflict changed config")
	}
}

func TestPilotConfigValidationWorkerPolicy(t *testing.T) {
	settings := validPilotSettings()
	settings.Stages[3].Workers = protocol.PilotStageWorkers{Low: "unknown", Medium: "worker-1", High: "worker-1"}
	if _, err := validatePilotSettings(settings); err == nil {
		t.Fatal("strict unknown worker was accepted")
	}
	settings.AllowAnyWorker = true
	warnings, err := validatePilotSettings(settings)
	if err != nil {
		t.Fatal(err)
	}
	if len(warnings) != 1 || warnings[0] != "Unknown worker: unknown" {
		t.Fatalf("warnings = %#v", warnings)
	}
}

func TestPilotConfigProjectProvidersAreStrictAndPreserved(t *testing.T) {
	settings := validPilotSettings()
	settings.ProjectProviders = []protocol.ProjectProvider{
		{RemoteIdentity: "github.com/acme/shop", Type: "trade"},
		{RemoteIdentity: "github.com/acme/factory", Type: "factory"},
	}
	if _, err := validatePilotSettings(settings); err != nil {
		t.Fatal(err)
	}
	store, _ := writePilotFixture(t, settings)
	current, err := store.Read()
	if err != nil || len(current.Settings.ProjectProviders) != 2 {
		t.Fatalf("round trip = %#v, %v", current.Settings.ProjectProviders, err)
	}
	settings.ProjectProviders[0].Type = "shell"
	if _, err := validatePilotSettings(settings); err == nil {
		t.Fatal("unknown executable provider type was accepted")
	}
}

func TestPilotConfigRejectsReasoningDowngradeInHigherTier(t *testing.T) {
	settings := validPilotSettings()
	settings.AllowAnyWorker = true
	settings.Stages[2].Workers = protocol.PilotStageWorkers{
		Low: "codex-terra-medium", Medium: "codex-sol-medium", High: "codex-sol-low",
	}

	if _, err := validatePilotSettings(settings); err == nil {
		t.Fatal("higher tier with lower reasoning effort was accepted")
	}

	settings.Stages[2].Workers.High = "codex-sol-high"
	if _, err := validatePilotSettings(settings); err != nil {
		t.Fatalf("monotonic reasoning tiers were rejected: %v", err)
	}
}

func TestUpdatePilotSettingsRequiresCompleteSchema(t *testing.T) {
	body := []byte(`{"version":"v","settings":{"enabled":true}}`)
	var request protocol.UpdatePilotSettingsRequest
	if err := json.Unmarshal(body, &request); err == nil {
		t.Fatal("incomplete settings schema was accepted")
	}
}

func TestPilotConfigStoreRejectsSymlinkAndInvalidJSON(t *testing.T) {
	dir := t.TempDir()
	target := filepath.Join(dir, "target")
	link := filepath.Join(dir, "config.json")
	if err := os.WriteFile(target, []byte("{}"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(target, link); err != nil {
		t.Fatal(err)
	}
	if _, err := NewPilotConfigStore(link).Read(); err == nil {
		t.Fatal("symlink was accepted")
	}
	if err := os.Remove(link); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(link, []byte("{"), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := NewPilotConfigStore(link).Read(); err == nil {
		t.Fatal("invalid JSON was accepted")
	}
}

func TestPilotConfigExampleMatchesServerSchema(t *testing.T) {
	example, err := os.ReadFile(filepath.Join("..", "..", "pilot", "config.example.json"))
	if err != nil {
		t.Fatal(err)
	}
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(example, &fields); err != nil {
		t.Fatal(err)
	}
	if got := string(fields["respect_host_load"]); got != "true" {
		t.Fatalf("example respect_host_load = %s, want true", got)
	}

	path := filepath.Join(t.TempDir(), "config.json")
	if err := os.WriteFile(path, example, 0o600); err != nil {
		t.Fatal(err)
	}
	store := NewPilotConfigStore(path)
	current, err := store.Read()
	if err != nil {
		t.Fatalf("strict decoder rejected config.example.json: %v", err)
	}
	if !current.Settings.RespectHostLoad {
		t.Fatal("example respect_host_load was not decoded as true")
	}
	if current.Settings.MaxParallelWorks != 4 {
		t.Fatalf("example max_parallel_works = %d, want 4", current.Settings.MaxParallelWorks)
	}

	current.Settings.RespectHostLoad = false
	if _, err := store.Write(current.Version, current.Settings); err != nil {
		t.Fatal(err)
	}
	saved, err := store.Read()
	if err != nil {
		t.Fatal(err)
	}
	if saved.Settings.RespectHostLoad {
		t.Fatal("explicit respect_host_load=false was not preserved")
	}
	savedBody, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Contains(savedBody, []byte(`"respect_host_load": false`)) {
		t.Fatal("saved config omitted explicit respect_host_load=false")
	}

	delete(fields, "respect_host_load")
	delete(fields, "max_parallel_works")
	legacy, err := json.Marshal(fields)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, legacy, 0o600); err != nil {
		t.Fatal(err)
	}
	legacySettings, err := store.Read()
	if err != nil {
		t.Fatalf("legacy config was rejected: %v", err)
	}
	if !legacySettings.Settings.RespectHostLoad {
		t.Fatal("legacy config did not receive respect_host_load=true")
	}
	if legacySettings.Settings.MaxParallelWorks != 4 {
		t.Fatalf("legacy max_parallel_works = %d, want 4", legacySettings.Settings.MaxParallelWorks)
	}

	fields["unknown_config_field"] = json.RawMessage("true")
	unknown, err := json.Marshal(fields)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, unknown, 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := store.Read(); err == nil {
		t.Fatal("strict decoder accepted an unknown config field")
	}
}

func TestPilotSettingsHTTPInitializesKnownWorkerIDsAndConflicts(t *testing.T) {
	settings := validPilotSettings()
	settings.AllowAnyWorker = true
	settings.AllowedWorkers = nil
	pilot, _ := writePilotFixture(t, settings)
	store := newTestStore(t)
	server := httptest.NewServer(NewHandlerWithPilotConfig(store, slog.Default(), NewAutomationService(store, slog.Default()), pilot))
	defer server.Close()
	register := protocol.WorkerRegistration{Name: "Known", WorkerVersion: "test", RuntimeVersion: "test", Capacity: 1, Health: "healthy"}
	body, _ := json.Marshal(register)
	request, _ := http.NewRequest(http.MethodPut, server.URL+"/api/v1/workers/worker-1", bytes.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	response, err := server.Client().Do(request)
	if err != nil {
		t.Fatal(err)
	}
	if response.StatusCode != http.StatusOK {
		t.Fatalf("register status %d", response.StatusCode)
	}
	response.Body.Close()
	response, err = server.Client().Get(server.URL + "/api/v1/settings/pilot")
	if err != nil {
		t.Fatal(err)
	}
	if response.StatusCode != http.StatusOK {
		t.Fatalf("GET status %d", response.StatusCode)
	}
	var got protocol.PilotSettingsResponse
	if err := json.NewDecoder(response.Body).Decode(&got); err != nil {
		t.Fatal(err)
	}
	response.Body.Close()
	if len(got.Settings.AllowedWorkers) != 1 || got.Settings.AllowedWorkers[0] != "worker-1" || !got.Settings.AllowAnyWorker {
		t.Fatalf("settings = %#v", got.Settings)
	}
	put, _ := json.Marshal(protocol.UpdatePilotSettingsRequest{Version: "stale", Settings: got.Settings})
	request, _ = http.NewRequest(http.MethodPut, server.URL+"/api/v1/settings/pilot", bytes.NewReader(put))
	request.Header.Set("Content-Type", "application/json")
	response, err = server.Client().Do(request)
	if err != nil {
		t.Fatal(err)
	}
	if response.StatusCode != http.StatusConflict {
		t.Fatalf("PUT status %d", response.StatusCode)
	}
	response.Body.Close()
}

func TestReviveWorkRemovesOnlyExactPauseAndIsIdempotent(t *testing.T) {
	settings := validPilotSettings()
	settings.StoppedPipelines = []string{"Работа", "Работа рядом"}
	store, path := writePilotFixture(t, settings)

	first, err := store.Revive("Работа")
	if err != nil || first.State != "reviving" {
		t.Fatalf("first revive = %#v, %v", first, err)
	}
	if _, err := store.Revive("Работа"); err != nil {
		t.Fatalf("idempotent revive: %v", err)
	}
	current, err := store.Read()
	if err != nil {
		t.Fatal(err)
	}
	if got := current.Settings.StoppedPipelines; len(got) != 1 || got[0] != "Работа рядом" {
		t.Fatalf("stopped pipelines = %#v", got)
	}
	if _, err := os.Stat(filepath.Join(filepath.Dir(path), "revive", reviveSignalName("Работа"))); err != nil {
		t.Fatalf("revive signal: %v", err)
	}
}

func TestReviveWorkRemainsIdempotentAfterPilotAcknowledgesSignal(t *testing.T) {
	settings := validPilotSettings()
	settings.StoppedPipelines = []string{"Работа"}
	store, _ := writePilotFixture(t, settings)
	if _, err := store.Revive("Работа"); err != nil {
		t.Fatal(err)
	}
	if err := os.Rename(store.reviveSignalPath("Работа"), store.reviveReceiptPath("Работа")); err != nil {
		t.Fatal(err)
	}

	if got, err := store.Revive("Работа"); err != nil || got.State != "reviving" {
		t.Fatalf("repeat after acknowledgement = %#v, %v", got, err)
	}
}

func TestReviveWorkCreatesFreshSignalAfterAcknowledgedWorkGivesUpAgain(t *testing.T) {
	settings := validPilotSettings()
	settings.StoppedPipelines = []string{"Работа"}
	store, _ := writePilotFixture(t, settings)
	if _, err := store.Revive("Работа"); err != nil {
		t.Fatal(err)
	}
	if err := os.Rename(store.reviveSignalPath("Работа"), store.reviveReceiptPath("Работа")); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(store.stallPath(), []byte(`{"Работа":{"why":"give_up"}}`), 0o600); err != nil {
		t.Fatal(err)
	}

	if got, err := store.Revive("Работа"); err != nil || got.State != "reviving" {
		t.Fatalf("revive after repeated give_up = %#v, %v", got, err)
	}
	if _, err := os.Stat(store.reviveSignalPath("Работа")); err != nil {
		t.Fatalf("fresh signal after repeated give_up: %v", err)
	}
	if _, err := os.Stat(store.reviveReceiptPath("Работа")); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("stale receipt still exists: %v", err)
	}
}

func TestReviveWorkCreatesFreshSignalWhenSameWorkStopsAgain(t *testing.T) {
	settings := validPilotSettings()
	settings.StoppedPipelines = []string{"Работа"}
	store, _ := writePilotFixture(t, settings)
	if _, err := store.Revive("Работа"); err != nil {
		t.Fatal(err)
	}
	if err := os.Rename(store.reviveSignalPath("Работа"), store.reviveReceiptPath("Работа")); err != nil {
		t.Fatal(err)
	}
	current, err := store.Read()
	if err != nil {
		t.Fatal(err)
	}
	current.Settings.StoppedPipelines = []string{"Работа"}
	if _, err := store.Write(current.Version, current.Settings); err != nil {
		t.Fatal(err)
	}

	if _, err := store.Revive("Работа"); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(store.reviveSignalPath("Работа")); err != nil {
		t.Fatalf("fresh signal: %v", err)
	}
}

func TestReviveWorkConcurrentSignalsAreNotLost(t *testing.T) {
	settings := validPilotSettings()
	settings.StoppedPipelines = []string{"Первая", "Вторая"}
	store, path := writePilotFixture(t, settings)
	var wg sync.WaitGroup
	for _, work := range []string{"Первая", "Вторая"} {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if _, err := store.Revive(work); err != nil {
				t.Errorf("revive %q: %v", work, err)
			}
		}()
	}
	wg.Wait()
	for _, work := range []string{"Первая", "Вторая"} {
		if _, err := os.Stat(filepath.Join(filepath.Dir(path), "revive", reviveSignalName(work))); err != nil {
			t.Fatalf("signal for %q: %v", work, err)
		}
	}
}

func TestReviveWorkSupportsMaximumLengthUnicodeName(t *testing.T) {
	work := strings.Repeat("я", 200)
	settings := validPilotSettings()
	settings.StoppedPipelines = []string{work}
	store, path := writePilotFixture(t, settings)

	if _, err := store.Revive(work); err != nil {
		t.Fatalf("revive 200-character work: %v", err)
	}
	signalPath := filepath.Join(filepath.Dir(path), "revive", reviveSignalName(work))
	body, err := os.ReadFile(signalPath)
	if err != nil {
		t.Fatalf("read revive signal: %v", err)
	}
	if string(body) != work {
		t.Fatalf("signal body does not preserve work name")
	}
	if len(filepath.Base(signalPath)) != sha256.Size*2 {
		t.Fatalf("signal filename length = %d", len(filepath.Base(signalPath)))
	}
}

func TestRevivedMaximumLengthTitleIsAcceptedByRealControlPlane(t *testing.T) {
	fixture := newHTTPFixture(t)
	worker := registerHTTPWorker(t, fixture, workerA, "factory", "github.com/owainlewis/factory", 1)
	workflow := createTestWorkflow(t, fixture.store, "revive-implement", "Implement", "Continue the existing work.")
	work := strings.Repeat("я", 200)

	response := fixture.request(http.MethodPost, "/api/v1/tasks", "application/json", "", protocol.CreateTaskRequest{
		RequestKey: "revive-maximum-title", Title: work, Context: "Работа оживлена; продолжить со следующего этапа.",
		WorkerID: worker.ID, RepositoryID: worker.Repositories[0].ID, TimeoutSeconds: 60,
		WorkflowRevisionID: workflow.Workflow.CurrentRevision.ID,
	})
	requireStatus(t, response, http.StatusCreated)
	created := decodeResponse[protocol.TaskDetail](t, response)
	if created.Task.Title != work || created.Workflow == nil || created.Workflow.Title != "Implement" {
		t.Fatalf("revived task lost title or stage metadata: %#v", created)
	}
}

func reviveSignalName(work string) string {
	sum := sha256.Sum256([]byte(work))
	return hex.EncodeToString(sum[:])
}

func TestReviveWorkSignalFailureLeavesWorkStopped(t *testing.T) {
	settings := validPilotSettings()
	settings.StoppedPipelines = []string{"Работа"}
	store, path := writePilotFixture(t, settings)
	if err := os.WriteFile(filepath.Join(filepath.Dir(path), "revive"), []byte("not a directory"), 0o600); err != nil {
		t.Fatal(err)
	}

	if _, err := store.Revive("Работа"); err == nil {
		t.Fatal("revive succeeded despite signal creation failure")
	}
	current, err := store.Read()
	if err != nil {
		t.Fatal(err)
	}
	if got := current.Settings.StoppedPipelines; len(got) != 1 || got[0] != "Работа" {
		t.Fatalf("stopped pipelines changed after signal failure: %#v", got)
	}
}

func TestReviveWorkAcceptsStuckAndRejectsUnknown(t *testing.T) {
	store, path := writePilotFixture(t, validPilotSettings())
	stall := []byte(`{"Застрявшая":{"why":"give_up"},"Другая":{"why":"nudged"}}`)
	if err := os.WriteFile(filepath.Join(filepath.Dir(path), "stalled.json"), stall, 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := store.Revive("Застрявшая"); err != nil {
		t.Fatalf("stuck revive: %v", err)
	}
	if _, err := store.Revive("Неизвестная"); err == nil {
		t.Fatal("unknown work was accepted")
	}
}

func TestReviveWorkReportsInvalidStallState(t *testing.T) {
	store, path := writePilotFixture(t, validPilotSettings())
	if err := os.WriteFile(filepath.Join(filepath.Dir(path), "stalled.json"), []byte(`{"Работа":`), 0o600); err != nil {
		t.Fatal(err)
	}

	_, err := store.Revive("Работа")
	var serviceErr *ServiceError
	if !errors.As(err, &serviceErr) {
		t.Fatalf("error = %v, want ServiceError", err)
	}
	if serviceErr.Code != "pilot_state_invalid" || serviceErr.Message != "pilot stall state contains invalid JSON" || serviceErr.Status != http.StatusServiceUnavailable {
		t.Fatalf("service error = %#v", serviceErr)
	}
	if serviceErr.Unwrap() == nil {
		t.Fatal("JSON decoding error was not preserved")
	}
}

func TestReviveWorkHTTPValidatesPathAndReturnsStatus(t *testing.T) {
	settings := validPilotSettings()
	settings.StoppedPipelines = []string{"Работа с пробелом"}
	pilot, _ := writePilotFixture(t, settings)
	store := newTestStore(t)
	server := httptest.NewServer(NewHandlerWithPilotConfig(store, slog.Default(), NewAutomationService(store, slog.Default()), pilot))
	defer server.Close()

	response, err := server.Client().Post(server.URL+"/api/v1/works/"+url.PathEscape("Работа с пробелом")+"/revive", "application/json", bytes.NewReader([]byte(`{}`)))
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		t.Fatalf("status = %d", response.StatusCode)
	}
	var got ReviveWorkResponse
	if err := json.NewDecoder(response.Body).Decode(&got); err != nil || got.Work != "Работа с пробелом" || got.State != "reviving" {
		t.Fatalf("response = %#v, %v", got, err)
	}
	if err := os.Rename(pilot.reviveSignalPath("Работа с пробелом"), pilot.reviveReceiptPath("Работа с пробелом")); err != nil {
		t.Fatal(err)
	}
	repeat, err := server.Client().Post(server.URL+"/api/v1/works/"+url.PathEscape("Работа с пробелом")+"/revive", "application/json", bytes.NewReader([]byte(`{}`)))
	if err != nil {
		t.Fatal(err)
	}
	repeat.Body.Close()
	if repeat.StatusCode != http.StatusOK {
		t.Fatalf("repeat status after pilot acknowledgement = %d", repeat.StatusCode)
	}
}

func TestReviveWorkHTTPRejectsCrossOriginAndNonJSON(t *testing.T) {
	settings := validPilotSettings()
	settings.StoppedPipelines = []string{"Работа"}
	pilot, _ := writePilotFixture(t, settings)
	store := newTestStore(t)
	server := httptest.NewServer(NewHandlerWithPilotConfig(store, slog.Default(), NewAutomationService(store, slog.Default()), pilot))
	defer server.Close()
	for _, test := range []struct {
		origin, contentType string
		status              int
	}{
		{"https://evil.example", "application/json", http.StatusForbidden},
		{"", "application/x-www-form-urlencoded", http.StatusUnsupportedMediaType},
	} {
		req, err := http.NewRequest(http.MethodPost, server.URL+"/api/v1/works/"+url.PathEscape("Работа")+"/revive", bytes.NewReader([]byte(`{}`)))
		if err != nil {
			t.Fatal(err)
		}
		req.Header.Set("Content-Type", test.contentType)
		req.Header.Set("Origin", test.origin)
		response, err := server.Client().Do(req)
		if err != nil {
			t.Fatal(err)
		}
		response.Body.Close()
		if response.StatusCode != test.status {
			t.Fatalf("status = %d, want %d", response.StatusCode, test.status)
		}
	}
}
