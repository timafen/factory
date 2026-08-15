package controlplane

import (
	"context"
	"crypto/sha256"
	"crypto/subtle"
	"database/sql"
	"encoding/base64"
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

const (
	factoryBrowserLauncher = "/usr/local/libexec/factory/factory-browser-sandbox"
	factoryBrowserPayload  = "/opt/factory-data/releases/factory/browser-runtime/current"
)

func (r commandDailyReportRenderer) Render(ctx context.Context, document, output string) error {
	command := exec.CommandContext(ctx, "node", r.script, output)
	command.Stdin = strings.NewReader(document)
	// The report scripts are materialized in the data directory, while their
	// Playwright payload belongs to the release.  Make both production paths
	// explicit so a server service never relies on a removed checkout or its
	// inherited environment.
	command.Env = browserRendererEnvironment()
	if output, err := command.CombinedOutput(); err != nil {
		return fmt.Errorf("render PDF: %w: %s", err, strings.TrimSpace(string(output)))
	}
	return nil
}

func browserRendererEnvironment() []string {
	environment := make([]string, 0, len(os.Environ())+2)
	for _, item := range os.Environ() {
		if strings.HasPrefix(item, "FACTORY_BROWSER_LAUNCHER=") || strings.HasPrefix(item, "FACTORY_BROWSER_PAYLOAD=") {
			continue
		}
		environment = append(environment, item)
	}
	return append(environment,
		"FACTORY_BROWSER_LAUNCHER="+factoryBrowserLauncher,
		"FACTORY_BROWSER_PAYLOAD="+factoryBrowserPayload,
	)
}

// DailyReportService uses the same durable background-service pattern as the
// automation runtime. The database row is both the job ledger and the lock:
// its primary key prevents duplicate daily PDFs across concurrent servers.
type DailyReportService struct {
	store         *Store
	logger        *slog.Logger
	renderer      dailyReportRenderer
	root          string
	location      *time.Location
	checkEvery    time.Duration
	renderTimeout time.Duration
}

func NewDailyReportService(store *Store, logger *slog.Logger, root, rendererScript, timezone string) (*DailyReportService, error) {
	location, err := time.LoadLocation(timezone)
	if err != nil {
		return nil, fmt.Errorf("load report timezone: %w", err)
	}
	store.reportRoot = root
	return &DailyReportService{store: store, logger: logger, renderer: commandDailyReportRenderer{script: rendererScript}, root: root, location: location, checkEvery: time.Minute, renderTimeout: 10 * time.Minute}, nil
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
	token, err := service.store.claimDailyReport(ctx, date, service.location.String())
	if err != nil || token == "" {
		return err
	}
	report, works, err := service.store.dailyReportData(ctx, date, service.location)
	if err != nil {
		service.store.failDailyReport(ctx, date, service.location.String(), token, err)
		return err
	}
	if !service.loadCaptureImages(works) {
		return service.store.deferDailyReport(ctx, date, service.location.String(), token)
	}
	metricsJSON, err := json.Marshal(report.Metrics)
	if err != nil {
		service.store.failDailyReport(ctx, date, service.location.String(), token, err)
		return err
	}
	zoneDigest := fmt.Sprintf("%x", sha256.Sum256([]byte(service.location.String())))[:12]
	filename := fmt.Sprintf("daily-report-%s-%s-%s.pdf", date, zoneDigest, token)
	temporary := filepath.Join(service.root, "."+filename+".tmp")
	renderTimeout := service.renderTimeout
	if renderTimeout == 0 {
		renderTimeout = 10 * time.Minute
	}
	renderContext, cancel := context.WithTimeout(ctx, renderTimeout)
	defer cancel()
	if err := service.renderer.Render(renderContext, buildDailyReportDocument(report, works), temporary); err != nil {
		_ = os.Remove(temporary)
		service.store.failDailyReport(ctx, date, service.location.String(), token, err)
		return err
	}
	content, err := os.ReadFile(temporary)
	if err != nil || len(content) < 5 || string(content[:5]) != "%PDF-" {
		if err == nil {
			err = fmt.Errorf("renderer output is not a PDF")
		}
		_ = os.Remove(temporary)
		service.store.failDailyReport(ctx, date, service.location.String(), token, err)
		return err
	}
	final := filepath.Join(service.root, filename)
	if err := os.Rename(temporary, final); err != nil {
		service.store.failDailyReport(ctx, date, service.location.String(), token, err)
		return err
	}
	hash := fmt.Sprintf("%x", sha256.Sum256(content))
	result, err := service.store.db.ExecContext(ctx, `UPDATE daily_reports SET status='ready',metrics_json=?,pdf_path=?,pdf_sha256=?,pdf_size=?,error='',updated_at=? WHERE report_date=? AND timezone=? AND status='running' AND claim_token=?`, string(metricsJSON), filename, hash, len(content), service.store.now().UTC().Format(time.RFC3339Nano), date, service.location.String(), token)
	if err != nil {
		// ExecContext can return a cancellation error after SQLite has already
		// committed the row.  Keep the atomically published file on an
		// ambiguous outcome so a durable ready row can never point at a file we
		// removed during shutdown.  An unreferenced file is safe and can be
		// cleaned later; a referenced missing report is not.
		return err
	}
	changed, err := result.RowsAffected()
	if err != nil {
		return err
	}
	if changed != 1 {
		_ = os.Remove(final)
		return fmt.Errorf("daily report claim expired")
	}
	return nil
}

func (s *Store) claimDailyReport(ctx context.Context, date, timezone string) (string, error) {
	instant := s.now().UTC()
	now := instant.Format(time.RFC3339Nano)
	token, err := newID()
	if err != nil {
		return "", err
	}
	_, err = s.db.ExecContext(ctx, `INSERT INTO daily_reports(report_date,timezone,status,created_at,updated_at) VALUES(?,?,'pending',?,?) ON CONFLICT(report_date,timezone) DO NOTHING`, date, timezone, now, now)
	if err != nil {
		return "", unavailable(err)
	}
	result, err := s.db.ExecContext(ctx, `UPDATE daily_reports SET status='running',claim_token=?,error='',updated_at=? WHERE report_date=? AND timezone=? AND (status IN ('pending','error') OR (status='running' AND updated_at<?))`, token, now, date, timezone, instant.Add(-time.Hour).Format(time.RFC3339Nano))
	if err != nil {
		return "", unavailable(err)
	}
	changed, err := result.RowsAffected()
	if err != nil || changed != 1 {
		return "", err
	}
	return token, nil
}

func (s *Store) failDailyReport(ctx context.Context, date, timezone, token string, cause error) {
	_, _ = s.db.ExecContext(ctx, `UPDATE daily_reports SET status='error',error=?,updated_at=? WHERE report_date=? AND timezone=? AND status='running' AND claim_token=?`, cause.Error(), s.now().UTC().Format(time.RFC3339Nano), date, timezone, token)
}

func (s *Store) deferDailyReport(ctx context.Context, date, timezone, token string) error {
	result, err := s.db.ExecContext(ctx, `UPDATE daily_reports SET status='pending',claim_token='',error='waiting for required captures',updated_at=? WHERE report_date=? AND timezone=? AND status='running' AND claim_token=?`, s.now().UTC().Format(time.RFC3339Nano), date, timezone, token)
	if err != nil {
		return unavailable(err)
	}
	changed, err := result.RowsAffected()
	if err != nil {
		return unavailable(err)
	}
	if changed != 1 {
		return fmt.Errorf("daily report claim expired")
	}
	return nil
}

func (s *Store) dailyReportData(ctx context.Context, date string, location *time.Location) (protocol.DailyReport, []reportVisualWork, error) {
	start, err := time.ParseInLocation(time.DateOnly, date, location)
	if err != nil {
		return protocol.DailyReport{}, nil, err
	}
	beforeMetrics, err := s.dailyReportMetrics(ctx, start.AddDate(0, 0, -1), start)
	if err != nil {
		return protocol.DailyReport{}, nil, err
	}
	afterMetrics, err := s.dailyReportMetrics(ctx, start, start.AddDate(0, 0, 1))
	if err != nil {
		return protocol.DailyReport{}, nil, err
	}
	metricMap := map[string]any{"before": beforeMetrics, "after": afterMetrics}
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
	Title       string
	Target      protocol.VisualTarget
	Before      protocol.VisualCapture
	After       protocol.VisualCapture
	BeforeImage string
	AfterImage  string
}

func (s *Store) dailyReportMetrics(ctx context.Context, start, end time.Time) (map[string]any, error) {
	metric := map[string]any{"period": start.Format(time.DateOnly)}
	for name, query := range map[string]string{
		"created":   `SELECT COUNT(*) FROM executions WHERE created_at>=? AND created_at<?`,
		"completed": `SELECT COUNT(*) FROM executions WHERE state IN ('succeeded','failed','cancelled') AND updated_at>=? AND updated_at<?`,
		"succeeded": `SELECT COUNT(*) FROM executions WHERE state='succeeded' AND updated_at>=? AND updated_at<?`,
		"failed":    `SELECT COUNT(*) FROM executions WHERE state='failed' AND updated_at>=? AND updated_at<?`,
	} {
		var value int64
		if err := s.db.QueryRowContext(ctx, query, start.UTC().UnixMilli(), end.UTC().UnixMilli()).Scan(&value); err != nil {
			return nil, unavailable(err)
		}
		metric[name] = value
	}
	return metric, nil
}

func (service *DailyReportService) loadCaptureImages(works []reportVisualWork) bool {
	ready := true
	for index := range works {
		works[index].BeforeImage = service.captureDataURL(works[index].Before)
		works[index].AfterImage = service.captureDataURL(works[index].After)
		if works[index].BeforeImage == "" || works[index].AfterImage == "" {
			ready = false
		}
	}
	return ready
}

func (service *DailyReportService) captureDataURL(capture protocol.VisualCapture) string {
	if capture.Status != "ready" || capture.Path == "" || capture.SHA256 == "" {
		return ""
	}
	path := filepath.Join(service.root, filepath.Clean(capture.Path))
	relative, err := filepath.Rel(service.root, path)
	if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) {
		return ""
	}
	content, err := os.ReadFile(path)
	if err != nil {
		return ""
	}
	actual := fmt.Sprintf("%x", sha256.Sum256(content))
	if subtle.ConstantTimeCompare([]byte(actual), []byte(capture.SHA256)) != 1 {
		return ""
	}
	return "data:image/png;base64," + base64.StdEncoding.EncodeToString(content)
}

