package controlplane

import (
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
)

// «Готово, когда» по работам: пилот записывает обещания Спецификации,
// экран показывает их владельцу — можно сверить перевод сути до разработки.

func promisesPath() string {
	home := os.Getenv("FACTORY_DATA_HOME")
	if home == "" {
		home = "/opt/factory-data"
	}
	return filepath.Join(home, "pilot", "promises.json")
}

func (a *API) getPromises(w http.ResponseWriter, r *http.Request) {
	out := map[string]any{}
	if data, err := os.ReadFile(promisesPath()); err == nil {
		_ = json.Unmarshal(data, &out)
	}
	// delivery_status is written by Pilot after a stale delivery is rebuilt.
	// Keep the persisted promises shape intact: this endpoint remains a
	// read-only view for operators and older files simply omit the field.
	writeJSON(w, http.StatusOK, out)
}
