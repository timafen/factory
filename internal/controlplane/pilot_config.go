package controlplane

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"net/url"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"

	"github.com/owainlewis/factory/internal/protocol"
)

const maxPilotConfigBytes = 1 << 20

var pilotStages = []string{"Triage", "Specification", "Implement + Test", "Review", "Verify"}
var projectProviderTypes = map[string]struct{}{"trade": {}, "factory": {}}

type PilotConfigStore struct {
	path      string
	mu        sync.Mutex
	writeTemp func(*os.File, []byte) (int, error)
}

func NewPilotConfigStore(path string) *PilotConfigStore { return &PilotConfigStore{path: path} }

func (s *PilotConfigStore) Read() (protocol.PilotSettingsResponse, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	settings, body, err := s.read()
	if err != nil {
		return protocol.PilotSettingsResponse{}, err
	}
	return protocol.PilotSettingsResponse{Settings: settings, Version: pilotDigest(body), Warnings: []string{}}, nil
}

func (s *PilotConfigStore) Write(version string, settings protocol.PilotSettings) (protocol.PilotSettingsResponse, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	_, current, err := s.read()
	if err != nil {
		return protocol.PilotSettingsResponse{}, err
	}
	if version == "" || version != pilotDigest(current) {
		return protocol.PilotSettingsResponse{}, conflict("config_conflict", "pilot settings changed; refresh before saving")
	}
	body, err := json.MarshalIndent(settings, "", "  ")
	if err != nil {
		return protocol.PilotSettingsResponse{}, unavailable(err)
	}
	body = append(body, '\n')
	if err := s.atomicWrite(body); err != nil {
		return protocol.PilotSettingsResponse{}, err
	}
	return protocol.PilotSettingsResponse{Settings: settings, Version: pilotDigest(body), Warnings: []string{}}, nil
}

func (s *PilotConfigStore) read() (protocol.PilotSettings, []byte, error) {
	info, err := os.Lstat(s.path)
	if errors.Is(err, os.ErrNotExist) {
		return protocol.PilotSettings{}, nil, &ServiceError{Code: "pilot_config_missing", Message: "pilot config file is missing", Status: 404}
	}
	if err != nil {
		return protocol.PilotSettings{}, nil, unavailable(err)
	}
	if info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
		return protocol.PilotSettings{}, nil, &ServiceError{Code: "pilot_config_unsafe", Message: "pilot config must be a regular file, not a symlink", Status: 503}
	}
	if info.Size() > maxPilotConfigBytes {
		return protocol.PilotSettings{}, nil, &ServiceError{Code: "pilot_config_too_large", Message: "pilot config exceeds 1 MiB", Status: 503}
	}
	f, err := os.Open(s.path)
	if err != nil {
		return protocol.PilotSettings{}, nil, unavailable(err)
	}
	defer f.Close()
	body, err := io.ReadAll(io.LimitReader(f, maxPilotConfigBytes+1))
	if err != nil {
		return protocol.PilotSettings{}, nil, unavailable(err)
	}
	if len(body) > maxPilotConfigBytes {
		return protocol.PilotSettings{}, nil, &ServiceError{Code: "pilot_config_too_large", Message: "pilot config exceeds 1 MiB", Status: 503}
	}
	settings, present, err := decodePilotSettings(body)
	if err != nil {
		return protocol.PilotSettings{}, nil, &ServiceError{Code: "pilot_config_invalid", Message: err.Error(), Status: 503}
	}
	// Compatibility default: older pilot files predate worker policy settings.
	if !present["allow_any_worker"] {
		settings.AllowAnyWorker = true
	}
	// Compatibility default: pilot.py treated an absent key as enabled.
	if !present["respect_host_load"] {
		settings.RespectHostLoad = true
	}
	// Compatibility default: automatic report intake existed before the switch.
	if !present["collect_report_ideas"] {
		settings.CollectReportIdeas = true
	}
	// Compatibility default: Pilot historically kept this limit only in Python.
	if !present["max_parallel_works"] {
		settings.MaxParallelWorks = 4
	}
	// Compatibility default matches pilot.py for older configuration files.
	if !present["max_terminal_tasks_per_cycle"] {
		settings.MaxTerminalTasksPerCycle = 4
	}
	return settings, body, nil
}

