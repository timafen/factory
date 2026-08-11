package controlplane

import (
	"context"
	"math"
	"testing"
	"time"

	"github.com/owainlewis/factory/internal/protocol"
)

func TestMetricsSummarizesBoundedExecutionFacts(t *testing.T) {
	store := newTestStore(t)
	now := time.Date(2026, time.July, 30, 12, 0, 0, 0, time.UTC)
	store.now = func() time.Time { return now }
	seedMetricsWorker(t, store, "worker-online", now.Add(-5*time.Second))
	seedMetricsWorker(t, store, "worker-offline", now.Add(-protocol.WorkerOnlineWindow-time.Millisecond))
	weeklyReset := now.Add(5 * 24 * time.Hour)
	if _, err := store.db.Exec(`
		UPDATE workers
		SET weekly_limit_used_percent = 11, weekly_limit_resets_at = ?
		WHERE id = 'worker-online'
	`, weeklyReset.UnixMilli()); err != nil {
		t.Fatal(err)
	}

	seedMetricsExecution(t, store, metricsExecution{
		id: "queued", state: "queued", createdAt: now.Add(-10 * time.Minute),
	})
	seedMetricsExecution(t, store, metricsExecution{
		id: "preparing", state: "preparing", createdAt: now.Add(-9 * time.Minute),
	})
	seedMetricsExecution(t, store, metricsExecution{
		id: "running", state: "running", createdAt: now.Add(-8 * time.Minute),
	})
	seedMetricsExecution(t, store, metricsExecution{
		id: "succeeded-one", state: "succeeded",
		createdAt: now.Add(-3 * time.Hour), updatedAt: now.Add(-2 * time.Hour),
		attempts: 1,
	})
	seedMetricsExecution(t, store, metricsExecution{
		id: "succeeded-retried", state: "succeeded",
		createdAt: now.Add(-5 * time.Hour), updatedAt: now.Add(-3 * time.Hour),
		attempts: 2, retries: 1,
	})
	seedMetricsExecution(t, store, metricsExecution{
		id: "failed", state: "failed",
		createdAt: now.Add(-4 * time.Hour), updatedAt: now.Add(-time.Hour),
		attempts: 1,
	})
	seedMetricsExecution(t, store, metricsExecution{
		id: "cancelled", state: "cancelled",
		createdAt: now.Add(-2 * time.Hour), updatedAt: now.Add(-30 * time.Minute),
	})
	seedMetricsExecution(t, store, metricsExecution{
		id: "old", state: "succeeded",
		createdAt: now.Add(-9 * 24 * time.Hour), updatedAt: now.Add(-8 * 24 * time.Hour),
		attempts: 1,
	})

	summary, err := store.Metrics(context.Background(), metricsWindow7Days)
	if err != nil {
		t.Fatal(err)
	}
	if summary.Window != metricsWindow7Days || !summary.GeneratedAt.Equal(now) {
		t.Fatalf("window metadata = %q %s", summary.Window, summary.GeneratedAt)
	}
	if summary.ExecutionsCreated != 7 || summary.ExecutionsCompleted != 4 {
		t.Fatalf(
			"execution counts = created %d completed %d",
			summary.ExecutionsCreated,
			summary.ExecutionsCompleted,
		)
	}
	if summary.Succeeded != 2 || summary.Failed != 1 || summary.Cancelled != 1 {
		t.Fatalf(
			"outcomes = succeeded %d failed %d cancelled %d",
			summary.Succeeded,
			summary.Failed,
			summary.Cancelled,
		)
	}
	if summary.Queued != 1 || summary.Running != 2 {
		t.Fatalf("live work = queued %d running %d", summary.Queued, summary.Running)
	}
	requireMetricRate(t, "success", summary.SuccessRate, 2.0/3.0)
	requireMetricRate(t, "retry", summary.RetryRate, 1.0/3.0)
	requireMetricRate(t, "median cycle seconds", summary.MedianCycleTimeSeconds, 2*time.Hour.Seconds())
	if summary.WorkersOnline != 1 || summary.WorkersTotal != 2 {
		t.Fatalf("workers = online %d total %d", summary.WorkersOnline, summary.WorkersTotal)
	}
	if summary.WeeklyLimit == nil || summary.WeeklyLimit.UsedPercent != 11 ||
		!summary.WeeklyLimit.ResetsAt.Equal(weeklyReset) {
		t.Fatalf("weekly limit = %#v", summary.WeeklyLimit)
	}

	all, err := store.Metrics(context.Background(), metricsWindowAll)
	if err != nil {
		t.Fatal(err)
	}
	if all.ExecutionsCreated != 8 || all.ExecutionsCompleted != 5 || all.Succeeded != 3 {
		t.Fatalf(
			"all-time counts = created %d completed %d succeeded %d",
			all.ExecutionsCreated,
			all.ExecutionsCompleted,
			all.Succeeded,
		)
	}
}

