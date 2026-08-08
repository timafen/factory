package controlplane

import (
	"net/http"
)

func (a *API) getDashboard(w http.ResponseWriter, r *http.Request) {
	tasks, err := a.store.ActiveTasks(r.Context())
	if err != nil {
		writeError(w, err)
		return
	}
	running := make([]dashboardWork, 0, len(tasks))
	for _, task := range tasks {
		running = append(running, dashboardWork{ID: task.ID, Title: task.Title})
	}
	writeJSON(w, http.StatusOK, map[string]any{"now": map[string]any{"running": running}})
}

type dashboardWork struct {
	ID    string `json:"id"`
	Title string `json:"title"`
}
