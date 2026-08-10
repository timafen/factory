package serverbrowser

import (
	"context"
	"crypto/rand"
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
	"sync"
	"syscall"
	"time"
)

const AllowedOrigin = "https://staging-automation.tarser.net"

const MaxPNGBytes = 4 << 20

const (
	processTerminationGrace = 500 * time.Millisecond
	processWaitDelay        = 2 * time.Second
	proxyStartupTimeout     = 3 * time.Second
	proxyTunnelDeadline     = 45 * time.Second
)

type Capture struct {
	URL string
	PNG []byte
}

type Runner struct {
	Executable        string
	SandboxExecutable string
	ProxyListen       func(context.Context, string, int) (net.Listener, error)
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

	proxyAddress, err := privateProxyAddress()
	if err != nil {
		return Capture{}, fmt.Errorf("choose browser allowlist proxy address: %w", err)
	}
	proxyPort, err := availableProxyPort()
	if err != nil {
		return Capture{}, fmt.Errorf("choose browser allowlist proxy port: %w", err)
	}
	var proxy *allowlistProxy
	defer func() {
		if proxy != nil {
			_ = proxy.Close()
		}
	}()

	arguments := []string{
		"--headless=new", "--disable-gpu", "--disable-quic", "--disable-background-networking",
		"--disable-component-update", "--no-first-run", "--no-default-browser-check",
		"--user-data-dir=" + profile,
		"--window-size=1440,1000", "--hide-scrollbars", "--screenshot=" + output, parsed.String(),
	}
	sandboxExecutable, sandboxArguments := runner.sandboxCommand(proxyAddress, proxyPort, executable, arguments)
	command := exec.Command(sandboxExecutable, sandboxArguments...)
	command.Dir = directory
	combined, err := runProcessGroup(ctx, command, func() error {
		listener, listenErr := runner.listenProxy(ctx, proxyAddress, proxyPort)
		if listenErr != nil {
			return fmt.Errorf("bind browser allowlist proxy to private veth %s: %w", proxyAddress, listenErr)
		}
		proxy = newAllowlistProxy()
		go func() { _ = proxy.server.Serve(listener) }()
		return nil
	})
	if err != nil {
		return Capture{}, fmt.Errorf("capture stand in Chromium: %w: %s", err, strings.TrimSpace(string(combined)))
	}
	file, err := os.Open(output)
	if err != nil {
		return Capture{}, fmt.Errorf("read browser capture: %w", err)
	}
	defer file.Close()
	png, err := io.ReadAll(io.LimitReader(file, MaxPNGBytes+1))
	if err != nil {
		return Capture{}, fmt.Errorf("read browser capture: %w", err)
	}
	if len(png) > MaxPNGBytes {
		return Capture{}, fmt.Errorf("Chromium PNG capture exceeds %d bytes", MaxPNGBytes)
	}
	if len(png) < 8 || string(png[:8]) != "\x89PNG\r\n\x1a\n" {
		return Capture{}, errors.New("Chromium returned an invalid PNG capture")
	}
	return Capture{URL: parsed.String(), PNG: png}, nil
}

// runProcessGroup keeps sudo, the namespace launcher and every Chromium child
// in one process group. Cancelling a capture therefore cannot leave a browser
// holding the command pipes or its network namespace behind.
func runProcessGroup(ctx context.Context, command *exec.Cmd, afterStart func() error) ([]byte, error) {
	command.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	command.WaitDelay = processWaitDelay
	var output strings.Builder
	command.Stdout = &output
	command.Stderr = &output
	if err := command.Start(); err != nil {
		return nil, err
	}
	if afterStart != nil {
		if err := afterStart(); err != nil {
			_ = syscall.Kill(-command.Process.Pid, syscall.SIGKILL)
			_ = command.Wait()
			return []byte(output.String()), err
		}
	}
	done := make(chan error, 1)
	go func() { done <- command.Wait() }()
	select {
	case err := <-done:
		return []byte(output.String()), err
	case <-ctx.Done():
	}

	// Negative PID addresses the process group created above. TERM gives the
	// launcher time to remove its namespace; KILL bounds cleanup even when a
	// Chromium descendant ignores TERM.
	_ = syscall.Kill(-command.Process.Pid, syscall.SIGTERM)
	timer := time.NewTimer(processTerminationGrace)
	defer timer.Stop()
	select {
	case <-done:
		// The launcher can exit from its TERM trap while a detached descendant
		// still belongs to the group. Do not mistake leader exit for tree exit.
		_ = syscall.Kill(-command.Process.Pid, syscall.SIGKILL)
		return []byte(output.String()), ctx.Err()
	case <-timer.C:
		_ = syscall.Kill(-command.Process.Pid, syscall.SIGKILL)
		<-done
		return []byte(output.String()), ctx.Err()
	}
}

