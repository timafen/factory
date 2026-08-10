package serverbrowser

import (
	"context"
	"errors"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
	"time"
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

func TestRunnerDefaultsToPrivilegedFactorySandbox(t *testing.T) {
	executable, arguments := (Runner{}).sandboxCommand(43210, "/usr/bin/chromium", []string{"--headless=new"})
	want := []string{"-n", "/usr/local/bin/fx", "factory", "browser-sandbox", "run", "--proxy-port=43210", "--", "/usr/bin/chromium", "--headless=new"}
	if executable != "/usr/bin/sudo" || strings.Join(arguments, "\x00") != strings.Join(want, "\x00") {
		t.Fatalf("sandbox command = %q %q", executable, arguments)
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
	for _, value := range []string{
		"0.0.0.1", "10.0.0.1", "100.64.0.1", "127.0.0.1", "169.254.1.1", "172.16.0.1",
		"192.0.0.1", "192.0.2.1", "192.168.1.1", "198.18.0.1", "198.51.100.1", "203.0.113.10", "240.0.0.1",
		"::1", "64:ff9b::1", "100::1", "100:0:0:1::1", "2001:db8::1", "2002::1", "3fff::1", "4000::1", "5f00::1", "fec0::1", "fe80::1", "fc00::1", "ff00::1",
	} {
		if publicAddress(net.ParseIP(value)) {
			t.Errorf("special address %s allowed", value)
		}
	}
	for _, value := range []string{"8.8.8.8", "1.1.1.1", "2606:4700:4700::1111"} {
		if !publicAddress(net.ParseIP(value)) {
			t.Errorf("public address %s rejected", value)
		}
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
	sandbox := fakeSandbox(t, directory)
	capture, err := (Runner{Executable: executable, SandboxExecutable: sandbox}).Capture(context.Background(), AllowedOrigin+"/orders")
	if err != nil {
		t.Fatal(err)
	}
	arguments, err := os.ReadFile(filepath.Join(directory, "args"))
	if err != nil {
		t.Fatal(err)
	}
	argumentText := string(arguments)
	if capture.URL != AllowedOrigin+"/orders" || !strings.Contains(argumentText, "--proxy-server=http://169.254.1.1:") || !strings.Contains(argumentText, "--disable-quic") || strings.Contains(argumentText, "--no-sandbox") {
		t.Fatalf("capture=%+v args=%s", capture, arguments)
	}
	var profile string
	for _, argument := range strings.Split(argumentText, "\n") {
		if strings.HasPrefix(argument, "--user-data-dir=") {
			profile = strings.TrimPrefix(argument, "--user-data-dir=")
		}
	}
	if profile == "" || filepath.Dir(profile) == "." || filepath.Base(profile) != "profile" {
		t.Fatalf("Chromium did not receive an isolated temporary profile: %q", profile)
	}
	if _, err := os.Stat(profile); !os.IsNotExist(err) {
		t.Fatalf("temporary Chromium profile was not removed: %v", err)
	}
}

func TestRunnerUsesMandatoryNetworkSandbox(t *testing.T) {
	directory := t.TempDir()
	executable := filepath.Join(directory, "chromium")
	script := `#!/bin/sh
set -eu
for argument do
  case "$argument" in
    --screenshot=*) output=${argument#--screenshot=} ;;
  esac
done
printf '\211PNG\r\n\032\nproof' >"$output"
`
	if err := os.WriteFile(executable, []byte(script), 0o700); err != nil {
		t.Fatal(err)
	}
	if _, err := (Runner{Executable: executable, SandboxExecutable: fakeSandbox(t, directory)}).Capture(context.Background(), AllowedOrigin+"/webrtc-internal-address"); err != nil {
		t.Fatalf("direct WebRTC connection to an internal address was not blocked: %v", err)
	}
}

func TestRunnerRejectsPNGOverDialogLimit(t *testing.T) {
	directory := t.TempDir()
	executable := filepath.Join(directory, "chromium")
	script := `#!/bin/sh
set -eu
for argument do case "$argument" in --screenshot=*) output=${argument#--screenshot=};; esac; done
printf '\211PNG\r\n\032\n' >"$output"
dd if=/dev/zero bs=1 count=` + fmt.Sprint(MaxPNGBytes) + ` >>"$output" 2>/dev/null
`
	if err := os.WriteFile(executable, []byte(script), 0o700); err != nil {
		t.Fatal(err)
	}
	_, err := (Runner{Executable: executable, SandboxExecutable: fakeSandbox(t, directory)}).Capture(context.Background(), AllowedOrigin)
	if err == nil || !strings.Contains(err.Error(), "exceeds") {
		t.Fatalf("oversized PNG error = %v", err)
	}
}

func TestRunnerCancellationTerminatesEntireBrowserProcessGroup(t *testing.T) {
	directory := t.TempDir()
	pidFile := filepath.Join(directory, "child.pid")
	namespaceMarker := filepath.Join(directory, "namespace.exists")
	executable := filepath.Join(directory, "chromium")
	script := `#!/bin/sh
trap '' TERM
sh -c 'trap "" TERM; while :; do sleep 1; done' &
child=$!
printf '%s\n' "$child" >"` + pidFile + `"
wait "$child"
`
	if err := os.WriteFile(executable, []byte(script), 0o700); err != nil {
		t.Fatal(err)
	}
	sandbox := filepath.Join(directory, "browser-sandbox")
	sandboxScript := `#!/bin/sh
set -eu
touch "` + namespaceMarker + `"
cleanup() { rm -f "` + namespaceMarker + `"; exit 143; }
trap cleanup TERM INT
port=${1#--proxy-port=}; shift
test "$1" = --; shift
"$@" "--proxy-server=http://169.254.1.1:$port" &
wait $!
`
	if err := os.WriteFile(sandbox, []byte(sandboxScript), 0o700); err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()
	started := time.Now()
	_, err := (Runner{Executable: executable, SandboxExecutable: sandbox}).Capture(ctx, AllowedOrigin)
	if !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("capture error = %v", err)
	}
	if elapsed := time.Since(started); elapsed > processTerminationGrace+processWaitDelay+time.Second {
		t.Fatalf("cancelled capture took %s", elapsed)
	}
	data, err := os.ReadFile(pidFile)
	if err != nil {
		t.Fatal(err)
	}
	var pid int
	if _, err := fmt.Sscanf(strings.TrimSpace(string(data)), "%d", &pid); err != nil {
		t.Fatal(err)
	}
	deadline := time.Now().Add(time.Second)
	for syscall.Kill(pid, 0) == nil && time.Now().Before(deadline) {
		time.Sleep(10 * time.Millisecond)
	}
	if err := syscall.Kill(pid, 0); err == nil {
		t.Fatalf("browser child %d survived capture cancellation", pid)
	}
	if _, err := os.Stat(namespaceMarker); !os.IsNotExist(err) {
		t.Fatalf("sandbox namespace marker survived cancellation: %v", err)
	}
}

func fakeSandbox(t *testing.T, directory string) string {
	t.Helper()
	path := filepath.Join(directory, "browser-sandbox")
	script := `#!/bin/sh
set -eu
port=${1#--proxy-port=}
shift
test "$1" = --
shift
executable=$1
shift
exec "$executable" "--proxy-server=http://169.254.1.1:$port" '--proxy-bypass-list=<-loopback>' "$@"
`
	if err := os.WriteFile(path, []byte(script), 0o700); err != nil {
		t.Fatal(err)
	}
	return path
}
