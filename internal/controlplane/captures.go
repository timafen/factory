package controlplane

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/owainlewis/factory/internal/protocol"
)

type visualCapturer interface {
	Capture(context.Context, protocol.VisualTarget, string) error
}

type commandVisualCapturer struct{ script string }

type claimedVisualCapture struct {
	WorkID string
	Phase  string
	Target protocol.VisualTarget
}

func (capturer commandVisualCapturer) Capture(ctx context.Context, target protocol.VisualTarget, output string) error {
	input, err := json.Marshal(target)
	if err != nil {
		return err
	}
	command := exec.CommandContext(ctx, "node", capturer.script, string(input), output)
	if body, err := command.CombinedOutput(); err != nil {
		return fmt.Errorf("capture page: %w: %s", err, strings.TrimSpace(string(body)))
	}
	return nil
}

type VisualCaptureService struct {
	store          *Store
	logger         *slog.Logger
	capturer       visualCapturer
	root           string
	checkEvery     time.Duration
	captureTimeout time.Duration
}

func NewVisualCaptureService(store *Store, logger *slog.Logger, root, script string) *VisualCaptureService {
	store.reportRoot = root
	return &VisualCaptureService{store: store, logger: logger, capturer: commandVisualCapturer{script: script}, root: root, checkEvery: time.Minute, captureTimeout: 2 * time.Minute}
}

func (service *VisualCaptureService) Run(ctx context.Context) {
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

func (service *VisualCaptureService) runOnce(ctx context.Context) {
	for {
		capture, token, ok, err := service.store.claimVisualCapture(ctx)
		if err != nil {
			service.logger.Error("visual_capture_claim_failed", "error", err)
			return
		}
		if !ok {
			return
		}
		if err := service.capture(ctx, capture, token); err != nil && ctx.Err() == nil {
			service.logger.Warn("visual_capture_failed", "phase", capture.Phase, "error", err)
		}
	}
}

func (service *VisualCaptureService) capture(ctx context.Context, capture claimedVisualCapture, token string) error {
	directory := filepath.Join(service.root, "captures")
	if err := os.MkdirAll(directory, 0o700); err != nil {
		return err
	}
	filename := fmt.Sprintf("%s-%s-%s.png", capture.WorkID, capture.Phase, token)
	path := filepath.Join(directory, filename)
	timeout := service.captureTimeout
	if timeout == 0 {
		timeout = 2 * time.Minute
	}
	captureContext, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	if err := service.capturer.Capture(captureContext, capture.Target, path); err != nil {
		service.store.failVisualCapture(ctx, capture.WorkID, capture.Phase, token, err)
		_ = os.Remove(path)
		return err
	}
	content, err := os.ReadFile(path)
	if err != nil || len(content) < 8 || string(content[:8]) != "\x89PNG\r\n\x1a\n" {
		if err == nil {
			err = fmt.Errorf("capture output is not a PNG")
		}
		service.store.failVisualCapture(ctx, capture.WorkID, capture.Phase, token, err)
		_ = os.Remove(path)
		return err
	}
	hash := fmt.Sprintf("%x", sha256.Sum256(content))
	result, err := service.store.db.ExecContext(ctx, `UPDATE visual_captures SET status='ready',path=?,sha256=?,captured_at=?,error='',updated_at=? WHERE work_id=? AND phase=? AND status='running' AND claim_token=?`, filepath.Join("captures", filename), hash, service.store.now().UTC().Format(time.RFC3339Nano), service.store.now().UTC().Format(time.RFC3339Nano), capture.WorkID, capture.Phase, token)
	if err != nil {
		_ = os.Remove(path)
		return err
	}
	changed, err := result.RowsAffected()
	if err != nil || changed != 1 {
		_ = os.Remove(path)
		return fmt.Errorf("visual capture claim expired")
	}
	return nil
}

func (s *Store) claimVisualCapture(ctx context.Context) (claimedVisualCapture, string, bool, error) {
	var capture claimedVisualCapture
	var target protocol.VisualTarget
	var phase string
	err := s.db.QueryRowContext(ctx, `SELECT capture.work_id,capture.phase,target.url,target.state_text,target.viewport_width,target.viewport_height FROM visual_captures capture JOIN task_visual_targets target ON target.work_id=capture.work_id WHERE capture.status='pending' OR (capture.status='running' AND capture.updated_at<?) OR (capture.status='missing' AND capture.updated_at<?) ORDER BY CASE capture.phase WHEN 'before' THEN 0 ELSE 1 END,target.created_at LIMIT 1`, s.now().UTC().Add(-5*time.Minute).Format(time.RFC3339Nano), s.now().UTC().Add(-time.Hour).Format(time.RFC3339Nano)).Scan(&capture.WorkID, &phase, &target.URL, &target.StateText, &target.ViewportWidth, &target.ViewportHeight)
	if err != nil {
		if err == sql.ErrNoRows {
			return capture, "", false, nil
		}
		return capture, "", false, unavailable(err)
	}
	token, err := newID()
	if err != nil {
		return capture, "", false, err
	}
	now := s.now().UTC().Format(time.RFC3339Nano)
	result, err := s.db.ExecContext(ctx, `UPDATE visual_captures SET status='running',claim_token=?,error='',updated_at=? WHERE work_id=? AND phase=? AND (status='pending' OR (status='running' AND updated_at<?) OR (status='missing' AND updated_at<?))`, token, now, capture.WorkID, phase, s.now().UTC().Add(-5*time.Minute).Format(time.RFC3339Nano), s.now().UTC().Add(-time.Hour).Format(time.RFC3339Nano))
	if err != nil {
		return capture, "", false, unavailable(err)
	}
	changed, err := result.RowsAffected()
	if err != nil || changed != 1 {
		return capture, "", false, err
	}
	capture.Phase, capture.Target = phase, target
	return capture, token, true, nil
}

func (s *Store) failVisualCapture(ctx context.Context, workID, phase, token string, cause error) {
	_, _ = s.db.ExecContext(ctx, `UPDATE visual_captures SET status='missing',error=?,updated_at=? WHERE work_id=? AND phase=? AND status='running' AND claim_token=?`, cause.Error(), s.now().UTC().Format(time.RFC3339Nano), workID, phase, token)
}