func (runner Runner) sandboxCommand(address string, port int, executable string, arguments []string) (string, []string) {
	prefix := []string{"-n", "/usr/local/bin/fx", "factory", "browser-sandbox", "run"}
	sandbox := "/usr/bin/sudo"
	if strings.TrimSpace(runner.SandboxExecutable) != "" {
		sandbox = runner.SandboxExecutable
		prefix = nil
	}
	result := append(prefix, "--proxy-address="+address, fmt.Sprintf("--proxy-port=%d", port), "--", executable)
	result = append(result, arguments...)
	return sandbox, result
}

func privateProxyAddress() (string, error) {
	var value [2]byte
	if _, err := rand.Read(value[:]); err != nil {
		return "", err
	}
	// Each capture gets a random /30 inside the link-local range. The first
	// usable address belongs only to its host-side veth; the second belongs to
	// Chromium's isolated namespace.
	return fmt.Sprintf("169.254.%d.%d", int(value[0])%250+1, (int(value[1])%64)*4+1), nil
}

func availableProxyPort() (int, error) {
	listener, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		return 0, err
	}
	port := listener.Addr().(*net.TCPAddr).Port
	if err := listener.Close(); err != nil {
		return 0, err
	}
	return port, nil
}

func (runner Runner) listenProxy(ctx context.Context, address string, port int) (net.Listener, error) {
	if runner.ProxyListen != nil {
		return runner.ProxyListen(ctx, address, port)
	}
	deadline := time.Now().Add(proxyStartupTimeout)
	for {
		listener, err := net.ListenTCP("tcp4", &net.TCPAddr{IP: net.ParseIP(address), Port: port})
		if err == nil {
			return listener, nil
		}
		if !errors.Is(err, syscall.EADDRNOTAVAIL) || time.Now().After(deadline) {
			return nil, err
		}
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-time.After(10 * time.Millisecond):
		}
	}
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

type allowlistProxy struct {
	server      *http.Server
	mu          sync.Mutex
	connections map[net.Conn]struct{}
	closed      bool
}

func newAllowlistProxy() *allowlistProxy {
	proxy := &allowlistProxy{connections: make(map[net.Conn]struct{})}
	proxy.server = &http.Server{
		Handler:           http.HandlerFunc(proxy.proxyRequest),
		ReadHeaderTimeout: 5 * time.Second,
	}
	return proxy
}

func (proxy *allowlistProxy) Close() error {
	err := proxy.server.Close()
	proxy.mu.Lock()
	proxy.closed = true
	connections := make([]net.Conn, 0, len(proxy.connections))
	for connection := range proxy.connections {
		connections = append(connections, connection)
	}
	proxy.mu.Unlock()
	for _, connection := range connections {
		_ = connection.Close()
	}
	return err
}

func (proxy *allowlistProxy) track(connections ...net.Conn) bool {
	proxy.mu.Lock()
	defer proxy.mu.Unlock()
	if proxy.closed {
		return false
	}
	for _, connection := range connections {
		proxy.connections[connection] = struct{}{}
	}
	return true
}

func (proxy *allowlistProxy) untrack(connections ...net.Conn) {
	proxy.mu.Lock()
	defer proxy.mu.Unlock()
	for _, connection := range connections {
		delete(proxy.connections, connection)
	}
}

func proxyRequest(writer http.ResponseWriter, request *http.Request) {
	newAllowlistProxy().proxyRequest(writer, request)
}

func (proxy *allowlistProxy) proxyRequest(writer http.ResponseWriter, request *http.Request) {
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
	upstream, err := (&net.Dialer{Timeout: 10 * time.Second}).DialContext(request.Context(), "tcp", address)
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
	if !proxy.track(client, upstream) {
		_ = client.Close()
		return
	}
	defer proxy.untrack(client, upstream)
	deadline := time.Now().Add(proxyTunnelDeadline)
	_ = client.SetDeadline(deadline)
	_ = upstream.SetDeadline(deadline)
	_, _ = io.WriteString(client, "HTTP/1.1 200 Connection Established\r\n\r\n")
	done := make(chan struct{}, 2)
	go func() { _, _ = io.Copy(upstream, client); done <- struct{}{} }()
	go func() { _, _ = io.Copy(client, upstream); done <- struct{}{} }()
	<-done
	_ = client.Close()
	_ = upstream.Close()
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
