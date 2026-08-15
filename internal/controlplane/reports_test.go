package controlplane

import (
	"context"
	"encoding/base64"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/owainlewis/factory/internal/protocol"
)

type retryReportRenderer struct {
	mu    sync.Mutex
	calls int
}

func (renderer *retryReportRenderer) Render(_ context.Context, _ string, output string) error {
	renderer.mu.Lock()
	defer renderer.mu.Unlock()
	renderer.calls++
	if renderer.calls == 1 {
		return errors.New("temporary chromium failure")
	}
	return os.WriteFile(output, []byte("%PDF-1.7\ntest"), 0o600)
}

func (renderer *retryReportRenderer) count() int {
	renderer.mu.Lock()
	defer renderer.mu.Unlock()
	return renderer.calls
}

func TestDailyReportServiceAutomaticallyRetriesWithoutDuplicates(t *testing.T) {
	store := newTestStore(t)
	now := time.Date(2026, 8, 13, 9, 0, 0, 0, time.UTC)
	store.now = func() time.Time { return now }
	root := t.TempDir()
	renderer := &retryReportRenderer{}
	service := &DailyReportService{
		store: store, logger: slog.New(slog.NewTextHandler(io.Discard, nil)), renderer: renderer,
		root: root, location: time.UTC, checkEvery: 5 * time.Millisecond,
	}
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() { defer close(done); service.Run(ctx) }()
	deadline := time.Now().Add(time.Second)
	for {
		var status string
		_ = store.db.QueryRow(`SELECT status FROM daily_reports WHERE report_date='2026-08-12' AND timezone='UTC'`).Scan(&status)
		if status == "ready" {
			break
		}
		if time.Now().After(deadline) {
			t.Fatalf("automatic report did not become ready, renderer calls=%d", renderer.count())
		}
		time.Sleep(time.Millisecond)
	}
	cancel()
	<-done
	if renderer.count() != 2 {
		t.Fatalf("renderer calls=%d, want one failure and one retry", renderer.count())
	}
	service.runOnce(context.Background())
	if renderer.count() != 2 {
		t.Fatalf("ready report was duplicated, renderer calls=%d", renderer.count())
	}
	var count int
	if err := store.db.QueryRow(`SELECT COUNT(*) FROM daily_reports WHERE report_date='2026-08-12'`).Scan(&count); err != nil || count != 1 {
		t.Fatalf("durable report rows=%d, err=%v", count, err)
	}
	var published string
	if err := store.db.QueryRow(`SELECT pdf_path FROM daily_reports WHERE report_date='2026-08-12' AND timezone='UTC'`).Scan(&published); err != nil {
		t.Fatal(err)
	}
	content, err := os.ReadFile(filepath.Join(root, published))
	if err != nil || !strings.HasPrefix(string(content), "%PDF-") {
		t.Fatalf("published PDF=%q, err=%v", content, err)
	}
}

func TestCommandDailyReportRendererUsesReleaseBrowserRuntime(t *testing.T) {
	directory := t.TempDir()
	recordedEnvironment := filepath.Join(directory, "environment")
	node := filepath.Join(directory, "node")
	if err := os.WriteFile(node, []byte("#!/bin/sh\nprintf '%s\\n%s\\n' \"$FACTORY_BROWSER_LAUNCHER\" \"$FACTORY_BROWSER_PAYLOAD\" >\"$RENDER_ENVIRONMENT\"\n"), 0o700); err != nil {
		t.Fatal(err)
	}
	t.Setenv("PATH", directory+string(os.PathListSeparator)+os.Getenv("PATH"))
	t.Setenv("RENDER_ENVIRONMENT", recordedEnvironment)
	t.Setenv("FACTORY_BROWSER_LAUNCHER", "/untrusted/launcher")
	t.Setenv("FACTORY_BROWSER_PAYLOAD", "/untrusted/payload")

	if err := (commandDailyReportRenderer{script: "production-renderer.mjs"}).Render(context.Background(), "<html/>", filepath.Join(directory, "report.pdf")); err != nil {
		t.Fatal(err)
	}
	got, err := os.ReadFile(recordedEnvironment)
	if err != nil {
		t.Fatal(err)
	}
	want := factoryBrowserLauncher + "\n" + factoryBrowserPayload + "\n"
	if string(got) != want {
		t.Fatalf("renderer browser environment = %q, want %q", got, want)
	}
}

