package serverbrowser

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/netip"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

const AllowedOrigin = "https://staging-automation.tarser.net"

type Capture struct {
	URL string
	PNG []byte
}

type Runner struct {
	Executable string
}

func ValidateURL(value string) (*url.URL, error) {
	parsed, err := url.Parse(value)
	if err != nil || parsed.Scheme != "https" || parsed.Host != "staging-automation.tarser.net" || parsed.User != nil {
		return nil, fmt.Errorf("browser URL must use %s", AllowedOrigin)
	}
	return parsed, nil
}

func (runner Runner) Capture(ctx context.Context, value string) (Capture, error) {
	parsed, err := ValidateURL(value)
	if err != nil {
		return Capture{}, err
	}
	executable, err := runner.resolveExecutable()
	if err != nil {
		return Capture{}, err
	}
	directory, err := os.MkdirTemp("", "factory-browser-*")
	if err != nil {
		return Capture{}, fmt.Errorf("create browser workspace: %w", err)
	}
	defer os.RemoveAll(directory)
	output := filepath.Join(directory, "capture.png")
	profile := filepath.Join(directory, "profile")

	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return Capture{}, fmt.Errorf("start browser allowlist proxy: %w", err)
	}
	proxy := &http.Server{Handler: http.HandlerFunc(proxyRequest), ReadHeaderTimeout: 5 * time.Second}
	defer proxy.Close()
	go func() { _ = proxy.Serve(listener) }()

	arguments := []string{
		"--headless=new", "--disable-gpu", "--disable-quic", "--disable-background-networking",
		"--disable-component-update", "--no-first-run", "--no-default-browser-check",
		"--user-data-dir=" + profile,
		"--proxy-server=http://" + listener.Addr().String(), "--proxy-bypass-list=<-loopback>",
		// WebRTC can otherwise create direct UDP sockets which bypass Chromium's
		// HTTP proxy. This policy permits only proxied traffic.
		"--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
		"--window-size=1440,1000", "--hide-scrollbars", "--screenshot=" + output, parsed.String(),
	}
	command := exec.CommandContext(ctx, executable, arguments...)
	command.Dir = directory
	combined, err := command.CombinedOutput()
	if err != nil {
		return Capture{}, fmt.Errorf("capture stand in Chromium: %w: %s", err, strings.TrimSpace(string(combined)))
	}
	png, err := os.ReadFile(output)
	if err != nil {
		return Capture{}, fmt.Errorf("read browser capture: %w", err)
	}
	if len(png) < 8 || string(png[:8]) != "\x89PNG\r\n\x1a\n" {
		return Capture{}, errors.New("Chromium returned an invalid PNG capture")
	}
	return Capture{URL: parsed.String(), PNG: png}, nil
}

func (runner Runner) resolveExecutable() (string, error) {
	if strings.TrimSpace(runner.Executable) != "" {
		return runner.Executable, nil
	}
	if configured := strings.TrimSpace(os.Getenv("FACTORY_BROWSER_EXECUTABLE")); configured != "" {
		return configured, nil
	}
	for _, candidate := range []string{"chromium", "chromium-browser", "google-chrome-stable", "google-chrome"} {
		if path, err := exec.LookPath(candidate); err == nil {
			return path, nil
		}
	}
	if home, err := os.UserHomeDir(); err == nil {
		patterns := []string{
			filepath.Join(home, ".cache", "ms-playwright", "chromium-*", "chrome-linux", "chrome"),
			filepath.Join(home, ".cache", "ms-playwright", "chromium-*", "chrome-linux64", "chrome"),
			filepath.Join(home, ".cache", "ms-playwright", "chromium_headless_shell-*", "chrome-headless-shell-linux64", "chrome-headless-shell"),
		}
		for _, pattern := range patterns {
			matches, _ := filepath.Glob(pattern)
			for _, match := range matches {
				if info, statErr := os.Stat(match); statErr == nil && info.Mode().IsRegular() && info.Mode()&0o111 != 0 {
					return match, nil
				}
			}
		}
	}
	return "", errors.New("supported Chromium not found; set FACTORY_BROWSER_EXECUTABLE")
}

func proxyRequest(writer http.ResponseWriter, request *http.Request) {
	host := request.URL.Hostname()
	if request.Method != http.MethodConnect || !strings.EqualFold(host, "staging-automation.tarser.net") || request.URL.Port() != "443" {
		http.Error(writer, "destination is outside the Factory browser allowlist", http.StatusForbidden)
		return
	}
	address, err := approvedAddress(request.Context())
	if err != nil {
		http.Error(writer, "stand address is unsafe or unavailable", http.StatusBadGateway)
		return
	}
	upstream, err := net.DialTimeout("tcp", address, 10*time.Second)
	if err != nil {
		http.Error(writer, "stand is unavailable", http.StatusBadGateway)
		return
	}
	defer upstream.Close()
	hijacker, ok := writer.(http.Hijacker)
	if !ok {
		http.Error(writer, "proxy transport unavailable", http.StatusInternalServerError)
		return
	}
	client, _, err := hijacker.Hijack()
	if err != nil {
		return
	}
	defer client.Close()
	_, _ = io.WriteString(client, "HTTP/1.1 200 Connection Established\r\n\r\n")
	done := make(chan struct{}, 1)
	go func() { _, _ = io.Copy(upstream, client); done <- struct{}{} }()
	_, _ = io.Copy(client, upstream)
	<-done
}

func approvedAddress(ctx context.Context) (string, error) {
	addresses, err := net.DefaultResolver.LookupIP(ctx, "ip", "staging-automation.tarser.net")
	if err != nil {
		return "", err
	}
	for _, address := range addresses {
		if publicAddress(address) {
			return net.JoinHostPort(address.String(), "443"), nil
		}
	}
	return "", errors.New("approved stand resolved only to non-public addresses")
}

func publicAddress(address net.IP) bool {
	parsed, ok := netip.AddrFromSlice(address)
	if !ok {
		return false
	}
	parsed = parsed.Unmap()
	if !parsed.IsGlobalUnicast() {
		return false
	}
	for _, prefix := range specialAddressPrefixes {
		if prefix.Contains(parsed) {
			return false
		}
	}
	if parsed.Is6() && !publicIPv6Prefix.Contains(parsed) {
		return false
	}
	return true
}

var publicIPv6Prefix = netip.MustParsePrefix("2000::/3")

// specialAddressPrefixes contains non-public IANA special-purpose ranges. A
// resolved stand address must be globally routable and outside every range.
var specialAddressPrefixes = mustPrefixes(
	"0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16",
	"172.16.0.0/12", "192.0.0.0/24", "192.0.2.0/24", "192.31.196.0/24", "192.52.193.0/24",
	"192.88.99.0/24", "192.168.0.0/16", "192.175.48.0/24", "198.18.0.0/15",
	"198.51.100.0/24", "203.0.113.0/24", "240.0.0.0/4",
	"64:ff9b::/96", "64:ff9b:1::/48", "100::/64", "100:0:0:1::/64", "2001::/23",
	"2001:db8::/32", "2002::/16", "2620:4f:8000::/48", "3fff::/20", "5f00::/16", "fc00::/7", "fe80::/10",
)

func mustPrefixes(values ...string) []netip.Prefix {
	prefixes := make([]netip.Prefix, 0, len(values))
	for _, value := range values {
		prefixes = append(prefixes, netip.MustParsePrefix(value))
	}
	return prefixes
}