// buildDailyReportDocument deliberately renders missing captures as facts. It
// never guesses a replacement page or image.
func buildDailyReportDocument(report protocol.DailyReport, works []reportVisualWork) string {
	var body strings.Builder
	fmt.Fprintf(&body, "<!doctype html><meta charset=utf-8><title>Ежедневный отчёт</title><style>body{font:16px system-ui;color:#18202a}section{border:1px solid #ccd5df;border-radius:12px;padding:18px;margin:14px 0}.missing{background:#fff4e5;padding:12px}svg{max-width:100%%}</style><h1>Ежедневный отчёт за %s</h1><p>Часовой пояс: %s</p>", html.EscapeString(report.ReportDate), html.EscapeString(report.Timezone))
	before, _ := report.Metrics["before"].(map[string]any)
	after, _ := report.Metrics["after"].(map[string]any)
	fmt.Fprintf(&body, "<h2>Метрики конвейера: до → после</h2><svg viewBox='0 0 680 150' role='img' aria-label='Сравнение метрик до и после'><rect width='330' height='150' rx='12' fill='#eef3f8'/><rect x='350' width='330' height='150' rx='12' fill='#e6f4ea'/><text x='20' y='30' font-weight='bold'>До · %s</text><text x='370' y='30' font-weight='bold'>После · %s</text>", html.EscapeString(fmt.Sprint(before["period"])), html.EscapeString(fmt.Sprint(after["period"])))
	for index, metric := range []string{"created", "completed", "succeeded", "failed"} {
		y := 58 + index*24
		fmt.Fprintf(&body, "<text x='20' y='%d'>%s: %v</text><text x='370' y='%d'>%s: %v</text>", y, metric, before[metric], y, metric, after[metric])
	}
	body.WriteString("</svg>")
	for _, work := range works {
		fmt.Fprintf(&body, "<section><h2>%s</h2><p>%s · %s · %d×%d</p>", html.EscapeString(work.Title), html.EscapeString(work.Target.URL), html.EscapeString(work.Target.StateText), work.Target.ViewportWidth, work.Target.ViewportHeight)
		for index, capture := range []protocol.VisualCapture{work.Before, work.After} {
			label := map[string]string{"before": "до", "after": "после"}[capture.Phase]
			image := []string{work.BeforeImage, work.AfterImage}[index]
			if capture.Status != "ready" || image == "" {
				reason := capture.Error
				if reason == "" {
					reason = "файл снимка недоступен или не прошёл проверку целостности"
				}
				fmt.Fprintf(&body, "<div class=missing>Снимок %s отсутствует: %s</div>", label, html.EscapeString(reason))
			} else {
				fmt.Fprintf(&body, "<figure><figcaption>Снимок %s</figcaption><img alt='Снимок %s' src='%s' style='max-width:100%%;height:auto'></figure>", label, label, image)
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
	if err != nil || parsed == nil || parsed.Host == "" {
		return invalid("invalid_visual_target", "visual target URL must be absolute HTTPS (HTTP is allowed for loopback)")
	}
	host := strings.ToLower(parsed.Hostname())
	loopback := host == "localhost" || host == "127.0.0.1" || host == "::1"
	allowedHost := loopback || host == "factory.timafen.com" || host == "staging-automation.tarser.net"
	if !allowedHost || (parsed.Scheme != "https" && !(parsed.Scheme == "http" && loopback)) {
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
