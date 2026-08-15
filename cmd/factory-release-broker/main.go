package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"net"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"sync/atomic"
	"syscall"
	"time"

	"github.com/owainlewis/factory/internal/releasebroker"
)

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, "factory-release-broker:", err)
		os.Exit(1)
	}
}

func run() error {
	socket := flag.String("socket", "/run/factory/project-release-broker.sock", "Unix socket path")
	stateDir := flag.String("state-dir", "/var/lib/factory/release-broker", "durable operation state directory")
	fxExecutable := flag.String("fx-executable", "", "path to the fixed fx release driver")
	factoryReleaseExecutable := flag.String("factory-release-executable", "", "path to the fixed Factory release driver")
	liveAcceptanceExecutable := flag.String("live-acceptance-executable", "", "path to the fixed read-only live acceptance checker")
	flag.Parse()
	// The installed broker owns privileged paths and must remain root-only.
	// An explicitly isolated socket and state directory are safe for the
	// integration fixture, which executes no privileged release driver.
	if os.Geteuid() != 0 && (*socket == "/run/factory/project-release-broker.sock" || *stateDir == "/var/lib/factory/release-broker") {
		return errors.New("must run as root")
	}
	if err := prepareSocket(*socket); err != nil {
		return err
	}
	oldMask := syscall.Umask(0o007)
	listener, err := net.Listen("unix", *socket)
	syscall.Umask(oldMask)
	if err != nil {
		return fmt.Errorf("listen on Unix socket: %w", err)
	}
	defer func() {
		_ = listener.Close()
		_ = os.Remove(*socket)
	}()
	if err := os.Chmod(*socket, 0o660); err != nil {
		return fmt.Errorf("secure Unix socket permissions: %w", err)
	}

	broker, err := releasebroker.NewAt(*stateDir, releasebroker.FXExecutor{
		Executable: *fxExecutable, FactoryReleaseExecutable: *factoryReleaseExecutable,
	})
	if err != nil {
		return fmt.Errorf("prepare durable state: %w", err)
	}
	if err := broker.ConfigureAcceptance(*liveAcceptanceExecutable); err != nil {
		return fmt.Errorf("configure live acceptance: %w", err)
	}
	server := &http.Server{
		Handler:           broker.Handler(),
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       10 * time.Second,
		WriteTimeout:      10 * time.Second,
		IdleTimeout:       30 * time.Second,
	}
	executable, err := os.Executable()
	if err != nil {
		return fmt.Errorf("locate broker executable: %w", err)
	}
	var restartRequested atomic.Bool
	if err := broker.RestartWhenExecutableChanges(executable, func() {
		restartRequested.Store(true)
		_ = server.Close()
	}); err != nil {
		return fmt.Errorf("watch broker executable: %w", err)
	}
	shutdown, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	go func() {
		<-shutdown.Done()
		_ = server.Close()
	}()
	err = server.Serve(listener)
	if errors.Is(err, http.ErrServerClosed) {
		if restartRequested.Load() {
			return errors.New("installed broker executable changed; requesting service restart")
		}
		return nil
	}
	return err
}

func prepareSocket(path string) error {
	if !filepath.IsAbs(path) || filepath.Clean(path) != path {
		return errors.New("socket path must be absolute and clean")
	}
	info, err := os.Lstat(path)
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	if err != nil {
		return err
	}
	if info.Mode()&os.ModeSocket == 0 || info.Mode()&os.ModeSymlink != 0 {
		return errors.New("refusing to replace a non-socket broker path")
	}
	return os.Remove(path)
}
