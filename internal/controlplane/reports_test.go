package controlplane

import (
	"strings"
	"testing"
	"time"

	"github.com/owainlewis/factory/internal/protocol"
)

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
