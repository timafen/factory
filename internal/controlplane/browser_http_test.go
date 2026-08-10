package controlplane

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/owainlewis/factory/internal/serverbrowser"
)

type fakeBrowser struct {
	called  string
	started chan struct{}
	release chan struct{}
	png     []byte
}

func (browser *fakeBrowser) Capture(_ context.Context, value string) (serverbrowser.Capture, error) {
	browser.called = value
	if browser.started != nil {
		browser.started <- struct{}{}
		<-browser.release
	}
	png := browser.png
	if png == nil {
		png = []byte("png")
	}
	return serverbrowser.Capture{URL: value, PNG: png}, nil
}

func TestCaptureBrowserRejectsPNGOverDialogLimit(t *testing.T) {
	browser := &fakeBrowser{png: make([]byte, serverbrowser.MaxPNGBytes+1)}
	api := &API{browser: browser}
	request := httptest.NewRequest(http.MethodPost, "/api/v1/browser/capture", strings.NewReader(`{"url":"https://staging-automation.tarser.net/"}`))
	request.Header.Set("Content-Type", "application/json")
	response := httptest.NewRecorder()
	api.captureBrowser(response, request)
	if response.Code != http.StatusBadGateway || !strings.Contains(response.Body.String(), "browser_capture_too_large") {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
}

func TestCaptureBrowserRejectsOversizedRequest(t *testing.T) {
	browser := &fakeBrowser{}
	api := &API{browser: browser, browserSlots: make(chan struct{}, 1)}
	body := `{"url":"https://staging-automation.tarser.net/` + strings.Repeat("x", 4096) + `"}`
	request := httptest.NewRequest(http.MethodPost, "/api/v1/browser/capture", strings.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	response := httptest.NewRecorder()
	api.captureBrowser(response, request)
	if response.Code != http.StatusRequestEntityTooLarge || browser.called != "" {
		t.Fatalf("status=%d called=%q body=%s", response.Code, browser.called, response.Body.String())
	}
}

func TestCaptureBrowserRejectsRequestWhileSlotIsOccupied(t *testing.T) {
	browser := &fakeBrowser{started: make(chan struct{}, 1), release: make(chan struct{})}
	api := &API{browser: browser, browserSlots: make(chan struct{}, 1)}
	firstDone := make(chan struct{})
	go func() {
		defer close(firstDone)
		request := httptest.NewRequest(http.MethodPost, "/api/v1/browser/capture", strings.NewReader(`{"url":"https://staging-automation.tarser.net/first"}`))
		request.Header.Set("Content-Type", "application/json")
		api.captureBrowser(httptest.NewRecorder(), request)
	}()
	<-browser.started

	request := httptest.NewRequest(http.MethodPost, "/api/v1/browser/capture", strings.NewReader(`{"url":"https://staging-automation.tarser.net/second"}`))
	request.Header.Set("Content-Type", "application/json")
	response := httptest.NewRecorder()
	api.captureBrowser(response, request)
	if response.Code != http.StatusTooManyRequests || !strings.Contains(response.Body.String(), "browser_busy") {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	close(browser.release)
	<-firstDone
}

func TestCaptureBrowserRejectsUnsafeMutationBeforeTakingSlot(t *testing.T) {
	for _, test := range []struct {
		name        string
		contentType string
		origin      string
		status      int
		code        string
	}{
		{name: "non JSON", contentType: "text/plain", status: http.StatusUnsupportedMediaType, code: "json_required"},
		{name: "cross origin", contentType: "application/json", origin: "https://evil.example", status: http.StatusForbidden, code: "cross_origin_request"},
	} {
		t.Run(test.name, func(t *testing.T) {
			browser := &fakeBrowser{}
			slots := make(chan struct{}, 1)
			slots <- struct{}{}
			api := &API{browser: browser, browserSlots: slots}
			request := httptest.NewRequest(http.MethodPost, "/api/v1/browser/capture", strings.NewReader(`{"url":"https://staging-automation.tarser.net/"}`))
			request.Header.Set("Content-Type", test.contentType)
			if test.origin != "" {
				request.Header.Set("Origin", test.origin)
			}
			response := httptest.NewRecorder()
			api.captureBrowser(response, request)
			if response.Code != test.status || !strings.Contains(response.Body.String(), test.code) || browser.called != "" {
				t.Fatalf("status=%d called=%q body=%s", response.Code, browser.called, response.Body.String())
			}
			if len(slots) != 1 {
				t.Fatal("unsafe request changed browser slot state")
			}
		})
	}
}

func TestCaptureBrowserAllowsStandPath(t *testing.T) {
	browser := &fakeBrowser{}
	api := &API{browser: browser}
	request := httptest.NewRequest(http.MethodPost, "/api/v1/browser/capture", strings.NewReader(`{"url":"https://staging-automation.tarser.net/orders"}`))
	request.Header.Set("Content-Type", "application/json")
	response := httptest.NewRecorder()
	api.captureBrowser(response, request)
	if response.Code != http.StatusOK || browser.called != "https://staging-automation.tarser.net/orders" {
		t.Fatalf("capture status=%d called=%q body=%s", response.Code, browser.called, response.Body.String())
	}
}

func TestCaptureBrowserRejectsEveryOtherOriginBeforeLaunch(t *testing.T) {
	browser := &fakeBrowser{}
	api := &API{browser: browser}
	for _, value := range []string{"https://automation.tarser.net", "https://example.com", "http://localhost:3000", "https://10.0.0.1"} {
		request := httptest.NewRequest(http.MethodPost, "/api/v1/browser/capture", strings.NewReader(`{"url":"`+value+`"}`))
		request.Header.Set("Content-Type", "application/json")
		response := httptest.NewRecorder()
		api.captureBrowser(response, request)
		if response.Code != http.StatusBadRequest {
			t.Errorf("%s status=%d body=%s", value, response.Code, response.Body.String())
		}
	}
	if browser.called != "" {
		t.Fatalf("browser launched for blocked URL %q", browser.called)
	}
}