type sequentialPNGWriter struct{ calls int }

func (writer *sequentialPNGWriter) Capture(_ context.Context, _ protocol.VisualTarget, output string) error {
	writer.calls++
	return os.WriteFile(output, append([]byte("\x89PNG\r\n\x1a\n"), []byte(fmt.Sprintf("capture-%d", writer.calls))...), 0o600)
}

type documentReportRenderer struct{ calls int }

func (renderer *documentReportRenderer) Render(_ context.Context, document, output string) error {
	renderer.calls++
	return os.WriteFile(output, append([]byte("%PDF-1.7\n"), []byte(document)...), 0o600)
}

func TestDailyReportWaitsForStartupCapturesAndBuildsAfterRestart(t *testing.T) {
	store := newTestStore(t)
	now := time.Date(2026, 8, 13, 9, 0, 0, 0, time.UTC)
	store.now = func() time.Time { return now }
	worker := registerTestWorker(t, store, workerA, 1, protocol.RepositoryRegistration{Key: "factory", RemoteIdentity: "github.com/example/report-startup-race"})
	task := createTestTask(t, store, "report-startup-race", workerA, worker.Repositories[0].ID)
	if _, err := store.db.Exec(`INSERT INTO task_visual_targets(work_id,url,state_text,viewport_width,viewport_height,created_at) VALUES(?,?,?,?,?,?)`, task.Task.WorkID, "https://example.test/listings", "Готово", 1280, 720, now.AddDate(0, 0, -1).UnixMilli()); err != nil {
		t.Fatal(err)
	}
	for _, phase := range []string{"before", "after"} {
		if _, err := store.db.Exec(`INSERT INTO visual_captures(work_id,phase,status,updated_at) VALUES(?,?, 'pending',?)`, task.Task.WorkID, phase, now.Format(time.RFC3339Nano)); err != nil {
			t.Fatal(err)
		}
	}
	root := t.TempDir()
	logger := slog.New(slog.NewTextHandler(io.Discard, nil))
	firstRenderer := &documentReportRenderer{}
	firstService := &DailyReportService{store: store, logger: logger, renderer: firstRenderer, root: root, location: time.UTC, checkEvery: 5 * time.Millisecond}
	firstContext, stopFirst := context.WithCancel(context.Background())
	firstDone := make(chan struct{})
	go func() { defer close(firstDone); firstService.Run(firstContext) }()

	deadline := time.Now().Add(time.Second)
	for {
		var status, reason string
		_ = store.db.QueryRow(`SELECT status,error FROM daily_reports WHERE report_date='2026-08-12' AND timezone='UTC'`).Scan(&status, &reason)
		if status == "pending" && reason == "waiting for required captures" {
			break
		}
		if time.Now().After(deadline) {
			t.Fatalf("report did not wait for startup captures: status=%q reason=%q", status, reason)
		}
		time.Sleep(time.Millisecond)
	}
	stopFirst()
	<-firstDone
	if firstRenderer.calls != 0 {
		t.Fatalf("report rendered before captures were ready: calls=%d", firstRenderer.calls)
	}

	restartedRenderer := &documentReportRenderer{}
	restartedService := &DailyReportService{store: store, logger: logger, renderer: restartedRenderer, root: root, location: time.UTC, checkEvery: 5 * time.Millisecond}
	restartedContext, stopRestarted := context.WithCancel(context.Background())
	restartedDone := make(chan struct{})
	go func() { defer close(restartedDone); restartedService.Run(restartedContext) }()
	capturer := &sequentialPNGWriter{}
	captureService := &VisualCaptureService{store: store, logger: logger, capturer: capturer, root: root, captureTimeout: time.Second}
	captureService.runOnce(context.Background())

	var published string
	deadline = time.Now().Add(time.Second)
	for {
		var status string
		_ = store.db.QueryRow(`SELECT status,pdf_path FROM daily_reports WHERE report_date='2026-08-12' AND timezone='UTC'`).Scan(&status, &published)
		if status == "ready" {
			break
		}
		if time.Now().After(deadline) {
			t.Fatalf("report did not rebuild after captures appeared: status=%q capture calls=%d", status, capturer.calls)
		}
		time.Sleep(time.Millisecond)
	}
	stopRestarted()
	<-restartedDone
	content, err := os.ReadFile(filepath.Join(root, published))
	if err != nil {
		t.Fatal(err)
	}
	for _, capture := range []string{"capture-1", "capture-2"} {
		encoded := base64.StdEncoding.EncodeToString(append([]byte("\x89PNG\r\n\x1a\n"), []byte(capture)...))
		if !strings.Contains(string(content), encoded) {
			t.Fatalf("published PDF does not contain %s capture", capture)
		}
	}
	if restartedRenderer.calls != 1 {
		t.Fatalf("renderer calls after restart=%d, want 1", restartedRenderer.calls)
	}
}

