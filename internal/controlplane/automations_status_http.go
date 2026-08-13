package controlplane

import "net/http"

func (a *API) listAutomationStatuses(w http.ResponseWriter, r *http.Request) {
	items, err := a.store.AutomationStatuses(r.Context(), automationStatusPath())
	if err != nil {
		writeError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"automations": items})
}
