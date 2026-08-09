package controlplane

import (
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
	"sync"
	"time"
)

var limitsMu sync.Mutex

// Limits: which subscription pools are currently exhausted. The pilot writes
// this file when a stage fails with a rate-limit signature; the UI shows it so
// the owner sees "we are waiting, not broken".

func limitsPath() string {
	home := os.Getenv("FACTORY_DATA_HOME")
	if home == "" {
		home = "/opt/factory-data"
	}
	return filepath.Join(home, "pilot", "limits.json")
}

func (a *API) getLimits(w http.ResponseWriter, r *http.Request) {
	out := map[string]any{}
	data, err := os.ReadFile(limitsPath())
	if err == nil {
		_ = json.Unmarshal(data, &out)
	}
	writeJSON(w, http.StatusOK, map[string]any{"limits": out})
}

type providerRequest struct {
	Enabled bool `json:"enabled"`
}

// setProvider is the owner's manual switch: turn a whole subscription pool off
// or back on. Off means the pilot hands it no work at all, regardless of limits.
func (a *API) setProvider(w http.ResponseWriter, r *http.Request) {
	p := r.PathValue("provider")
	if p != "claude" && p != "codex" {
		writeError(w, invalid("bad_provider", "provider must be claude or codex"))
		return
	}
	var req providerRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, invalid("bad_body", "expected {\"enabled\": true|false}"))
		return
	}
	limitsMu.Lock()
	defer limitsMu.Unlock()
	all := map[string]any{}
	if data, err := os.ReadFile(limitsPath()); err == nil {
		_ = json.Unmarshal(data, &all)
	}
	rec, _ := all[p].(map[string]any)
	if rec == nil {
		rec = map[string]any{}
	}
	rec["manual_off"] = !req.Enabled
	rec["manual_changed_at"] = time.Now().UTC().Format(time.RFC3339)
	all[p] = rec
	data, err := json.MarshalIndent(all, "", " ")
	if err != nil {
		writeError(w, unavailable(err))
		return
	}
	if err := os.WriteFile(limitsPath(), data, 0o644); err != nil {
		writeError(w, unavailable(err))
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true, "provider": p, "enabled": req.Enabled})
}
