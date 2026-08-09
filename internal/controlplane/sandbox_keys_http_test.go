package controlplane

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
)

type fakeSandboxKeysRunner struct {
	start, status []byte
	statusID      string
	err           error
}

func (f *fakeSandboxKeysRunner) Start(context.Context) ([]byte, error) { return f.start, f.err }
func (f *fakeSandboxKeysRunner) Status(_ context.Context, id string) ([]byte, error) {
	f.statusID = id
	return f.status, f.err
}

func TestEbaySellerConsentStartsAndReadsSafeStatus(t *testing.T) {
	runner := &fakeSandboxKeysRunner{start: []byte(`{"operation_id":"op-1","consent_url":"https://auth.example/consent","state":"private","status":"pending"}`), status: []byte(`{"operation_id":"op-1","access_token":"private","status":"authorized"}`)}
	api := &API{sandboxKeys: runner}
	start := httptest.NewRecorder()
	api.startEbaySellerConsent(start, httptest.NewRequest(http.MethodPost, "/api/v1/sandbox-keys/ebay-seller/consent", nil))
	if start.Code != http.StatusOK {
		t.Fatalf("start status = %d: %s", start.Code, start.Body.String())
	}
	if contains(start.Body.String(), "private") {
		t.Fatalf("start leaked private bridge fields: %s", start.Body.String())
	}
	status := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/api/v1/sandbox-keys/ebay-seller/consent/op-1", nil)
	req.SetPathValue("operation_id", "op-1")
	api.ebaySellerConsentStatus(status, req)
	if status.Code != http.StatusOK || runner.statusID != "op-1" || contains(status.Body.String(), "private") {
		t.Fatalf("status = %d, id = %q", status.Code, runner.statusID)
	}
}

func TestEbaySellerConsentRejectsSecretsAndMalformedResults(t *testing.T) {
	runner := &fakeSandboxKeysRunner{start: []byte(`{"operation_id":"op-1","consent_url":"http://unsafe.example","access_token":"secret","status":"pending"}`)}
	api := &API{sandboxKeys: runner}
	w := httptest.NewRecorder()
	api.startEbaySellerConsent(w, httptest.NewRequest(http.MethodPost, "/api/v1/sandbox-keys/ebay-seller/consent", nil))
	if w.Code != http.StatusBadGateway || w.Body.String() == "" {
		t.Fatalf("unsafe response = %d: %s", w.Code, w.Body.String())
	}
	if got := w.Body.String(); contains(got, "op-1") || contains(got, "unsafe.example") {
		t.Fatalf("response leaked bridge data: %s", got)
	}
}

func TestEbaySellerConsentStatusRejectsSubstitutedOperation(t *testing.T) {
	runner := &fakeSandboxKeysRunner{status: []byte(`{"operation_id":"op-other","status":"authorized"}`)}
	api := &API{sandboxKeys: runner}
	w := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/api/v1/sandbox-keys/ebay-seller/consent/op-1", nil)
	req.SetPathValue("operation_id", "op-1")
	api.ebaySellerConsentStatus(w, req)
	if w.Code != http.StatusBadGateway || contains(w.Body.String(), "op-other") {
		t.Fatalf("substituted operation response = %d: %s", w.Code, w.Body.String())
	}
}

func TestEbaySellerConsentStatusDropsURLAndSecrets(t *testing.T) {
	runner := &fakeSandboxKeysRunner{status: []byte(`{"operation_id":"op-1","status":"pending","message":"still waiting","consent_url":"javascript:alert(1)","access_token":"secret","refresh_token":"private"}`)}
	api := &API{sandboxKeys: runner}
	w := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/api/v1/sandbox-keys/ebay-seller/consent/op-1", nil)
	req.SetPathValue("operation_id", "op-1")
	api.ebaySellerConsentStatus(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("status response = %d: %s", w.Code, w.Body.String())
	}
	for _, forbidden := range []string{"consent_url", "javascript:", "access_token", "secret", "refresh_token", "private"} {
		if contains(w.Body.String(), forbidden) {
			t.Fatalf("status leaked %q: %s", forbidden, w.Body.String())
		}
	}
}

func contains(s, part string) bool {
	return len(part) > 0 && len(s) >= len(part) && (func() bool {
		for i := 0; i+len(part) <= len(s); i++ {
			if s[i:i+len(part)] == part {
				return true
			}
		}
		return false
	})()
}