func TestMetricsCountsCapacityReconciliationsInWindow(t *testing.T) {
	store := newTestStore(t)
	now := time.Date(2026, time.August, 11, 12, 0, 0, 0, time.UTC)
	store.now = func() time.Time { return now }
	seedMetricsWorker(t, store, "capacity-metrics", now)
	if _, err := store.db.Exec(`
		INSERT INTO worker_capacity_reconciliations(worker_id, reconciled_at, trigger, previous_active_count, derived_active_count, ghost_slots_released)
		VALUES ('capacity-metrics', ?, 'sweep', 2, 0, 2), ('capacity-metrics', ?, 'claim', 0, 1, 0)
	`, now.Add(-time.Hour).UnixMilli(), now.Add(-8*24*time.Hour).UnixMilli()); err != nil {
		t.Fatal(err)
	}
	summary, err := store.Metrics(context.Background(), metricsWindow24Hours)
	if err != nil {
		t.Fatal(err)
	}
	if summary.CapacityReconciliations != 1 || summary.GhostSlotsReleased != 2 {
		t.Fatalf("capacity metrics = reconciliations %d, ghost slots %d; want 1, 2", summary.CapacityReconciliations, summary.GhostSlotsReleased)
	}
}

func TestSweepExpiredPrunesExpiredReconciliationRowsWhenWorkersAreIdle(t *testing.T) {
	store := newTestStore(t)
	now := time.Date(2026, time.August, 11, 12, 0, 0, 0, time.UTC)
	store.now = func() time.Time { return now }
	worker := "capacity-retention"
	seedMetricsWorker(t, store, worker, now)
	if _, err := store.db.Exec(`
		INSERT INTO worker_capacity_reconciliations(worker_id, reconciled_at, trigger, previous_active_count, derived_active_count, ghost_slots_released)
		VALUES (?, ?, 'claim', 1, 0, 0), (?, ?, 'claim', 1, 0, 0)
	`, worker, now.Add(-capacityRetention-time.Millisecond).UnixMilli(), worker, now.Add(-time.Hour).UnixMilli()); err != nil {
		t.Fatal(err)
	}
	if expired, err := store.SweepExpired(context.Background()); err != nil {
		t.Fatal(err)
	} else if len(expired) != 0 {
		t.Fatalf("expired leases = %d; want 0", len(expired))
	}
	var expired, retained int
	if err := store.db.QueryRow(`SELECT COUNT(*) FROM worker_capacity_reconciliations WHERE reconciled_at < ?`, now.Add(-capacityRetention).UnixMilli()).Scan(&expired); err != nil {
		t.Fatal(err)
	}
	if err := store.db.QueryRow(`SELECT COUNT(*) FROM worker_capacity_reconciliations WHERE reconciled_at >= ?`, now.Add(-capacityRetention).UnixMilli()).Scan(&retained); err != nil {
		t.Fatal(err)
	}
	if expired != 0 || retained != 1 {
		t.Fatalf("journal retention = expired %d retained %d; want 0, 1", expired, retained)
	}
	summary, err := store.Metrics(context.Background(), metricsWindow24Hours)
	if err != nil || summary.CapacityReconciliations != 1 {
		t.Fatalf("in-window reconciliation metrics = %d, %v; want 1", summary.CapacityReconciliations, err)
	}
}

