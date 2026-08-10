package controlplane

import (
	"bufio"
	"bytes"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"

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

func TestReviveWorkWritesSignalWithoutChangingConfigAndIsIdempotent(t *testing.T) {
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
	if got := current.Settings.StoppedPipelines; len(got) != 2 || got[0] != "Работа" || got[1] != "Работа рядом" {
		t.Fatalf("stopped pipelines = %#v", got)
	}
	var signals map[string]bool
	body, _ := os.ReadFile(filepath.Join(filepath.Dir(path), "revive.json"))
	if err := json.Unmarshal(body, &signals); err != nil || !signals["Работа"] || len(signals) != 1 {
		t.Fatalf("signals = %#v, %v", signals, err)
	}
}

func TestReviveWorkDoesNotLosePauseAddedWhileSignalIsWritten(t *testing.T) {
	settings := validPilotSettings()
	settings.StoppedPipelines = []string{"Работа"}
	store, path := writePilotFixture(t, settings)
	store.rename = func(oldPath, newPath string) error {
		if newPath == filepath.Join(filepath.Dir(path), "revive.json") {
			latest := validPilotSettings()
			latest.StoppedPipelines = []string{"Работа", "Параллельная пауза"}
			body, err := json.MarshalIndent(latest, "", "  ")
			if err != nil {
				return err
			}
			if err := os.WriteFile(path, append(body, '\n'), 0o600); err != nil {
				return err
			}
		}
		return os.Rename(oldPath, newPath)
	}

	if _, err := store.Revive("Работа"); err != nil {
		t.Fatal(err)
	}
	current, err := store.Read()
	if err != nil {
		t.Fatal(err)
	}
	if got := current.Settings.StoppedPipelines; len(got) != 2 || got[0] != "Работа" || got[1] != "Параллельная пауза" {
		t.Fatalf("concurrent pause was lost: %#v", got)
	}
}

func TestReviveConfigWritesUseSharedGoPythonLock(t *testing.T) {
	settings := validPilotSettings()
	settings.StoppedPipelines = []string{"Работа", "Другая пауза"}
	store, path := writePilotFixture(t, settings)
	current, err := store.Read()
	if err != nil {
		t.Fatal(err)
	}

	root, err := filepath.Abs(filepath.Join("..", ".."))
	if err != nil {
		t.Fatal(err)
	}
	script := `
import sys
sys.path.insert(0, sys.argv[1])
from pilot import pilot

pilot.CONF_PATH = sys.argv[2]
original_load = pilot.load

def load_after_go_starts(path, default):
    value = original_load(path, default)
    if path == pilot.CONF_PATH:
        print("READY", flush=True)
        sys.stdin.readline()
    return value

pilot.load = load_after_go_starts
conf = {"stopped_pipelines": ["Работа", "Другая пауза"]}
pilot.release_revive_pauses(conf, {"Работа": True})
if conf.get("stopped_pipelines") != ["Другая пауза"]:
    raise SystemExit("revive did not update Python config")
`
	command := exec.Command("python3", "-c", script, root, path)
	stdin, err := command.StdinPipe()
	if err != nil {
		t.Fatal(err)
	}
	stdout, err := command.StdoutPipe()
	if err != nil {
		t.Fatal(err)
	}
	command.Stderr = os.Stderr
	if err := command.Start(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if command.Process != nil {
			_ = command.Process.Kill()
		}
	})

	ready := make(chan string, 1)
	go func() {
		line, _ := bufio.NewReader(stdout).ReadString('\n')
		ready <- line
	}()
	select {
	case line := <-ready:
		if line != "READY\n" {
			t.Fatalf("python ready line = %q", line)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("python did not acquire the config lock")
	}

	updated := current.Settings
	updated.PollSeconds = 15
	writeDone := make(chan error, 1)
	go func() {
		_, writeErr := store.Write(current.Version, updated)
		writeDone <- writeErr
	}()
	select {
	case writeErr := <-writeDone:
		t.Fatalf("Go write escaped Python lock: %v", writeErr)
	case <-time.After(150 * time.Millisecond):
	}

	_, _ = stdin.Write([]byte("\n"))
	_ = stdin.Close()
	if err := command.Wait(); err != nil {
		t.Fatal(err)
	}
	select {
	case writeErr := <-writeDone:
		if writeErr == nil {
			t.Fatal("stale Go write succeeded after Python changed config")
		}
		var serviceErr *ServiceError
		if !errors.As(writeErr, &serviceErr) || serviceErr.Code != "config_conflict" {
			t.Fatalf("Go write error = %v", writeErr)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("Go write remained blocked after Python released config")
	}

	after, err := store.Read()
	if err != nil {
		t.Fatal(err)
	}
	if after.Settings.PollSeconds != 10 {
		t.Fatalf("stale Go settings overwrote Python config: poll_seconds = %v", after.Settings.PollSeconds)
	}
	if got := after.Settings.StoppedPipelines; len(got) != 1 || got[0] != "Другая пауза" {
		t.Fatalf("Python revive change was lost: %#v", got)
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

func TestReviveWorkKeepsOwnerPauseWhenSignalWriteFails(t *testing.T) {
	settings := validPilotSettings()
	settings.StoppedPipelines = []string{"Работа", "Работа рядом"}
	store, path := writePilotFixture(t, settings)
	store.rename = func(oldPath, newPath string) error {
		if newPath == filepath.Join(filepath.Dir(path), "revive.json") {
			return errors.New("injected revive signal write failure")
		}
		return os.Rename(oldPath, newPath)
	}

	if _, err := store.Revive("Работа"); err == nil {
		t.Fatal("revive succeeded despite signal write failure")
	}
	current, err := store.Read()
	if err != nil {
		t.Fatal(err)
	}
	if got := current.Settings.StoppedPipelines; len(got) != 2 || got[0] != "Работа" || got[1] != "Работа рядом" {
		t.Fatalf("stopped pipelines changed after failed signal write: %#v", got)
	}
}

func TestReviveWorkHTTPRejectsCrossOrigin(t *testing.T) {
	settings := validPilotSettings()
	settings.StoppedPipelines = []string{"Работа с пробелом"}
	pilot, _ := writePilotFixture(t, settings)
	store := newTestStore(t)
	server := httptest.NewServer(NewHandlerWithPilotConfig(store, slog.Default(), NewAutomationService(store, slog.Default()), pilot))
	defer server.Close()

	request, err := http.NewRequest(http.MethodPost, server.URL+"/api/v1/works/"+url.PathEscape("Работа с пробелом")+"/revive", bytes.NewReader([]byte(`{}`)))
	if err != nil {
		t.Fatal(err)
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Origin", "https://evil.example")
	response, err := server.Client().Do(request)
	if err != nil {
		t.Fatal(err)
	}
	if response.StatusCode != http.StatusForbidden {
		response.Body.Close()
		t.Fatalf("cross-origin status = %d", response.StatusCode)
	}
	var rejection protocol.ErrorBody
	if err := json.NewDecoder(response.Body).Decode(&rejection); err != nil {
		response.Body.Close()
		t.Fatal(err)
	}
	response.Body.Close()
	if rejection.Error.Code != "cross_origin_request" {
		t.Fatalf("cross-origin error = %q", rejection.Error.Code)
	}
	current, err := pilot.Read()
	if err != nil {
		t.Fatal(err)
	}
	if got := current.Settings.StoppedPipelines; len(got) != 1 || got[0] != "Работа с пробелом" {
		t.Fatalf("cross-origin request changed stopped pipelines: %#v", got)
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
}
