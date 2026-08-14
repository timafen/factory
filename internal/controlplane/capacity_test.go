package controlplane

import (
	"context"
	"io"
	"log/slog"
	"math"
	"os"
	"path/filepath"
	"sync/atomic"
	"testing"
	"time"

	"github.com/owainlewis/factory/internal/protocol"
)

func TestHasOpenOwnerQuestionExcludesUnelevatedAdminAudits(t *testing.T) {
	home := t.TempDir()
	t.Setenv("FACTORY_DATA_HOME", home)
	directory := filepath.Join(home, "pilot", "questions")
	if err := os.MkdirAll(directory, 0o755); err != nil {
		t.Fatal(err)
	}
	for name, content := range map[string]string{
		"admin-running.json": `{"status":"open","authority":"admin"}`,
		"admin-failed.json":  `{"status":"open","authority":"admin","admin_result":"failed"}`,
	} {
		if err := os.WriteFile(filepath.Join(directory, name), []byte(content), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	if hasOpenOwnerQuestion() {
		t.Fatal("unelevated admin audits were treated as an owner question")
	}
	if err := os.WriteFile(filepath.Join(directory, "admin-escalated.json"), []byte(`{"status":"open","authority":"admin","owner_only":true}`), 0o644); err != nil {
		t.Fatal(err)
	}
	if !hasOpenOwnerQuestion() {
		t.Fatal("explicit admin escalation was not treated as an owner question")
	}
}

func TestProductCapacityStartsSamplingWithoutInventingHistory(t *testing.T) {
	store := newTestStore(t)
	now := time.Date(2026, time.August, 10, 12, 0, 0, 0, time.UTC)
	store.now = func() time.Time { return now }
	repository := createManagedTestRepository(t, store, "github.com/example/capacity")
	if _, err := store.RegisterWorker(context.Background(), "efficiency-worker", protocol.WorkerRegistration{Name: "capacity-worker", WorkerVersion: "test", RuntimeVersion: "test", Capacity: 4, Health: "healthy", AcceptsManagedRepositories: true, ManagedRepositoryIDs: []string{repository.ID}}); err != nil {
		t.Fatal(err)
	}

	first, err := store.ProductCapacity(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if !first.Periods[metricsWindow24Hours].LowData || first.Periods[metricsWindow24Hours].Samples != 0 {
		t.Fatalf("first observation presented as history: %#v", first.Periods[metricsWindow24Hours])
	}
	if len(first.Periods[metricsWindow24Hours].Underload) != 0 {
		t.Fatalf("unobserved reasons were exposed: %#v", first.Periods[metricsWindow24Hours].Underload)
	}
	if err := store.recordProductCapacitySample(context.Background(), now); err != nil {
		t.Fatal(err)
	}

	seedEfficiencyTask(t, store, repository.ID, "product-running", "[auto] [3/5 Implement + Test] Product", "running", now, now, now)
	seedEfficiencyTask(t, store, repository.ID, "queued", "[auto] [4/5 Review] Product", "running", now, now, now)
	if _, err := store.db.Exec(`UPDATE executions SET state = 'queued' WHERE id = 'execution-queued'`); err != nil {
		t.Fatal(err)
	}
	seedEfficiencyTask(t, store, repository.ID, "helper-running", "[helper] housekeeping", "running", now, now, now)
	now = now.Add(time.Minute)
	if err := store.recordProductCapacitySample(context.Background(), now); err != nil {
		t.Fatal(err)
	}
	second, err := store.ProductCapacity(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	period := second.Periods[metricsWindow24Hours]
	if !period.LowData || period.Samples != 2 || period.QueueP90 == nil || *period.QueueP90 != 1 {
		t.Fatalf("second observation = %#v", period)
	}
	unknown := capacityReason(t, period, "unknown")
	if unknown.Reason != "unknown" || unknown.Seconds != 0 {
		t.Fatalf("unknown reason is not explicit: %#v", unknown)
	}
	for _, invented := range []string{"provider_limit", "repository_conflict", "release_lock"} {
		for _, reason := range period.Underload {
			if reason.Reason == invented {
				t.Fatalf("unproved reason %q was exposed: %#v", invented, period.Underload)
			}
		}
	}
	// The just-recorded queued sample has no elapsed interval yet. The next one proves
	// that its unknown cause, rather than a guessed provider or release cause, is retained.
	now = now.Add(time.Minute)
	if err := store.recordProductCapacitySample(context.Background(), now); err != nil {
		t.Fatal(err)
	}
	third, err := store.ProductCapacity(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	unknown = capacityReason(t, third.Periods[metricsWindow24Hours], "unknown")
	if unknown.Seconds != 60 {
		t.Fatalf("unknown interval seconds = %#v", unknown)
	}
}

func TestProductCapacityCountsDirectAndDelegatedProductButExcludesServiceWork(t *testing.T) {
	store := newTestStore(t)
	now := time.Date(2026, time.August, 10, 12, 0, 0, 0, time.UTC)
	repository := createManagedTestRepository(t, store, "github.com/example/classification")
	if _, err := store.RegisterWorker(context.Background(), "efficiency-worker", protocol.WorkerRegistration{
		Name: "capacity-worker", WorkerVersion: "test", RuntimeVersion: "test", Capacity: 8,
		Health: "healthy", AcceptsManagedRepositories: true, ManagedRepositoryIDs: []string{repository.ID},
	}); err != nil {
		t.Fatal(err)
	}
	seedEfficiencyTask(t, store, repository.ID, "direct", "Исправить оплату", "running", now, now, now)
	seedEfficiencyTask(t, store, repository.ID, "delegated", "Проверить мобильную корзину", "running", now, now, now)
	if _, err := store.db.Exec(`UPDATE executions SET state = 'queued' WHERE id = 'execution-delegated'`); err != nil {
		t.Fatal(err)
	}
	seedEfficiencyTask(t, store, repository.ID, "pipeline", "[auto] [3/5 Implement + Test] Каталог", "running", now, now, now)
	for _, fixture := range []struct{ id, title string }{
		{"helper", "[helper] обновить индекс"}, {"debug", "[debug] проверить runner"},
		{"service", "[service] очистить кэш"}, {"epic", "[epic-plan] разбить цель"},
	} {
		seedEfficiencyTask(t, store, repository.ID, fixture.id, fixture.title, "running", now, now, now)
	}
	patrol := seedEfficiencyTask(t, store, repository.ID, "capacity-patrol", "[auto] [1/5 Triage] Патруль", "running", now, now, now)
	scheduled := seedEfficiencyTask(t, store, repository.ID, "capacity-scheduled", "Плановая проверка", "running", now, now, now)
	linkEfficiencySchedule(t, store, repository.ID, patrol, "capacity-patrol", PipelinePatrolInstruction, now)
	linkEfficiencySchedule(t, store, repository.ID, scheduled, "capacity-scheduled", "Run scheduled maintenance.", now)

	active, queued, err := store.currentProductWorkCounts(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if active != 2 || queued != 1 {
		t.Fatalf("product counts = active %d queued %d, want direct+pipeline 2 and delegated 1", active, queued)
	}
}

func TestProductCapacitySamplerWritesWithoutMetricsGETAndStops(t *testing.T) {
	store := newTestStore(t)
	base := time.Date(2026, time.August, 10, 12, 0, 0, 0, time.UTC)
	var clock atomic.Int64
	store.now = func() time.Time { return base.Add(time.Duration(clock.Add(1)) * time.Minute) }
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() {
		defer close(done)
		store.runProductCapacitySampler(ctx, slog.New(slog.NewTextHandler(io.Discard, nil)), 20*time.Millisecond)
	}()

	deadline := time.Now().Add(10 * time.Second)
	for {
		var samples int
		if err := store.db.QueryRow(`SELECT COUNT(*) FROM product_capacity_samples`).Scan(&samples); err != nil {
			t.Fatal(err)
		}
		if samples >= 2 {
			break
		}
		if time.Now().After(deadline) {
			t.Fatal("background sampler did not write two samples")
		}
		time.Sleep(25 * time.Millisecond)
	}
	cancel()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("capacity sampler did not stop after cancellation")
	}
	var stoppedAt int
	if err := store.db.QueryRow(`SELECT COUNT(*) FROM product_capacity_samples`).Scan(&stoppedAt); err != nil {
		t.Fatal(err)
	}
	time.Sleep(15 * time.Millisecond)
	var after int
	if err := store.db.QueryRow(`SELECT COUNT(*) FROM product_capacity_samples`).Scan(&after); err != nil {
		t.Fatal(err)
	}
	if after != stoppedAt {
		t.Fatalf("sampler wrote after shutdown: before %d after %d", stoppedAt, after)
	}
}

func TestProductCapacityRetentionAndWeightedSummary(t *testing.T) {
	store := newTestStore(t)
	now := time.Date(2026, time.August, 10, 12, 0, 0, 0, time.UTC)
	store.now = func() time.Time { return now }
	for _, sample := range []struct {
		offset        time.Duration
		active, queue int
		reason        string
	}{
		{-25 * time.Hour, 4, 9, "none"}, {-2 * time.Hour, 0, 0, "no_ready_work"}, {-time.Hour, 2, 3, "unknown"},
	} {
		if _, err := store.db.Exec(`INSERT INTO product_capacity_samples VALUES (?, ?, ?, ?)`, now.Add(sample.offset).UnixMilli(), sample.active, sample.queue, sample.reason); err != nil {
			t.Fatal(err)
		}
	}
	period, err := store.productCapacityPeriod(context.Background(), now.Add(-2*time.Hour), now)
	if err != nil {
		t.Fatal(err)
	}
	if period.AverageBusy == nil || math.Abs(*period.AverageBusy-1) > 0.00001 || period.QueueP90 == nil || *period.QueueP90 != 3 {
		t.Fatalf("weighted summary = %#v", period)
	}
	if period.ActiveTime[0].Seconds != 3600 || period.ActiveTime[2].Seconds != 3600 {
		t.Fatalf("active distribution = %#v", period.ActiveTime)
	}
	if err := store.recordProductCapacitySample(context.Background(), now); err != nil {
		t.Fatal(err)
	}
	var old int
	if err := store.db.QueryRow(`SELECT COUNT(*) FROM product_capacity_samples WHERE sampled_at < ?`, now.Add(-capacityRetention).UnixMilli()).Scan(&old); err != nil {
		t.Fatal(err)
	}
	if old != 0 {
		t.Fatalf("expired samples retained: %d", old)
	}
}

func TestHTTPProductCapacity(t *testing.T) {
	fixture := newHTTPFixture(t)
	response := fixture.request("GET", "/api/v1/metrics/product-capacity", "", "", nil)
	requireStatus(t, response, 200)
	summary := decodeResponse[ProductCapacitySummary](t, response)
	if summary.Capacity != productCapacity || !summary.Periods[metricsWindow24Hours].LowData {
		t.Fatalf("capacity response = %#v", summary)
	}
}

func capacityReason(t *testing.T, period ProductCapacityPeriod, want string) ProductCapacityReasonShare {
	t.Helper()
	for _, reason := range period.Underload {
		if reason.Reason == want {
			return reason
		}
	}
	t.Fatalf("reason %q is absent from %#v", want, period.Underload)
	return ProductCapacityReasonShare{}
}
