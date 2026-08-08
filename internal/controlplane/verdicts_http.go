package controlplane

import (
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
)

// Verdicts are plain-language summaries of what a pipeline stage actually did,
// written by the pilot from the same decision call (so they cost nothing extra).

func verdictsDir() string {
	home := os.Getenv("FACTORY_DATA_HOME")
	if home == "" {
		home = "/opt/factory-data"
	}
	return filepath.Join(home, "pilot", "verdicts")
}

func (a *API) getVerdict(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("task_id")
	if !epicIDPattern.MatchString(id) {
		writeError(w, invalid("bad_task_id", "task id has an unexpected format"))
		return
	}
	data, err := os.ReadFile(filepath.Join(verdictsDir(), id+".json"))
	if err != nil {
		writeJSON(w, http.StatusOK, map[string]any{"verdict": ""})
		return
	}
	var rec map[string]any
	if err := json.Unmarshal(data, &rec); err != nil {
		writeJSON(w, http.StatusOK, map[string]any{"verdict": ""})
		return
	}
	writeJSON(w, http.StatusOK, rec)
}