func TestMetricsHaveUndefinedRatesWithoutCompletedAgentOutcomes(t *testing.T) {
	store := newTestStore(t)
	store.now = func() time.Time {
		return time.Date(2026, time.July, 30, 12, 0, 0, 0, time.UTC)
	}
	summary, err := store.Metrics(context.Background(), "")
	if err != nil {
		t.Fatal(err)
	}
	if summary.Window != metricsWindow7Days {
		t.Fatalf("default window = %q", summary.Window)
	}
	if summary.SuccessRate != nil || summary.RetryRate != nil ||
		summary.MedianCycleTimeSeconds != nil {
		t.Fatalf("empty metrics exposed invented rates: %#v", summary)
	}
}

func TestMetricsCountQueueReassignmentsByEventTime(t *testing.T) {
	store := newTestStore(t)
	now := time.Date(2026, time.July, 30, 12, 0, 0, 0, time.UTC)
	store.now = func() time.Time { return now }
	seedMetricsWorker(t, store, "worker-online", now)
	seedMetricsWorker(t, store, "worker-old", now)
	seedMetricsExecution(t, store, metricsExecution{
		id: "reassigned", state: "queued", createdAt: now.Add(-48 * time.Hour), updatedAt: now,
	})
	if _, err := store.db.Exec(`
		INSERT INTO execution_reassignments(execution_id, from_worker_id, to_worker_id, reassigned_at)
		VALUES ('execution-reassigned', 'worker-old', 'worker-online', ?)
	`, now.Add(-25*time.Hour).UnixMilli()); err != nil {
		t.Fatal(err)
	}
	// A later execution update must not pull this old reassignment into the new window.
	if _, err := store.db.Exec(`UPDATE executions SET updated_at = ? WHERE id = 'execution-reassigned'`, now.UnixMilli()); err != nil {
		t.Fatal(err)
	}

	summary, err := store.Metrics(context.Background(), metricsWindow24Hours)
	if err != nil {
		t.Fatal(err)
	}
	if summary.QueueReassignments != 0 {
		t.Fatalf("24h reassignments = %d, want 0", summary.QueueReassignments)
	}
}

func TestMetricsCountExplicitRetryBeforeFirstClaim(t *testing.T) {
	store := newTestStore(t)
	now := time.Date(2026, time.July, 30, 12, 0, 0, 0, time.UTC)
	store.now = func() time.Time { return now }
	seedMetricsWorker(t, store, "worker-online", now.Add(-5*time.Second))
	seedMetricsExecution(t, store, metricsExecution{
		id:        "cancelled-before-claim",
		state:     "cancelled",
		createdAt: now.Add(-time.Hour),
		updatedAt: now.Add(-30 * time.Minute),
	})

	if _, err := store.RetryExecution(
		context.Background(),
		"execution-cancelled-before-claim",
	); err != nil {
		t.Fatal(err)
	}
	if _, err := store.db.Exec(`
		UPDATE executions
		SET state = 'succeeded', updated_at = ?
		WHERE id = 'execution-cancelled-before-claim'
	`, now.UnixMilli()); err != nil {
		t.Fatal(err)
	}

	summary, err := store.Metrics(context.Background(), metricsWindow7Days)
	if err != nil {
		t.Fatal(err)
	}
	requireMetricRate(t, "retry", summary.RetryRate, 1)
}

