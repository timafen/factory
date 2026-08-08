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
		// the long Russian explanation is not needed for the board
		delete(rec, "verdict")
		out[strings.TrimSuffix(e.Name(), ".json")] = rec
	}
	writeJSON(w, http.StatusOK, map[string]any{"verdicts": out})
}