func TestVisualTargetValidation(t *testing.T) {
	valid := protocol.VisualTarget{URL: "https://factory.timafen.com/listings", StateText: "Готово", ViewportWidth: 1280, ViewportHeight: 720}
	if err := validateVisualTarget(&valid); err != nil {
		t.Fatalf("valid target: %v", err)
	}
	for name, target := range map[string]protocol.VisualTarget{
		"insecure remote URL": {URL: "http://example.test", StateText: "ok", ViewportWidth: 800, ViewportHeight: 600},
		"missing marker":      {URL: "https://example.test", ViewportWidth: 800, ViewportHeight: 600},
		"small viewport":      {URL: "https://example.test", StateText: "ok", ViewportWidth: 319, ViewportHeight: 600},
		"malformed URL":       {URL: "http://[::1", StateText: "ok", ViewportWidth: 800, ViewportHeight: 600},
		"unlisted HTTPS host": {URL: "https://example.test", StateText: "ok", ViewportWidth: 800, ViewportHeight: 600},
	} {
		t.Run(name, func(t *testing.T) {
			if validateVisualTarget(&target) == nil {
				t.Fatal("invalid target accepted")
			}
		})
	}
}

func TestDailyVisualReportKeepsMissingBeforeHonest(t *testing.T) {
	report := protocol.DailyReport{ReportDate: "2026-08-12", Timezone: "America/Chicago", Metrics: map[string]any{
		"before": map[string]any{"period": "2026-08-11", "created": int64(2), "completed": int64(1), "succeeded": int64(1), "failed": int64(0)},
		"after":  map[string]any{"period": "2026-08-12", "created": int64(5), "completed": int64(4), "succeeded": int64(3), "failed": int64(1)},
	}}
	work := reportVisualWork{
		Title:  "Новая витрина",
		Target: protocol.VisualTarget{URL: "https://example.test/listings", StateText: "Готово", ViewportWidth: 1280, ViewportHeight: 720},
		Before: protocol.VisualCapture{Phase: "before", Status: "missing", Error: "страница потребовала вход"},
		After:  protocol.VisualCapture{Phase: "after", Status: "ready", CapturedAt: time.Date(2026, 8, 12, 18, 0, 0, 0, time.UTC)}, AfterImage: "data:image/png;base64,iVBORw0KGgo=",
	}
	document := buildDailyReportDocument(report, []reportVisualWork{work})
	if !strings.Contains(document, "Снимок до отсутствует") || !strings.Contains(document, "страница потребовала вход") {
		t.Fatalf("missing before must stay explicit in report: %s", document)
	}
	if strings.Contains(document, "Обзор") {
		t.Fatalf("report must not substitute Overview for a missing capture: %s", document)
	}
	for _, want := range []string{"До · 2026-08-11", "После · 2026-08-12", "created: 2", "created: 5", "data:image/png;base64,iVBORw0KGgo="} {
		if !strings.Contains(document, want) {
			t.Fatalf("report misses %q: %s", want, document)
		}
	}
}

type blockingReportRenderer struct {
	started chan struct{}
	release chan struct{}
	body    string
}

