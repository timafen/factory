package controlplane

import (
	"net/http"

	"github.com/owainlewis/factory/internal/protocol"
)

func registerProjectOnboardingRoutes(mux *http.ServeMux, service *ProjectOnboardingService) {
	mux.HandleFunc("GET /api/v1/repositories/{repository_id}/onboarding", func(w http.ResponseWriter, r *http.Request) {
		card, err := service.Get(r.Context(), r.PathValue("repository_id"))
		if err != nil {
			writeError(w, err)
			return
		}
		writeJSON(w, http.StatusOK, card)
	})
	mux.HandleFunc("PUT /api/v1/repositories/{repository_id}/onboarding", func(w http.ResponseWriter, r *http.Request) {
		if !prepareMutation(w, r, protocol.MaxBodyBytes) {
			return
		}
		var input ProjectOnboardingInput
		if !decodeJSON(w, r, &input) {
			return
		}
		card, err := service.Put(r.Context(), r.PathValue("repository_id"), input)
		if err != nil {
			writeError(w, err)
			return
		}
		writeJSON(w, http.StatusOK, card)
	})
}
