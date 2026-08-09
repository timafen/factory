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
	writeJSON(w, http.StatusOK, out)
}
