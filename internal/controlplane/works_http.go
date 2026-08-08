package controlplane

import (
	"net/http"
	"strings"
)

func (a *API) getWorks(w http.ResponseWriter, r *http.Request) {
	tasks, err := a.store.ActiveTasks(r.Context())
	if err != nil {
		writeError(w, err)
		return
	}
	works := make(map[string]workMetadata, len(tasks))
	for _, task := range tasks {
		origin := "owner"
		if strings.HasPrefix(task.RequestKey, "automation:") {
			origin = "orchestrator"
		}
		works[task.ID] = workMetadata{Origin: origin, Stage: task.Stage}
	}
	writeJSON(w, http.StatusOK, works)
}

type workMetadata struct {
	Origin string `json:"origin"`
	Stage  string `json:"stage,omitempty"`
}
