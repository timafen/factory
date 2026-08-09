package controlplane

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"os/exec"
	"strings"
)

// sandboxKeysRunner is deliberately narrower than a command executor: neither
// the browser nor a caller can choose an environment, role, or Django command.
type sandboxKeysRunner interface {
	Start(context.Context) ([]byte, error)
	Status(context.Context, string) ([]byte, error)
}

type commandSandboxKeysRunner struct{}

func (commandSandboxKeysRunner) Start(ctx context.Context) ([]byte, error) {
	return exec.CommandContext(ctx, "sudo", "-n", "/usr/local/bin/fx", "staging", "sandbox", "bootstrap-accounts", "--interactive-bootstrap", "--role=seller").Output()
}

func (commandSandboxKeysRunner) Status(ctx context.Context, operationID string) ([]byte, error) {
	return exec.CommandContext(ctx, "sudo", "-n", "/usr/local/bin/fx", "staging", "sandbox", "bootstrap-accounts", "--consent-status="+operationID).Output()
}

type ebayConsentResponse struct {
	OperationID string `json:"operation_id"`
	ConsentURL  string `json:"consent_url,omitempty"`
	Status      string `json:"status"`
	Message     string `json:"message,omitempty"`
}

type ebayConsentStatusResponse struct {
	OperationID string `json:"operation_id"`
	Status      string `json:"status"`
	Message     string `json:"message,omitempty"`
}

func decodeEbayConsent(body []byte, start bool) (ebayConsentResponse, error) {
	var response ebayConsentResponse
	if err := json.Unmarshal(body, &response); err != nil {
		return response, errors.New("sandbox consent returned an invalid response")
	}
	if response.OperationID == "" || !validConsentStatus(response.Status) || (start && !validConsentURL(response.ConsentURL)) {
		return response, errors.New("sandbox consent returned an invalid response")
	}
	return response, nil
}

func decodeEbayConsentStatus(body []byte, operationID string) (ebayConsentStatusResponse, error) {
	var response ebayConsentStatusResponse
	if err := json.Unmarshal(body, &response); err != nil {
		return response, errors.New("sandbox consent returned an invalid response")
	}
	if response.OperationID != operationID || !validConsentStatus(response.Status) {
		return response, errors.New("sandbox consent returned an invalid response")
	}
	return response, nil
}

func validConsentStatus(status string) bool {
	return status == "pending" || status == "authorized" || status == "failed" || status == "expired"
}

func validConsentURL(value string) bool {
	return strings.HasPrefix(value, "https://") && !strings.ContainsAny(value, "\r\n")
}

func (a *API) startEbaySellerConsent(w http.ResponseWriter, r *http.Request) {
	body, err := a.sandboxKeys.Start(r.Context())
	response := ebayConsentResponse{}
	if err == nil {
		response, err = decodeEbayConsent(body, true)
	}
	if err != nil {
		writeError(w, &ServiceError{Code: "sandbox_consent_unavailable", Message: "sandbox consent could not be started", Status: http.StatusBadGateway, Err: err})
		return
	}
	writeJSON(w, http.StatusOK, response)
}

func (a *API) ebaySellerConsentStatus(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("operation_id")
	if id == "" || strings.ContainsAny(id, "/\r\n") {
		writeError(w, invalid("invalid_operation_id", "operation_id is invalid"))
		return
	}
	body, err := a.sandboxKeys.Status(r.Context(), id)
	response := ebayConsentStatusResponse{}
	if err == nil {
		response, err = decodeEbayConsentStatus(body, id)
	}
	if err != nil {
		writeError(w, &ServiceError{Code: "sandbox_consent_unavailable", Message: "sandbox consent status is unavailable", Status: http.StatusBadGateway, Err: err})
		return
	}
	writeJSON(w, http.StatusOK, response)
}
