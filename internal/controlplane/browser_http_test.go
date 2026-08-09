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
}

func (browser *fakeBrowser) Capture(_ context.Context, value string) (serverbrowser.Capture, error) {
	browser.called = value
	if browser.started != nil {
		browser.started <- struct{}{}
		<-browser.release
	}
	return serverbrowser.Capture{URL: value, PNG: []byte("png")}, nil
}

func TestCaptureBrowserRejectsOversizedRequest(t *testing.T) {
	browser := &fakeBrowser{}
	api := &API{browser: browser, browserSlots: make(chan struct{}, 1)}
	body := `{"url":"https://staging-automation.tarser.net/` + strings.Repeat("x", 4096) + `"}`
	request := httptest.NewRequest(http.MethodPost, "/api/v1/browser/capture", strings.NewReader(body))
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
		api.captureBrowser(httptest.NewRecorder(), request)
	}()
	<-browser.started

	request := httptest.NewRequest(http.MethodPost, "/api/v1/browser/capture", strings.NewReader(`{"url":"https://staging-automation.tarser.net/second"}`))
	response := httptest.NewRecorder()
	api.captureBrowser(response, request)
	if response.Code != http.StatusTooManyRequests || !strings.Contains(response.Body.String(), "browser_busy") {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	close(browser.release)
	<-firstDone
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
