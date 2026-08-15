//go:build darwin || dragonfly || freebsd || linux || netbsd || openbsd || solaris

package worker

import (
	"os"
	"os/signal"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"testing"
	"time"
)

const interruptedTestControlledEnv = "FACTORY_WORKER_INTERRUPTION_CONTROLLED"

var interruptedTestLifecycle = struct {
	sync.Mutex
	syncDirs []string
	signal   chan os.Signal
}{signal: make(chan os.Signal, 1)}

// runInterruptedTestLifecycle wraps every worker-test run. Signal notification is
// installed before main.Run can publish a readiness marker from a blocking fake gh.
func runInterruptedTestLifecycle(main *testing.M) int {
	signals := make(chan os.Signal, 1)
	signal.Notify(signals, syscall.SIGTERM, syscall.SIGINT, syscall.SIGHUP)
	defer signal.Stop(signals)
	go func() {
		sig := <-signals
		cleanupInterruptedTestGroups()
		root := os.Getenv("FACTORY_WORKER_INTERRUPTION_ROOT")
		if root != "" {
			_ = os.RemoveAll(root)
		}
		if os.Getenv(interruptedTestControlledEnv) == "1" {
			interruptedTestLifecycle.signal <- sig
			return
		}
		os.Exit(128 + int(sig.(syscall.Signal)))
	}()
	code := main.Run()
	_ = os.RemoveAll(os.Getenv("FACTORY_WORKER_INTERRUPTION_ROOT"))
	return code
}

func registerInterruptibleSyncDir(path string) {
	interruptedTestLifecycle.Lock()
	defer interruptedTestLifecycle.Unlock()
	interruptedTestLifecycle.syncDirs = append(interruptedTestLifecycle.syncDirs, path)
}

func cleanupInterruptedTestGroups() {
	interruptedTestLifecycle.Lock()
	dirs := append([]string(nil), interruptedTestLifecycle.syncDirs...)
	interruptedTestLifecycle.Unlock()
	for _, dir := range dirs {
		matches, _ := filepath.Glob(filepath.Join(dir, "*.pid"))
		for _, path := range matches {
			data, err := os.ReadFile(path)
			if err != nil {
				continue
			}
			pgid, err := strconv.Atoi(strings.TrimSpace(string(data)))
			if err != nil {
				continue
			}
			_ = signalProcessGroup(pgid, syscall.SIGTERM)
			deadline := time.Now().Add(time.Second)
			for processGroupAlive(pgid) && time.Now().Before(deadline) {
				time.Sleep(20 * time.Millisecond)
			}
			if processGroupAlive(pgid) {
				_ = forceStopStartedProcessGroup(pgid)
			}
		}
	}
}
