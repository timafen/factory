package controlplane

import (
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
)

// The dashboard is computed by the pilot once per cycle and dropped as a single
// file. Serving it is deliberately dumb: no fan-out of API calls per page load.

func dashboardPath() string {
	home := os.Getenv("FACTORY_DATA_HOME")
	if home == "" {
		home = "/opt/factory-data"
	}
	return filepath.Join(home, "pilot", "dashboard.json")
}

func (a *API) getDashboard(w http.ResponseWriter, r *http.Request) {
	out := map[string]any{}
	if data, err := os.ReadFile(dashboardPath()); err == nil {
		_ = json.Unmarshal(data, &out)
	}
	if now, ok := out["now"].(map[string]any); ok {
		if running, ok := now["running"].([]any); ok {
			now["running_count"] = len(running)
		}
	}
	writeJSON(w, http.StatusOK, out)
}
