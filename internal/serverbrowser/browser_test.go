package serverbrowser

import (
	"context"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestValidateURLAllowsOnlyApprovedStandOrigin(t *testing.T) {
	allowed := []string{AllowedOrigin, AllowedOrigin + "/orders/42?tab=history#latest"}
	for _, value := range allowed {
		if _, err := ValidateURL(value); err != nil {
			t.Errorf("ValidateURL(%q): %v", value, err)
		}
	}
	blocked := []string{
		"https://automation.tarser.net", "https://ops.tarser.net", "https://staging.ops.tarser.net",
		"http://staging-automation.tarser.net", "https://staging-automation.tarser.net.evil.test",
		"https://localhost", "https://127.0.0.1", "https://user@staging-automation.tarser.net",
	}
	for _, value := range blocked {
		if _, err := ValidateURL(value); err == nil {
			t.Errorf("ValidateURL(%q) unexpectedly allowed", value)
		}
	}
}

func TestProxyRejectsRedirectDestinationsOutsideAllowlist(t *testing.T) {
	for _, target := range []string{"automation.tarser.net:443", "localhost:443", "10.0.0.1:443", "example.com:443"} {
		request := httptest.NewRequest(http.MethodConnect, "http://"+target, nil)
		response := httptest.NewRecorder()
		proxyRequest(response, request)
		if response.Code != http.StatusForbidden {
			t.Errorf("CONNECT %s status=%d", target, response.Code)
		}
	}
}

func TestPublicAddressRejectsInternalTargets(t *testing.T) {
	for _, value := range []string{"127.0.0.1", "10.0.0.1", "172.16.0.1", "192.168.1.1", "::1", "fe80::1", "fc00::1"} {
		if publicAddress(net.ParseIP(value)) {
			t.Errorf("internal address %s allowed", value)
		}
	}
	if !publicAddress(net.ParseIP("203.0.113.10")) {
		t.Error("public address rejected")
	}
}

func TestRunnerInvokesChromiumThroughRestrictiveProxy(t *testing.T) {
	directory := t.TempDir()
	executable := filepath.Join(directory, "chromium")
	script := `#!/bin/sh
set -eu
printf '%s\n' "$@" >"` + filepath.Join(directory, "args") + `"
for argument do
  case "$argument" in --screenshot=*) output=${argument#--screenshot=};; esac
done
printf '\211PNG\r\n\032\nproof' >"$output"
`
	if err := os.WriteFile(executable, []byte(script), 0o700); err != nil {
		t.Fatal(err)
	}
	capture, err := (Runner{Executable: executable}).Capture(context.Background(), AllowedOrigin+"/orders")
	if err != nil {
		t.Fatal(err)
	}
	arguments, err := os.ReadFile(filepath.Join(directory, "args"))
	if err != nil {
		t.Fatal(err)
	}
	if capture.URL != AllowedOrigin+"/orders" || !strings.Contains(string(arguments), "--proxy-server=http://127.0.0.1:") || !strings.Contains(string(arguments), "--disable-quic") || !strings.Contains(string(arguments), "--no-sandbox") {
		t.Fatalf("capture=%+v args=%s", capture, arguments)
	}
}
