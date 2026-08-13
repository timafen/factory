package controlplane

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"os"
	"testing"
	"time"

	"github.com/owainlewis/factory/internal/protocol"
)

type retryCapturer struct{ calls int }

func (capturer *retryCapturer) Capture(_ context.Context, _ protocol.VisualTarget, output string) error {
	capturer.calls++
	if capturer.calls == 1 {
		return errors.New("temporary browser failure")
	}
	return os.WriteFile(output, []byte("\x89PNG\r\n\x1a\nimage"), 0o600)
}

func TestVisualCaptureRetriesAndPublishesVerifiedPNG(t *testing.T) {
	store := newTestStore(t)
	now := time.Date(2026, 8, 13, 9, 0, 0, 0, time.UTC)
	store.now = func() time.Time { return now }
	if _, err := store.db.Exec(`INSERT INTO task_visual_targets(work_id,url,state_text,viewport_width,viewport_height,created_at) VALUES('visual-work','https://example.test/listings','Готово',1280,720,?)`, now.UnixMilli()); err != nil {
		t.Fatal(err)
	}
	if _, err := store.db.Exec(`INSERT INTO visual_captures(work_id,phase,status,updated_at) VALUES('visual-work','before','pending',?)`, now.Format(time.RFC3339Nano)); err != nil {
		t.Fatal(err)
	}
	capturer := &retryCapturer{}
	service := &VisualCaptureService{store: store, logger: slog.New(slog.NewTextHandler(io.Discard, nil)), capturer: capturer, root: t.TempDir(), captureTimeout: time.Second}
	service.runOnce(context.Background())
	var status string
	if err := store.db.QueryRow(`SELECT status FROM visual_captures WHERE work_id='visual-work' AND phase='before'`).Scan(&status); err != nil || status != "missing" {
		t.Fatalf("first status=%q err=%v", status, err)
	}
	now = now.Add(2 * time.Hour)
	service.runOnce(context.Background())
	var path, hash string
	if err := store.db.QueryRow(`SELECT status,path,sha256 FROM visual_captures WHERE work_id='visual-work' AND phase='before'`).Scan(&status, &path, &hash); err != nil || status != "ready" || path == "" || hash == "" {
		t.Fatalf("retry status=%q path=%q hash=%q err=%v", status, path, hash, err)
	}
	if capturer.calls != 2 {
		t.Fatalf("capture calls=%d", capturer.calls)
	}
}

func TestSuccessfulConfiguredStageQueuesAfterCapture(t *testing.T) {
	store := newTestStore(t)
	worker := registerTestWorker(t, store, workerA, 1, protocol.RepositoryRegistration{Key: "factory", RemoteIdentity: "github.com/example/visual-after"})
	task := createTestTask(t, store, "visual-after", workerA, worker.Repositories[0].ID)
	if _, err := store.db.Exec(`INSERT INTO task_visual_targets(work_id,url,state_text,viewport_width,viewport_height,after_workflow_title,created_at) VALUES(?,?,?,?,?,?,?)`, task.Task.WorkID, "https://example.test", "Готово", 800, 600, "", store.now().UnixMilli()); err != nil {
		t.Fatal(err)
	}
	if _, err := store.db.Exec(`INSERT INTO visual_captures(work_id,phase,status,updated_at) VALUES(?,'before','ready',?)`, task.Task.WorkID, store.now().UTC().Format(time.RFC3339Nano)); err != nil {
		t.Fatal(err)
	}
	claim := claimTestTask(t, store, workerA, "visual-after-claim", tokenA)
	if _, err := store.StartAttempt(context.Background(), claim.Attempt.ID, protocol.StartAttemptRequest{LeaseToken: tokenA}); err != nil {
		t.Fatal(err)
	}
	if _, err := store.CompleteAttempt(context.Background(), claim.Attempt.ID, protocol.CompleteAttemptRequest{LeaseToken: tokenA, State: "succeeded"}); err != nil {
		t.Fatal(err)
	}
	var status string
	if err := store.db.QueryRow(`SELECT status FROM visual_captures WHERE work_id=? AND phase='after'`, task.Task.WorkID).Scan(&status); err != nil || status != "pending" {
		t.Fatalf("after status=%q err=%v", status, err)
	}
}
