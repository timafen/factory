package controlplane

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/json"
	"fmt"
	"html"
	"log/slog"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/owainlewis/factory/internal/protocol"
)

type dailyReportRenderer interface {
	Render(context.Context, string, string) error
}

type commandDailyReportRenderer struct{ script string }

func (r commandDailyReportRenderer) Render(ctx context.Context, document, output string) error {
	command := exec.CommandContext(ctx, "node", r.script, output)
	command.Stdin = strings.NewReader(document)
	if output, err := command.CombinedOutput(); err != nil {
		return fmt.Errorf("render PDF: %w: %s", err, strings.TrimSpace(string(output)))
	}
	return nil
}

// DailyReportService uses the same durable background-service pattern as the
// automation runtime. The database row is both the job ledger and the lock:
// its primary key prevents duplicate daily PDFs across concurrent servers.
type DailyReportService struct {
	store      *Store
	logger     *slog.Logger
	renderer   dailyReportRenderer
	root       string
	location   *time.Location
	checkEvery time.Duration
}

func NewDailyReportService(store *Store, logger *slog.Logger, root, rendererScript, timezone string) (*DailyReportService, error) {
	location, err := time.LoadLocation(timezone)
	if err != nil {
		return nil, fmt.Errorf("load report timezone: %w", err)
	}
	return &DailyReportService{store: store, logger: logger, renderer: commandDailyReportRenderer{script: rendererScript}, root: root, location: location, checkEvery: time.Minute}, nil
}

func (service *DailyReportService) Run(ctx context.Context) {
	service.runOnce(ctx)
	ticker := time.NewTicker(service.checkEvery)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			service.runOnce(ctx)
		}
	}
}

func (service *DailyReportService) runOnce(ctx context.Context) {
	if err := service.createPreviousDay(ctx); err != nil && ctx.Err() == nil {
		service.logger.Error("daily_report_failed", "error", err)
	}
}

func (service *DailyReportService) createPreviousDay(ctx context.Context) error {
	now := service.store.now().In(service.location)
	date := now.AddDate(0, 0, -1).Format(time.DateOnly)
	claimed, err := service.store.claimDailyReport(ctx, date, service.location.String())
	if err != nil || !claimed {
		return err
	}
	report, works, err := service.store.dailyReportData(ctx, date, service.location)
	if err != nil {
		service.store.failDailyReport(ctx, date, service.location.String(), err)
		return err
	}
	filename := "daily-report-" + date + ".pdf"
	temporary := filepath.Join(service.root, "."+filename+".tmp")
	_ = os.Remove(temporary)
	if err := service.renderer.Render(ctx, buildDailyReportDocument(report, works), temporary); err != nil {
		service.store.failDailyReport(ctx, date, service.location.String(), err)
		return err
	}
	content, err := os.ReadFile(temporary)
	if err != nil || len(content) < 5 || string(content[:5]) != "%PDF-" {
		if err == nil {
			err = fmt.Errorf("renderer output is not a PDF")
		}
		_ = os.Remove(temporary)
		service.store.failDailyReport(ctx, date, service.location.String(), err)
		return err
	}
	final := filepath.Join(service.root, filename)
	if err := os.Rename(temporary, final); err != nil {
		service.store.failDailyReport(ctx, date, service.location.String(), err)
		return err
	}
	hash := fmt.Sprintf("%x", sha256.Sum256(content))
	_, err = service.store.db.ExecContext(ctx, `UPDATE daily_reports SET status='ready',pdf_path=?,pdf_sha256=?,pdf_size=?,error='',updated_at=? WHERE report_date=? AND timezone=? AND status='running'`, filename, hash, len(content), service.store.now().UTC().Format(time.RFC3339Nano), date, service.location.String())
	return err
}

func (s *Store) claimDailyReport(ctx context.Context, date, timezone string) (bool, error) {
	instant := s.now().UTC()
	now := instant.Format(time.RFC3339Nano)
	_, err := s.db.ExecContext(ctx, `INSERT INTO daily_reports(report_date,timezone,status,created_at,updated_at) VALUES(?,?,'pending',?,?) ON CONFLICT(report_date,timezone) DO NOTHING`, date, timezone, now, now)
	if err != nil {
		return false, unavailable(err)
	}
	result, err := s.db.ExecContext(ctx, `UPDATE daily_reports SET status='running',error='',updated_at=? WHERE report_date=? AND timezone=? AND (status IN ('pending','error') OR (status='running' AND updated_at<?))`, now, date, timezone, instant.Add(-time.Hour).Format(time.RFC3339Nano))
	if err != nil {
		return false, unavailable(err)
	}
	changed, err := result.RowsAffected()
	return changed == 1, err
}

