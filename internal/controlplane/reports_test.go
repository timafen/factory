package controlplane

import (
	"context"
	"errors"
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
	content, err := os.ReadFile(filepath.Join(root, "daily-report-2026-08-12.pdf"))
	if err != nil || !strings.HasPrefix(string(content), "%PDF-") {
		t.Fatalf("published PDF=%q, err=%v", content, err)
	}
}

func TestVisualTargetValidation(t *testing.T) {
	valid := protocol.VisualTarget{URL: "https://example.test/listings", StateText: "Готово", ViewportWidth: 1280, ViewportHeight: 720}
	if err := validateVisualTarget(&valid); err != nil {
		t.Fatalf("valid target: %v", err)
	}
	for name, target := range map[string]protocol.VisualTarget{
		"insecure remote URL": {URL: "http://example.test", StateText: "ok", ViewportWidth: 800, ViewportHeight: 600},
		"missing marker":      {URL: "https://example.test", ViewportWidth: 800, ViewportHeight: 600},
		"small viewport":      {URL: "https://example.test", StateText: "ok", ViewportWidth: 319, ViewportHeight: 600},
	} {
		t.Run(name, func(t *testing.T) {
			if validateVisualTarget(&target) == nil {
				t.Fatal("invalid target accepted")
			}
		})
	}
}

func TestDailyVisualReportKeepsMissingBeforeHonest(t *testing.T) {
	report := protocol.DailyReport{ReportDate: "2026-08-12", Timezone: "America/Chicago"}
	work := reportVisualWork{
		Title:  "Новая витрина",
		Target: protocol.VisualTarget{URL: "https://example.test/listings", StateText: "Готово", ViewportWidth: 1280, ViewportHeight: 720},
		Before: protocol.VisualCapture{Phase: "before", Status: "missing", Error: "страница потребовала вход"},
		After:  protocol.VisualCapture{Phase: "after", Status: "ready", CapturedAt: time.Date(2026, 8, 12, 18, 0, 0, 0, time.UTC)},
	}
	document := buildDailyReportDocument(report, []reportVisualWork{work})
	if !strings.Contains(document, "Снимок до отсутствует") || !strings.Contains(document, "страница потребовала вход") {
		t.Fatalf("missing before must stay explicit in report: %s", document)
	}
	if strings.Contains(document, "Обзор") {
		t.Fatalf("report must not substitute Overview for a missing capture: %s", document)
	}
}
