package controlplane

import (
	"context"
	"math"
	"testing"
	"time"

	"github.com/owainlewis/factory/internal/protocol"
)

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
	if !first.Periods[metricsWindow24Hours].LowData || first.Periods[metricsWindow24Hours].Samples != 1 {
		t.Fatalf("first observation presented as history: %#v", first.Periods[metricsWindow24Hours])
	}
	if got := first.Periods[metricsWindow24Hours].Underload[0]; got.Reason != "no_ready_work" {
		t.Fatalf("empty queue reason = %#v", got)
	}

	seedEfficiencyTask(t, store, repository.ID, "product-running", "[auto] [3/5 Implement + Test] Product", "running", now, now, now)
	seedEfficiencyTask(t, store, repository.ID, "queued", "[auto] [4/5 Review] Product", "running", now, now, now)
	if _, err := store.db.Exec(`UPDATE executions SET state = 'queued' WHERE id = 'execution-queued'`); err != nil {
		t.Fatal(err)
	}
	seedEfficiencyTask(t, store, repository.ID, "helper-running", "[helper] housekeeping", "running", now, now, now)
	now = now.Add(time.Minute)
	second, err := store.ProductCapacity(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	period := second.Periods[metricsWindow24Hours]
	if !period.LowData || period.Samples != 2 || period.QueueP90 == nil || *period.QueueP90 != 1 {
		t.Fatalf("second observation = %#v", period)
	}
	unknown := period.Underload[len(period.Underload)-1]
	if unknown.Reason != "unknown" || unknown.Seconds != 0 {
		t.Fatalf("unknown reason is not explicit: %#v", unknown)
	}
	// The just-recorded queued sample has no elapsed interval yet. The next one proves
	// that its unknown cause, rather than a guessed provider or release cause, is retained.
	now = now.Add(time.Minute)
	third, err := store.ProductCapacity(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	unknown = third.Periods[metricsWindow24Hours].Underload[len(period.Underload)-1]
	if unknown.Seconds != 60 {
		t.Fatalf("unknown interval seconds = %#v", unknown)
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
