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

type PilotConfigStore struct {
	path                  string
	mu                    sync.Mutex
	reviveSignalPublished func(string)
}

type ReviveWorkResponse struct {
	Work  string `json:"work"`
	State string `json:"state"`
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

// Revive removes only the requested owner pause and leaves an idempotent signal
// for pipeline_watch. Task selection remains entirely in the pilot.
func (s *PilotConfigStore) Revive(work string) (ReviveWorkResponse, error) {
	work = strings.TrimSpace(work)
	if work == "" {
		return ReviveWorkResponse{}, invalid("invalid_work", "work name is required")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	settings, _, err := s.read()
	if err != nil {
		return ReviveWorkResponse{}, err
	}
	known := s.hasReviveSignal(work) || s.hasReviveReceipt(work)
	needsSignal := false
	configChanged := false
	stopped := make([]string, 0, len(settings.StoppedPipelines))
	for _, name := range settings.StoppedPipelines {
		if name == work {
			known = true
			needsSignal = true
			configChanged = true
			continue
		}
		stopped = append(stopped, name)
	}
	stalls, readErr := s.readStalls()
	if readErr != nil {
		return ReviveWorkResponse{}, readErr
	}
	if rec, ok := stalls[work]; ok && rec.Why == "give_up" {
		known = true
		needsSignal = true
	}
	if !known {
		return ReviveWorkResponse{}, &ServiceError{Code: "work_not_stopped", Message: "work is not stopped", Status: 404}
	}
	created := false
	if needsSignal || !s.hasReviveReceipt(work) {
		created, err = s.createReviveSignal(work)
		if err != nil {
			return ReviveWorkResponse{}, err
		}
	}
	// A stuck work is not present in stopped_pipelines. Publishing its targeted
	// signal is the whole mutation; rewriting identical settings would add a
	// second failure after the pilot may already have consumed the signal.
	if !configChanged {
		return ReviveWorkResponse{Work: work, State: "reviving"}, nil
	}
	settings.StoppedPipelines = stopped
	body, err := json.MarshalIndent(settings, "", "  ")
	if err != nil {
		if created {
			_ = os.Remove(s.reviveSignalPath(work))
		}
		return ReviveWorkResponse{}, unavailable(err)
	}
	if err := s.atomicWrite(append(body, '\n')); err != nil {
		if created {
			_ = os.Remove(s.reviveSignalPath(work))
		}
		return ReviveWorkResponse{}, err
	}
	return ReviveWorkResponse{Work: work, State: "reviving"}, nil
}

type pilotStall struct {
	Why string `json:"why"`
}

func (s *PilotConfigStore) revivePath() string {
	return filepath.Join(filepath.Dir(s.path), "revive")
}
func (s *PilotConfigStore) stallPath() string {
	return filepath.Join(filepath.Dir(s.path), "stalled.json")
}

func (s *PilotConfigStore) reviveSignalPath(work string) string {
	sum := sha256.Sum256([]byte(work))
	return filepath.Join(s.revivePath(), hex.EncodeToString(sum[:]))
}

func (s *PilotConfigStore) reviveReceiptPath(work string) string {
	return s.reviveSignalPath(work) + ".done"
}

func (s *PilotConfigStore) hasReviveSignal(work string) bool {
	_, err := os.Stat(s.reviveSignalPath(work))
	return err == nil
}

func (s *PilotConfigStore) hasReviveReceipt(work string) bool {
	_, err := os.Stat(s.reviveReceiptPath(work))
	return err == nil
}

// createReviveSignal creates one file per work. O_EXCL makes a concurrent
// request for another work independent, and makes a repeated request safe.
func (s *PilotConfigStore) createReviveSignal(work string) (bool, error) {
	if err := os.MkdirAll(s.revivePath(), 0o700); err != nil {
		return false, unavailable(err)
	}
	if err := os.Remove(s.reviveReceiptPath(work)); err != nil && !errors.Is(err, os.ErrNotExist) {
		return false, unavailable(err)
	}
	f, err := os.OpenFile(s.reviveSignalPath(work), os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)
	if errors.Is(err, os.ErrExist) {
		return false, nil
	}
	if err != nil {
		return false, unavailable(err)
	}
	if _, err := f.WriteString(work); err != nil {
		_ = f.Close()
		_ = os.Remove(s.reviveSignalPath(work))
		return false, unavailable(err)
	}
	if err := f.Close(); err != nil {
		_ = os.Remove(s.reviveSignalPath(work))
		return false, unavailable(err)
	}
	if s.reviveSignalPublished != nil {
		s.reviveSignalPublished(work)
	}
	return true, nil
}

func (s *PilotConfigStore) readStalls() (map[string]pilotStall, error) {
	result := map[string]pilotStall{}
	body, err := os.ReadFile(s.stallPath())
	if errors.Is(err, os.ErrNotExist) {
		return result, nil
	}
	if err != nil {
		return nil, unavailable(err)
	}
	if err := json.Unmarshal(body, &result); err != nil {
		return nil, &ServiceError{Code: "pilot_state_invalid", Message: "pilot stall state contains invalid JSON", Status: 503, Err: err}
	}
	return result, nil
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
	// Compatibility default: Pilot historically kept this limit only in Python.
	if !present["max_parallel_works"] {
		settings.MaxParallelWorks = 4
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
	defer os.Remove(tmpName)
	err = tmp.Chmod(0o600)
	if err == nil {
		_, err = tmp.Write(body)
	}
	if err == nil {
		err = tmp.Sync()
	}
	if closeErr := tmp.Close(); err == nil {
		err = closeErr
	}
	if err == nil {
		err = os.Rename(tmpName, s.path)
	}
	if err == nil {
		if d, openErr := os.Open(dir); openErr == nil {
			err = d.Sync()
			_ = d.Close()
		} else {
			err = openErr
		}
	}
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
	if settings.MaxStageAttempts <= 0 || settings.MaxParallelSubtasks <= 0 || settings.MaxParallelWorks <= 0 {
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
		if provider.Type != "trade" && provider.Type != "factory" {
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
