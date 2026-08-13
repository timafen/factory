package controlplane

import (
	"context"
	"encoding/json"
	"fmt"
	"html"
	"net/url"
	"strings"

	"github.com/owainlewis/factory/internal/protocol"
)

type reportVisualWork struct {
	Title  string
	Target protocol.VisualTarget
	Before protocol.VisualCapture
	After  protocol.VisualCapture
}

// buildDailyReportDocument deliberately renders missing captures as facts. It
// never guesses a replacement page or image.
func buildDailyReportDocument(report protocol.DailyReport, works []reportVisualWork) string {
	var body strings.Builder
	fmt.Fprintf(&body, "<!doctype html><meta charset=utf-8><title>Ежедневный отчёт</title><style>body{font:16px system-ui;color:#18202a}section{border:1px solid #ccd5df;border-radius:12px;padding:18px;margin:14px 0}.missing{background:#fff4e5;padding:12px}svg{max-width:100%%}</style><h1>Ежедневный отчёт за %s</h1><p>Часовой пояс: %s</p>", html.EscapeString(report.ReportDate), html.EscapeString(report.Timezone))
	metrics, _ := json.Marshal(report.Metrics)
	fmt.Fprintf(&body, "<h2>Метрики конвейера: предыдущий день → отчётный день</h2><svg viewBox='0 0 600 50' role='img' aria-label='Инфографика метрик'><rect width='600' height='50' fill='#e8f0fe'/><text x='15' y='31'>%s</text></svg>", html.EscapeString(string(metrics)))
	for _, work := range works {
		fmt.Fprintf(&body, "<section><h2>%s</h2><p>%s · %s · %d×%d</p>", html.EscapeString(work.Title), html.EscapeString(work.Target.URL), html.EscapeString(work.Target.StateText), work.Target.ViewportWidth, work.Target.ViewportHeight)
		for _, capture := range []protocol.VisualCapture{work.Before, work.After} {
			label := map[string]string{"before": "до", "after": "после"}[capture.Phase]
			if capture.Status != "ready" {
				fmt.Fprintf(&body, "<div class=missing>Снимок %s отсутствует: %s</div>", label, html.EscapeString(capture.Error))
			} else {
				fmt.Fprintf(&body, "<p>Снимок %s сохранён</p>", label)
			}
		}
		body.WriteString("</section>")
	}
	return body.String()
}

func validateVisualTarget(target *protocol.VisualTarget) error {
	if target == nil {
		return nil
	}
	parsed, err := url.Parse(strings.TrimSpace(target.URL))
	loopback := parsed.Hostname() == "localhost" || parsed.Hostname() == "127.0.0.1" || parsed.Hostname() == "::1"
	if err != nil || parsed.Host == "" || (parsed.Scheme != "https" && !(parsed.Scheme == "http" && loopback)) {
		return invalid("invalid_visual_target", "visual target URL must be absolute HTTPS (HTTP is allowed for loopback)")
	}
	if strings.TrimSpace(target.StateText) == "" {
		return invalid("invalid_visual_target", "visual target state_text is required")
	}
	if target.ViewportWidth < 320 || target.ViewportWidth > 2560 || target.ViewportHeight < 320 || target.ViewportHeight > 2560 {
		return invalid("invalid_visual_target", "visual target viewport must be between 320 and 2560 pixels")
	}
	return nil
}

func (s *Store) ListDailyReports(ctx context.Context) ([]protocol.DailyReport, error) {
	rows, err := s.db.QueryContext(ctx, `SELECT report_date,timezone,status,metrics_json,pdf_sha256,pdf_size,error FROM daily_reports ORDER BY report_date DESC`)
	if err != nil {
		return nil, unavailable(err)
	}
	defer rows.Close()
	var out []protocol.DailyReport
	for rows.Next() {
		var r protocol.DailyReport
		var raw string
		if err := rows.Scan(&r.ReportDate, &r.Timezone, &r.Status, &raw, &r.PDFSHA256, &r.PDFSize, &r.Error); err != nil {
			return nil, unavailable(err)
		}
		_ = json.Unmarshal([]byte(raw), &r.Metrics)
		out = append(out, r)
	}
	return out, rows.Err()
}