func decodePilotSettings(body []byte) (protocol.PilotSettings, map[string]bool, error) {
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(body, &fields); err != nil {
		return protocol.PilotSettings{}, nil, fmt.Errorf("pilot config contains invalid JSON")
	}
	decoder := json.NewDecoder(bytes.NewReader(body))
	decoder.DisallowUnknownFields()
	var settings protocol.PilotSettings
	if err := decoder.Decode(&settings); err != nil {
		return settings, nil, fmt.Errorf("pilot config schema is invalid: %v", err)
	}
	present := make(map[string]bool, len(fields))
	for key := range fields {
		present[key] = true
	}
	return settings, present, nil
}

func (s *PilotConfigStore) atomicWrite(body []byte) error {
	dir := filepath.Dir(s.path)
	tmp, err := os.CreateTemp(dir, ".pilot-config-*")
	if err != nil {
		return unavailable(err)
	}
	tmpName := tmp.Name()
	defer func() {
		_ = tmp.Close()
		_ = os.Remove(tmpName)
	}()
	if err := tmp.Chmod(0o600); err != nil {
		return unavailable(err)
	}
	var written int
	if s.writeTemp == nil {
		written, err = tmp.Write(body)
	} else {
		written, err = s.writeTemp(tmp, body)
	}
	if err != nil {
		return unavailable(err)
	}
	if written != len(body) {
		return unavailable(io.ErrShortWrite)
	}
	if err := tmp.Sync(); err != nil {
		return unavailable(err)
	}
	if err := tmp.Close(); err != nil {
		return unavailable(err)
	}
	if err := os.Rename(tmpName, s.path); err != nil {
		return unavailable(err)
	}
	d, err := os.Open(dir)
	if err != nil {
		return unavailable(err)
	}
	err = d.Sync()
	_ = d.Close()
	if err != nil {
		return unavailable(err)
	}
	return nil
}

func pilotDigest(body []byte) string { sum := sha256.Sum256(body); return hex.EncodeToString(sum[:]) }