func (s *Store) failDailyReport(ctx context.Context, date, timezone string, cause error) {
	_, _ = s.db.ExecContext(ctx, `UPDATE daily_reports SET status='error',error=?,updated_at=? WHERE report_date=? AND timezone=? AND status='running'`, cause.Error(), s.now().UTC().Format(time.RFC3339Nano), date, timezone)
}

func (s *Store) dailyReportData(ctx context.Context, date string, location *time.Location) (protocol.DailyReport, []reportVisualWork, error) {
	start, err := time.ParseInLocation(time.DateOnly, date, location)
	if err != nil {
		return protocol.DailyReport{}, nil, err
	}
	metrics, err := s.Metrics(ctx, metricsWindow24Hours)
	if err != nil {
		return protocol.DailyReport{}, nil, err
	}
	rawMetrics, _ := json.Marshal(metrics)
	var metricMap map[string]any
	_ = json.Unmarshal(rawMetrics, &metricMap)
	report := protocol.DailyReport{ReportDate: date, Timezone: location.String(), Status: "running", Metrics: metricMap}
	rows, err := s.db.QueryContext(ctx, `
		SELECT target.work_id, task.title, target.url, target.state_text, target.viewport_width, target.viewport_height,
		       before.status, before.path, before.sha256, before.captured_at, before.error,
		       after.status, after.path, after.sha256, after.captured_at, after.error
		FROM task_visual_targets target
		JOIN tasks task ON task.id=(SELECT candidate.id FROM tasks candidate WHERE candidate.work_id=target.work_id ORDER BY candidate.created_at,candidate.id LIMIT 1)
		LEFT JOIN visual_captures before ON before.work_id=target.work_id AND before.phase='before'
		LEFT JOIN visual_captures after ON after.work_id=target.work_id AND after.phase='after'
		WHERE CAST(target.created_at AS INTEGER)>=? AND CAST(target.created_at AS INTEGER)<?
		ORDER BY CAST(target.created_at AS INTEGER), target.work_id`, start.UTC().UnixMilli(), start.AddDate(0, 0, 1).UTC().UnixMilli())
	if err != nil {
		return report, nil, unavailable(err)
	}
	defer rows.Close()
	var works []reportVisualWork
	for rows.Next() {
		var work reportVisualWork
		var workID string
		var beforeStatus, beforePath, beforeHash, beforeTime, beforeError sql.NullString
		var afterStatus, afterPath, afterHash, afterTime, afterError sql.NullString
		if err := rows.Scan(&workID, &work.Title, &work.Target.URL, &work.Target.StateText, &work.Target.ViewportWidth, &work.Target.ViewportHeight,
			&beforeStatus, &beforePath, &beforeHash, &beforeTime, &beforeError, &afterStatus, &afterPath, &afterHash, &afterTime, &afterError); err != nil {
			return report, nil, unavailable(err)
		}
		work.Target.WorkID, work.Before.WorkID, work.Before.Phase = workID, workID, "before"
		work.Before.Status = beforeStatus.String
		work.Before.Path, work.Before.SHA256, work.Before.Error = beforePath.String, beforeHash.String, beforeError.String
		work.After = protocol.VisualCapture{WorkID: workID, Phase: "after", Status: afterStatus.String, Path: afterPath.String, SHA256: afterHash.String, Error: afterError.String}
		if work.Before.Status == "" {
			work.Before.Status, work.Before.Error = "missing", "снимок не был создан"
		}
		if work.After.Status == "" {
			work.After.Status, work.After.Error = "missing", "снимок не был создан"
		}
		if beforeTime.Valid {
			work.Before.CapturedAt, _ = time.Parse(time.RFC3339Nano, beforeTime.String)
		}
		if afterTime.Valid {
			work.After.CapturedAt, _ = time.Parse(time.RFC3339Nano, afterTime.String)
		}
		works = append(works, work)
	}
	return report, works, rows.Err()
}

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