func (renderer *blockingReportRenderer) Render(ctx context.Context, _ string, output string) error {
	close(renderer.started)
	select {
	case <-renderer.release:
	case <-ctx.Done():
		return ctx.Err()
	}
	return os.WriteFile(output, []byte(renderer.body), 0o600)
}

type fixedReportRenderer string

func (renderer fixedReportRenderer) Render(_ context.Context, _ string, output string) error {
	return os.WriteFile(output, []byte(renderer), 0o600)
}

func TestDailyReportStaleRendererCannotOverwriteTakeover(t *testing.T) {
	store := newTestStore(t)
	now := time.Date(2026, 8, 13, 9, 0, 0, 0, time.UTC)
	store.now = func() time.Time { return now }
	root := t.TempDir()
	oldRenderer := &blockingReportRenderer{started: make(chan struct{}), release: make(chan struct{}), body: "%PDF-old"}
	oldService := &DailyReportService{store: store, logger: slog.Default(), renderer: oldRenderer, root: root, location: time.UTC, renderTimeout: time.Minute}
	done := make(chan error, 1)
	go func() { done <- oldService.createPreviousDay(context.Background()) }()
	<-oldRenderer.started
	now = now.Add(2 * time.Hour)
	newService := &DailyReportService{store: store, logger: slog.Default(), renderer: fixedReportRenderer("%PDF-new"), root: root, location: time.UTC, renderTimeout: time.Minute}
	if err := newService.createPreviousDay(context.Background()); err != nil {
		t.Fatal(err)
	}
	close(oldRenderer.release)
	if err := <-done; err == nil || !strings.Contains(err.Error(), "claim expired") {
		t.Fatalf("stale renderer error=%v", err)
	}
	var path, hash string
	if err := store.db.QueryRow(`SELECT pdf_path,pdf_sha256 FROM daily_reports WHERE report_date='2026-08-12' AND timezone='UTC'`).Scan(&path, &hash); err != nil {
		t.Fatal(err)
	}
	content, err := os.ReadFile(filepath.Join(root, path))
	if err != nil || string(content) != "%PDF-new" || hash == "" {
		t.Fatalf("published=%q hash=%q err=%v", content, hash, err)
	}
}

func TestDailyReportUsesConfiguredTimezoneAcrossDST(t *testing.T) {
	store := newTestStore(t)
	location, err := time.LoadLocation("America/Chicago")
	if err != nil {
		t.Fatal(err)
	}
	worker := registerTestWorker(t, store, workerA, 3, protocol.RepositoryRegistration{Key: "factory", RemoteIdentity: "github.com/example/report-timezone"})
	start := time.Date(2026, 11, 1, 0, 0, 0, 0, location)
	end := start.AddDate(0, 0, 1)
	if end.Sub(start) != 25*time.Hour {
		t.Fatalf("DST report day=%s", end.Sub(start))
	}
	for index, instant := range []time.Time{start.Add(-time.Millisecond), start.Add(time.Millisecond), end.Add(-time.Millisecond)} {
		task := createTestTask(t, store, fmt.Sprintf("timezone-%d", index), workerA, worker.Repositories[0].ID)
		if _, err := store.db.Exec(`INSERT INTO task_visual_targets(work_id,url,state_text,viewport_width,viewport_height,created_at) VALUES(?,?,?,?,?,?)`, task.Task.WorkID, "https://example.test", "Готово", 800, 600, instant.UnixMilli()); err != nil {
			t.Fatal(err)
		}
	}
	report, works, err := store.dailyReportData(context.Background(), "2026-11-01", location)
	if err != nil {
		t.Fatal(err)
	}
	if report.Timezone != "America/Chicago" || len(works) != 2 {
		t.Fatalf("timezone=%q works=%d", report.Timezone, len(works))
	}
	before := report.Metrics["before"].(map[string]any)
	after := report.Metrics["after"].(map[string]any)
	if before["period"] != "2026-10-31" || after["period"] != "2026-11-01" {
		t.Fatalf("metric periods before=%v after=%v", before["period"], after["period"])
	}
}