func TestMetricsColumnsAreIndexed(t *testing.T) {
	store := newTestStore(t)
	for _, name := range []string{
		"executions_metrics_created",
		"executions_metrics_outcomes",
	} {
		var count int
		if err := store.db.QueryRow(`
			SELECT COUNT(*) FROM sqlite_master
			WHERE type = 'index' AND name = ?
		`, name).Scan(&count); err != nil {
			t.Fatal(err)
		}
		if count != 1 {
			t.Fatalf("metrics index %q count = %d", name, count)
		}
	}
}

func requireMetricRate(t *testing.T, name string, value *float64, expected float64) {
	t.Helper()
	if value == nil || math.Abs(*value-expected) > 0.000001 {
		t.Fatalf("%s = %v, want %f", name, value, expected)
	}
}

type metricsExecution struct {
	id        string
	state     string
	createdAt time.Time
	updatedAt time.Time
	attempts  int
	retries   int
}

func seedMetricsWorker(t *testing.T, store *Store, id string, lastHeartbeat time.Time) {
	t.Helper()
	if _, err := store.db.Exec(`
		INSERT INTO workers(
			id, name, worker_version, runtime, runtime_version, capacity, active_count, health,
			retained_worktrees_json, registered_at, last_heartbeat
		) VALUES (?, ?, 'test', 'codex', 'test', 1, 0, 'healthy', '[]', ?, ?)
	`, id, id, lastHeartbeat.Add(-time.Hour).UnixMilli(), lastHeartbeat.UnixMilli()); err != nil {
		t.Fatal(err)
	}
}

func seedMetricsExecution(t *testing.T, store *Store, value metricsExecution) {
	t.Helper()
	if value.updatedAt.IsZero() {
		value.updatedAt = value.createdAt
	}
	repositoryID := "repository-" + value.id
	taskID := "task-" + value.id
	executionID := "execution-" + value.id
	if _, err := store.db.Exec(
		`INSERT INTO repositories(id, remote_identity, created_at) VALUES (?, ?, ?)`,
		repositoryID,
		"github.com/example/"+value.id,
		value.createdAt.UnixMilli(),
	); err != nil {
		t.Fatal(err)
	}
	if _, err := store.db.Exec(`
		INSERT INTO worker_repositories(
			worker_id, display_key, repository_id, retained_count, advertised, updated_at
		) VALUES ('worker-online', ?, ?, 0, 1, ?)
	`, value.id, repositoryID, value.createdAt.UnixMilli()); err != nil {
		t.Fatal(err)
	}
	if _, err := store.db.Exec(`
		INSERT INTO tasks(
			id, request_key, title, description, repository_id, timeout_seconds, created_at
		) VALUES (?, ?, ?, 'metrics fixture', ?, 3600, ?)
	`, taskID, "request-"+value.id, value.id, repositoryID, value.createdAt.UnixMilli()); err != nil {
		t.Fatal(err)
	}
	if _, err := store.db.Exec(`
		INSERT INTO executions(
			id, task_id, assigned_worker_id, required_runtime, state,
			cancellation_requested, retry_count, created_at, updated_at
		) VALUES (?, ?, 'worker-online', 'codex', ?, 0, ?, ?, ?)
	`,
		executionID,
		taskID,
		value.state,
		value.retries,
		value.createdAt.UnixMilli(),
		value.updatedAt.UnixMilli(),
	); err != nil {
		t.Fatal(err)
	}
	for index := 1; index <= value.attempts; index++ {
		state := value.state
		if index < value.attempts {
			state = "failed"
		}
		if _, err := store.db.Exec(`
			INSERT INTO attempts(
				id, execution_id, worker_id, attempt_number, state, lease_digest,
				lease_expires_at, started_at, completed_at, created_at
			) VALUES (?, ?, 'worker-online', ?, ?, X'00', ?, ?, ?, ?)
		`,
			value.id+"-attempt-"+string(rune('0'+index)),
			executionID,
			index,
			state,
			value.updatedAt.UnixMilli(),
			value.createdAt.UnixMilli(),
			value.updatedAt.UnixMilli(),
			value.createdAt.UnixMilli(),
		); err != nil {
			t.Fatal(err)
		}
	}
}
