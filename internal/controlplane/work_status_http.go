package controlplane

import (
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
)

// Почему работа стоит. Это знает только пилот — он и записывает словами.
// Экран читает готовое и ничего не додумывает за него.

func workStatusPath() string {
	home := os.Getenv("FACTORY_DATA_HOME")
	if home == "" {
		home = "/opt/factory-data"
	}
	return filepath.Join(home, "pilot", "work_status.json")
}

func (a *API) getWorkStatus(w http.ResponseWriter, r *http.Request) {
	out := map[string]any{}
	if data, err := os.ReadFile(workStatusPath()); err == nil {
		_ = json.Unmarshal(data, &out)
	}
	writeJSON(w, http.StatusOK, out)
}
