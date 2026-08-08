package controlplane

import (
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
	"sync"
)

// Pipeline configuration is owned by the factory-pilot orchestrator and stored
// as a JSON file beside its runtime state. These endpoints let the operator read
// and edit the pipeline (stage order, per-complexity model routing, decision
// model) from the control-plane UI instead of editing the file by hand.

var pipelineMu sync.Mutex

func pipelineConfigPath() string {
	if p := os.Getenv("FACTORY_PIPELINE_CONFIG"); p != "" {
		return p
	}
	home := os.Getenv("FACTORY_DATA_HOME")
	if home == "" {
		home = "/opt/factory-data"
	}
	return filepath.Join(home, "pilot", "config.json")
}

type pipelineStage struct {
	Workflow string            `json:"workflow"`
	Worker   string            `json:"worker,omitempty"`
	Workers  map[string]string `json:"workers,omitempty"`
}

type pipelineConfig struct {
	Enabled        bool            `json:"enabled"`
	DecisionModel  string          `json:"decision_model"`
	PollSeconds    int             `json:"poll_seconds,omitempty"`
	TimeoutSeconds int             `json:"timeout_seconds,omitempty"`
	Note           string          `json:"_note,omitempty"`
	Stages         []pipelineStage `json:"stages"`
}

func (a *API) getPipeline(w http.ResponseWriter, r *http.Request) {
	pipelineMu.Lock()
	defer pipelineMu.Unlock()
	data, err := os.ReadFile(pipelineConfigPath())
	if err != nil {
		if os.IsNotExist(err) {
			writeJSON(w, http.StatusOK, pipelineConfig{Enabled: false, Stages: []pipelineStage{}})
			return
		}
		writeError(w, unavailable(err))
		return
	}
	var cfg pipelineConfig
	if err := json.Unmarshal(data, &cfg); err != nil {
		writeError(w, unavailable(err))
		return
	}
	if cfg.Stages == nil {
		cfg.Stages = []pipelineStage{}
	}
	writeJSON(w, http.StatusOK, cfg)
}

func (a *API) putPipeline(w http.ResponseWriter, r *http.Request) {
	r.Body = http.MaxBytesReader(w, r.Body, 256*1024)
	var cfg pipelineConfig
	if err := json.NewDecoder(r.Body).Decode(&cfg); err != nil {
		writeError(w, invalid("invalid_pipeline", "pipeline body is not valid JSON: "+err.Error()))
		return
	}
	if len(cfg.Stages) == 0 {
		writeError(w, invalid("pipeline_empty", "at least one stage is required"))
		return
	}
	for _, stage := range cfg.Stages {
		if stage.Workflow == "" {
			writeError(w, invalid("pipeline_stage_workflow", "every stage needs a workflow title"))
			return
		}
	}
	pipelineMu.Lock()
	defer pipelineMu.Unlock()
	out, err := json.MarshalIndent(cfg, "", "  ")
	if err != nil {
		writeError(w, unavailable(err))
		return
	}
	path := pipelineConfigPath()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		writeError(w, unavailable(err))
		return
	}
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, out, 0o644); err != nil {
		writeError(w, unavailable(err))
		return
	}
	if err := os.Rename(tmp, path); err != nil {
		writeError(w, unavailable(err))
		return
	}
	a.logger.Info("pipeline_updated", "stages", len(cfg.Stages), "enabled", cfg.Enabled)
	writeJSON(w, http.StatusOK, cfg)
}
