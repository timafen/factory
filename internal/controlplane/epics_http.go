package controlplane

import (
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"sync"
)

// Epics are owned by the factory-pilot orchestrator and stored as JSON files
// under <data-home>/pilot/epics/. The control plane exposes them read-only,
// plus a "start" action that flips a planned epic to start-requested; the
// pilot picks that up on its next cycle and fans the subtasks out.

var epicsMu sync.Mutex

var epicIDPattern = regexp.MustCompile(`^[A-Za-z0-9-]+$`)

func epicsDir() string {
	home := os.Getenv("FACTORY_DATA_HOME")
	if home == "" {
		home = "/opt/factory-data"
	}
	return filepath.Join(home, "pilot", "epics")
}

// Epics are written by the pilot and may carry fields the control plane does
// not model (per-subtask status, task ids, timestamps). Decode into a generic
// map so nothing is silently dropped on the way to the UI.
func readEpics() ([]map[string]any, error) {
	entries, err := os.ReadDir(epicsDir())
	if err != nil {
		if os.IsNotExist(err) {
			return []map[string]any{}, nil
		}
		return nil, err
	}
	out := []map[string]any{}
	for _, e := range entries {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		data, err := os.ReadFile(filepath.Join(epicsDir(), e.Name()))
		if err != nil {
			continue
		}
		var rec map[string]any
		if err := json.Unmarshal(data, &rec); err != nil {
			continue
		}
		out = append(out, rec)
	}
	sort.Slice(out, func(i, j int) bool {
		return toString(out[i]["id"]) < toString(out[j]["id"])
	})
	return out, nil
}

func (a *API) listEpics(w http.ResponseWriter, r *http.Request) {
	epicsMu.Lock()
	defer epicsMu.Unlock()
	epics, err := readEpics()
	if err != nil {
		writeError(w, unavailable(err))
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"epics": epics})
}

func (a *API) deleteEpic(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("epic_id")
	if !epicIDPattern.MatchString(id) {
		writeError(w, invalid("bad_epic_id", "epic id has an unexpected format"))
		return
	}
	epicsMu.Lock()
	defer epicsMu.Unlock()
	path := filepath.Join(epicsDir(), id+".json")
	if _, err := os.Stat(path); err != nil {
		writeError(w, ErrNotFound)
		return
	}
	if err := os.Remove(path); err != nil {
		writeError(w, unavailable(err))
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true})
}

func (a *API) startEpic(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("epic_id")
	if !epicIDPattern.MatchString(id) {
		writeError(w, invalid("bad_epic_id", "epic id has an unexpected format"))
		return
	}
	epicsMu.Lock()
	defer epicsMu.Unlock()
	path := filepath.Join(epicsDir(), id+".json")
	data, err := os.ReadFile(path)
	if err != nil {
		writeError(w, ErrNotFound)
		return
	}
	var rec map[string]any
	if err := json.Unmarshal(data, &rec); err != nil {
		writeError(w, unavailable(err))
		return
	}
	status, _ := rec["status"].(string)
	if status != "planned" {
		writeError(w, conflict("epic_not_planned", "only a planned epic can be started"))
		return
	}
	rec["status"] = "start-requested"
	updated, err := json.MarshalIndent(rec, "", " ")
	if err != nil {
		writeError(w, unavailable(err))
		return
	}
	if err := os.WriteFile(path, updated, 0o644); err != nil {
		writeError(w, unavailable(err))
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true, "status": "start-requested"})
}
