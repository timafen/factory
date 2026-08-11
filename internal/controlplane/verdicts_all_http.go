package controlplane

import (
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
	"strings"
)

// Bulk verdicts: the Work board needs to show a human outcome for every task
// at once. Asking per task would be one request per card.

func verdictsDirAll() string {
	home := os.Getenv("FACTORY_DATA_HOME")
	if home == "" {
		home = "/opt/factory-data"
	}
	return filepath.Join(home, "pilot", "verdicts")
}

func (a *API) listVerdicts(w http.ResponseWriter, r *http.Request) {
	out := map[string]any{}
	entries, err := os.ReadDir(verdictsDirAll())
	if err != nil {
		writeJSON(w, http.StatusOK, map[string]any{"verdicts": out})
		return
	}
	for _, e := range entries {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		data, err := os.ReadFile(filepath.Join(verdictsDirAll(), e.Name()))
		if err != nil {
			continue
		}
		var rec map[string]any
		if err := json.Unmarshal(data, &rec); err != nil {
			continue
		}
		// A stopped Review sends the work back. Keep one compact explanation
		// per task so repeated laps remain understandable on the Work board.
		// Older records predate the short reason and fall back to the verdict.
		if rec["stage"] == "Review" && rec["action"] == "stop" {
			if reason, ok := rec["reason"].(string); ok && strings.TrimSpace(reason) != "" {
				rec["return_reason"] = reason
			} else if verdict, ok := rec["verdict"].(string); ok && strings.TrimSpace(verdict) != "" {
				rec["return_reason"] = verdict
			}
		}
		// Long explanations and generic routing reasons are not needed by the board.
		delete(rec, "verdict")
		delete(rec, "reason")
		out[strings.TrimSuffix(e.Name(), ".json")] = rec
	}
	writeJSON(w, http.StatusOK, map[string]any{"verdicts": out})
}
