package controlplane

import (
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
)

// Кто поставил работу и какие стадии ей не нужны. Пилот пишет это один раз при
// заведении; экран читает готовое, чтобы ничего не додумывать за него.

func worksPath() string {
	home := os.Getenv("FACTORY_DATA_HOME")
	if home == "" {
		home = "/opt/factory-data"
	}
	return filepath.Join(home, "pilot", "works.json")
}

func (a *API) getWorks(w http.ResponseWriter, r *http.Request) {
	out := map[string]any{}
	if data, err := os.ReadFile(worksPath()); err == nil {
		_ = json.Unmarshal(data, &out)
	}
	writeJSON(w, http.StatusOK, out)
}