func validatePilotSettings(settings protocol.PilotSettings) ([]string, error) {
	positive := []struct {
		name  string
		value float64
	}{{"poll_seconds", settings.PollSeconds}, {"timeout_seconds", settings.TimeoutSeconds}, {"day_cap_usd", settings.DayCapUSD}}
	for _, field := range positive {
		if math.IsNaN(field.value) || math.IsInf(field.value, 0) || field.value <= 0 {
			return nil, invalid("invalid_pilot_settings", field.name+" must be positive")
		}
	}
	if math.IsNaN(settings.ReleaseBatchSeconds) || math.IsInf(settings.ReleaseBatchSeconds, 0) || settings.ReleaseBatchSeconds < 0 {
		return nil, invalid("invalid_pilot_settings", "release_batch_seconds must be zero or positive")
	}
	if settings.MaxStageAttempts <= 0 || settings.MaxParallelSubtasks <= 0 || settings.MaxParallelWorks <= 0 || settings.MaxTerminalTasksPerCycle <= 0 {
		return nil, invalid("invalid_pilot_settings", "attempt and parallelism limits must be positive")
	}
	if len(settings.Stages) != len(pilotStages) || len(settings.StageBaseUSD) != len(pilotStages) {
		return nil, invalid("invalid_pilot_settings", "stages and stage_base_usd must contain exactly the five pilot stages")
	}
	allowed := map[string]bool{}
	for _, id := range settings.AllowedWorkers {
		if strings.TrimSpace(id) == "" {
			return nil, invalid("invalid_pilot_settings", "allowed_workers cannot contain an empty ID")
		}
		allowed[id] = true
	}
	warnings := []string{}
	warningSeen := map[string]bool{}
	for _, stage := range pilotStages {
		// Этапы лежат списком: порядок в конвейере — это и есть порядок здесь.
		var workers protocol.PilotStageWorkers
		ok := false
		for _, st := range settings.Stages {
			if st.Workflow == stage {
				workers, ok = st.Workers, true
				break
			}
		}
		if !ok {
			return nil, invalid("invalid_pilot_settings", "missing stage: "+stage)
		}
		if workers.Low == "" || workers.Medium == "" || workers.High == "" {
			return nil, invalid("invalid_pilot_settings", "each stage requires low, medium, and high workers")
		}
		if err := validateWorkerEffortOrder(stage, workers); err != nil {
			return nil, err
		}
		if cost, ok := settings.StageBaseUSD[stage]; !ok || cost <= 0 || math.IsNaN(cost) || math.IsInf(cost, 0) {
			return nil, invalid("invalid_pilot_settings", "stage_base_usd values must be positive")
		}
		for _, worker := range []string{workers.Low, workers.Medium, workers.High} {
			if !allowed[worker] {
				if !settings.AllowAnyWorker {
					return nil, invalid("unknown_worker", "worker "+worker+" is not in allowed_workers")
				}
				warning := "Unknown worker: " + worker
				if !warningSeen[warning] {
					warnings = append(warnings, warning)
					warningSeen[warning] = true
				}
			}
		}
	}
	for _, values := range []map[string]float64{settings.ComplexityFactor, settings.WorkCapUSD} {
		if len(values) != 3 {
			return nil, invalid("invalid_pilot_settings", "complexity_factor and work_cap_usd require low, medium, and high")
		}
		for _, tier := range []string{"low", "medium", "high"} {
			if value, ok := values[tier]; !ok || value <= 0 || math.IsNaN(value) || math.IsInf(value, 0) {
				return nil, invalid("invalid_pilot_settings", "tier values must be positive")
			}
		}
	}
	for name, raw := range map[string]string{"owner_chat_url": settings.OwnerChatURL, "owner_ui_url": settings.OwnerUIURL, "ntfy_server": settings.NtfyServer} {
		parsed, err := url.ParseRequestURI(raw)
		if err != nil || (parsed.Scheme != "http" && parsed.Scheme != "https") || parsed.Host == "" {
			return nil, invalid("invalid_pilot_settings", name+" must be an http or https URL")
		}
	}
	if settings.NtfyTopic == "" || settings.NtfyOwnerTopic == "" {
		return nil, invalid("invalid_pilot_settings", "notification topics are required")
	}
	if len(settings.BrainChain) == 0 {
		return nil, invalid("invalid_pilot_settings", "brain_chain must not be empty")
	}
	for _, entry := range settings.BrainChain {
		if entry.CLI == "" || entry.Model == "" || entry.Provider == "" {
			return nil, invalid("invalid_pilot_settings", "each brain_chain entry requires cli, model, and provider")
		}
	}
	providers := map[string]bool{}
	for _, provider := range settings.ProjectProviders {
		identity := strings.ToLower(strings.TrimSpace(provider.RemoteIdentity))
		if identity == "" {
			return nil, invalid("invalid_pilot_settings", "each project provider requires remote_identity")
		}
		if provider.Type != strings.TrimSpace(provider.Type) {
			return nil, invalid("invalid_pilot_settings", "project provider type cannot contain surrounding whitespace")
		}
		if _, ok := projectProviderTypes[provider.Type]; !ok {
			return nil, invalid("unknown_project_provider", "unknown project provider type: "+provider.Type)
		}
		if providers[identity] {
			return nil, invalid("invalid_pilot_settings", "duplicate project provider: "+identity)
		}
		providers[identity] = true
	}
	sort.Strings(warnings)
	return warnings, nil
}

func validateWorkerEffortOrder(stage string, workers protocol.PilotStageWorkers) error {
	ordered := []struct {
		tier string
		name string
	}{{"low", workers.Low}, {"medium", workers.Medium}, {"high", workers.High}}
	for i := 1; i < len(ordered); i++ {
		previousFamily, previousEffort, previousOK := workerEffort(ordered[i-1].name)
		family, effort, ok := workerEffort(ordered[i].name)
		if previousOK && ok && previousFamily == family && effort < previousEffort {
			return invalid("invalid_pilot_settings", fmt.Sprintf(
				"%s %s worker %s has lower reasoning effort than %s worker %s",
				stage, ordered[i].tier, ordered[i].name,
				ordered[i-1].tier, ordered[i-1].name))
		}
	}
	return nil
}

func workerEffort(name string) (string, int, bool) {
	lower := strings.ToLower(strings.TrimSpace(name))
	for suffix, rank := range map[string]int{
		"-low": 0, "-medium": 1, "-high": 2, "-max": 3,
	} {
		if strings.HasSuffix(lower, suffix) {
			return strings.TrimSuffix(lower, suffix), rank, true
		}
	}
	return "", 0, false
}
