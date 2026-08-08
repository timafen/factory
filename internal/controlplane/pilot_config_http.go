package controlplane

import (
	"context"
	"net/http"
	"sort"

	"github.com/owainlewis/factory/internal/protocol"
)

func (a *API) getPilotSettings(w http.ResponseWriter, r *http.Request) {
	if a.pilotConfig == nil {
		writeError(w, &ServiceError{Code: "pilot_config_unavailable", Message: "pilot settings are not configured", Status: 503})
		return
	}
	response, err := a.pilotConfig.Read()
	if err != nil {
		writeError(w, err)
		return
	}
	if err := a.initializeAllowedWorkers(r.Context(), &response.Settings); err != nil {
		writeError(w, err)
		return
	}
	warnings, err := validatePilotSettings(response.Settings)
	if err != nil {
		writeError(w, err)
		return
	}
	response.Warnings = warnings
	writeJSON(w, http.StatusOK, response)
}

func (a *API) updatePilotSettings(w http.ResponseWriter, r *http.Request) {
	if a.pilotConfig == nil {
		writeError(w, &ServiceError{Code: "pilot_config_unavailable", Message: "pilot settings are not configured", Status: 503})
		return
	}
	if !prepareMutation(w, r, protocol.MaxBodyBytes) {
		return
	}
	var input protocol.UpdatePilotSettingsRequest
	if !decodeJSON(w, r, &input) {
		return
	}
	if input.Settings.AllowedWorkers == nil {
		if err := a.initializeAllowedWorkers(r.Context(), &input.Settings); err != nil {
			writeError(w, err)
			return
		}
	}
	warnings, err := validatePilotSettings(input.Settings)
	if err != nil {
		writeError(w, err)
		return
	}
	response, err := a.pilotConfig.Write(input.Version, input.Settings)
	if err != nil {
		writeError(w, err)
		return
	}
	response.Warnings = warnings
	writeJSON(w, http.StatusOK, response)
}

func (a *API) initializeAllowedWorkers(ctx context.Context, settings *protocol.PilotSettings) error {
	if settings.AllowedWorkers != nil {
		return nil
	}
	workers, err := a.store.Workers(ctx)
	if err != nil {
		return err
	}
	settings.AllowedWorkers = []string{}
	seen := map[string]bool{}
	for _, stage := range settings.Stages {
		for _, workerID := range []string{stage.Low, stage.Medium, stage.High} {
			if workerID != "" && !seen[workerID] {
				settings.AllowedWorkers = append(settings.AllowedWorkers, workerID)
				seen[workerID] = true
			}
		}
	}
	for _, worker := range workers {
		if !seen[worker.ID] {
			settings.AllowedWorkers = append(settings.AllowedWorkers, worker.ID)
			seen[worker.ID] = true
		}
	}
	sort.Strings(settings.AllowedWorkers)
	return nil
}
