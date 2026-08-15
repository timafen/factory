package controlplane

import (
	"bytes"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
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
		Note: "keep this", Enabled: true, PollSeconds: 10, TimeoutSeconds: 60, AutoMerge: true, AutoAnswer: true, CollectReportIdeas: true,
		MaxStageAttempts: 2, AllowAnyWorker: false, AllowedWorkers: []string{"worker-1"}, MaxParallelSubtasks: 2, MaxParallelWorks: 4, MaxTerminalTasksPerCycle: 8,
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

func TestPilotConfigStoreAtomicallyReplacesFile(t *testing.T) {
	store, path := writePilotFixture(t, validPilotSettings())
	beforeInfo, err := os.Stat(path)
	if err != nil {
		t.Fatal(err)
	}
	current, err := store.Read()
	if err != nil {
		t.Fatal(err)
	}
	current.Settings.PollSeconds = 15
	if _, err := store.Write(current.Version, current.Settings); err != nil {
		t.Fatal(err)
	}
	afterInfo, err := os.Stat(path)
	if err != nil {
		t.Fatal(err)
	}
	if os.SameFile(beforeInfo, afterInfo) {
		t.Fatal("save rewrote the existing file instead of atomically replacing it")
	}
}

func TestPilotConfigStoreAtomicWriteFailureKeepsOriginalAndRemovesTempFile(t *testing.T) {
	tests := map[string]func(*os.File, []byte) (int, error){
		"write error": func(tmp *os.File, body []byte) (int, error) {
			written, _ := tmp.Write(body[:len(body)/2])
			return written, errors.New("injected write failure")
		},
		"short write": func(tmp *os.File, body []byte) (int, error) {
			return tmp.Write(body[:len(body)/2])
		},
	}
	for name, writeTemp := range tests {
		t.Run(name, func(t *testing.T) {
			store, path := writePilotFixture(t, validPilotSettings())
			before, err := os.ReadFile(path)
			if err != nil {
				t.Fatal(err)
			}
			current, err := store.Read()
			if err != nil {
				t.Fatal(err)
			}
			var capturedTemp *os.File
			store.writeTemp = func(tmp *os.File, body []byte) (int, error) {
				capturedTemp = tmp
				return writeTemp(tmp, body)
			}
			current.Settings.PollSeconds = 20
			if _, err := store.Write(current.Version, current.Settings); err == nil {
				t.Fatal("temporary-file write failure was accepted")
			}
			if capturedTemp == nil {
				t.Fatal("atomic write did not reach the temporary file")
			}
			if _, err := capturedTemp.Write([]byte("still open")); err == nil {
				t.Fatal("temporary file remained open after write failure")
			}
			after, err := os.ReadFile(path)
			if err != nil {
				t.Fatal(err)
			}
			if !bytes.Equal(after, before) {
				t.Fatal("temporary-file write failure changed the previous config")
			}
			temps, err := filepath.Glob(filepath.Join(filepath.Dir(path), ".pilot-config-*"))
			if err != nil {
				t.Fatal(err)
			}
			if len(temps) != 0 {
				t.Fatalf("temporary-file write failure left files behind: %v", temps)
			}
		})
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
	settings.ProjectProviders[0].Type = " trade "
	if _, err := validatePilotSettings(settings); err == nil {
		t.Fatal("provider type with ambiguous whitespace was accepted")
	}

	settings = validPilotSettings()
	settings.ProjectProviders = []protocol.ProjectProvider{{RemoteIdentity: "github.com/acme/shop", Type: "trade"}}
	store, path := writePilotFixture(t, settings)
	body, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	body = bytes.Replace(body, []byte(`"type":"trade"`), []byte(`"type":"trade","health_command":"curl production"`), 1)
	if err := os.WriteFile(path, body, 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := store.Read(); err == nil {
		t.Fatal("provider-owned shell command was accepted by strict config schema")
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
	before, err := os.ReadFile(link)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := NewPilotConfigStore(link).Write("stale", validPilotSettings()); err == nil {
		t.Fatal("write replaced an invalid config")
	}
	after, err := os.ReadFile(link)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(after, before) {
		t.Fatal("failed write changed invalid config contents")
	}
}

func TestPilotConfigStoreReportsMissingAndOversizedFiles(t *testing.T) {
	dir := t.TempDir()
	missing := NewPilotConfigStore(filepath.Join(dir, "missing.json"))
	assertPilotConfigError(t, missing, "pilot_config_missing")

	oversizedPath := filepath.Join(dir, "oversized.json")
	if err := os.WriteFile(oversizedPath, bytes.Repeat([]byte("x"), maxPilotConfigBytes+1), 0o600); err != nil {
		t.Fatal(err)
	}
	assertPilotConfigError(t, NewPilotConfigStore(oversizedPath), "pilot_config_too_large")
}

func assertPilotConfigError(t *testing.T, store *PilotConfigStore, code string) {
	t.Helper()
	_, err := store.Read()
	var serviceErr *ServiceError
	if !errors.As(err, &serviceErr) || serviceErr.Code != code {
		t.Fatalf("error = %v, want service error %q", err, code)
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
	if !current.Settings.CollectReportIdeas {
		t.Fatal("example collect_report_ideas was not decoded as true")
	}
	if current.Settings.MaxParallelWorks != 4 {
		t.Fatalf("example max_parallel_works = %d, want 4", current.Settings.MaxParallelWorks)
	}
	if current.Settings.MaxTerminalTasksPerCycle != 4 {
		t.Fatalf("example max_terminal_tasks_per_cycle = %d, want 4", current.Settings.MaxTerminalTasksPerCycle)
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
	delete(fields, "collect_report_ideas")
	delete(fields, "max_parallel_works")
	delete(fields, "max_terminal_tasks_per_cycle")
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
	if !legacySettings.Settings.CollectReportIdeas {
		t.Fatal("legacy config did not receive collect_report_ideas=true")
	}
	if legacySettings.Settings.MaxParallelWorks != 4 {
		t.Fatalf("legacy max_parallel_works = %d, want 4", legacySettings.Settings.MaxParallelWorks)
	}
	if legacySettings.Settings.MaxTerminalTasksPerCycle != 4 {
		t.Fatalf("legacy max_terminal_tasks_per_cycle = %d, want 4", legacySettings.Settings.MaxTerminalTasksPerCycle)
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
	server := httptest.NewServer(NewHandlerWithPilotConfig(store, slog.Default(), NewAutomationService(store, slog.Default()), pilot, testWorkerBootstrapCredential))
	defer server.Close()
	register := protocol.WorkerRegistration{Name: "Known", WorkerVersion: "test", RuntimeVersion: "test", Capacity: 1, Health: "healthy"}
	body, _ := json.Marshal(register)
	request, _ := http.NewRequest(http.MethodPut, server.URL+"/api/v1/workers/worker-1", bytes.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set(protocol.WorkerBootstrapCredentialHeader, testWorkerBootstrapCredential)
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
