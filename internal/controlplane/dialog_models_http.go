package controlplane

import (
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// Доступность моделей для «Диалога». Правду о лимитах знает пилот:
// он пишет отдых модели в brain_down.json, а блок подписки — в limits.json.
// Экран читает готовое и не даёт выбрать то, что сейчас не ответит.

type dialogModelView struct {
	Index     int    `json:"index"`
	Model     string `json:"model"`
	Provider  string `json:"provider"`
	Note      string `json:"note,omitempty"`
	Available bool   `json:"available"`
	Reason    string `json:"reason,omitempty"`
}

func pilotFilePath(name string) string {
	home := os.Getenv("FACTORY_DATA_HOME")
	if home == "" {
		home = "/opt/factory-data"
	}
	return filepath.Join(home, "pilot", name)
}

func engineResting(model string) bool {
	raw, err := os.ReadFile(pilotFilePath("brain_down.json"))
	if err != nil {
		return false
	}
	rest := map[string]float64{}
	if json.Unmarshal(raw, &rest) != nil {
		return false
	}
	until, ok := rest[model]
	return ok && until > float64(time.Now().Unix())
}

func providerBlocked(provider string) bool {
	raw, err := os.ReadFile(pilotFilePath("limits.json"))
	if err != nil {
		return false
	}
	limits := map[string]struct {
		State     string `json:"state"`
		ManualOff bool   `json:"manual_off"`
	}{}
	if json.Unmarshal(raw, &limits) != nil {
		return false
	}
	record, ok := limits[provider]
	if !ok {
		return false
	}
	return record.ManualOff || record.State == "exhausted" || record.State == "throttled"
}

func (a *API) getDialogModels(w http.ResponseWriter, r *http.Request) {
	if a.pilotConfig == nil {
		writeError(w, &ServiceError{Code: "dialog_unavailable", Message: "Диалог сейчас недоступен", Status: http.StatusServiceUnavailable})
		return
	}
	settings, err := a.pilotConfig.Read()
	if err != nil {
		writeError(w, err)
		return
	}
	out := []dialogModelView{}
	for index, brain := range settings.Settings.BrainChain {
		view := dialogModelView{Index: index, Model: brain.Model, Provider: brain.Provider,
			Note: strings.TrimSpace(brain.Note), Available: true}
		if engineResting(brain.Model) {
			view.Available, view.Reason = false, "квота модели исчерпана, отдыхает"
		} else if providerBlocked(brain.Provider) {
			view.Available, view.Reason = false, "подписка сейчас заблокирована"
		}
		out = append(out, view)
	}
	writeJSON(w, http.StatusOK, map[string]any{"models": out})
}
