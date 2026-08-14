package controlplane

import (
	"context"
	"encoding/json"
	"log/slog"
	"math"
	"os"
	"path/filepath"
	"sort"
	"time"
)

const (
	productCapacity          = 4
	capacitySampleResolution = time.Minute
	capacityRetention        = 8 * 24 * time.Hour
	capacitySampleLimit      = 12000
)

type ProductCapacitySummary struct {
	GeneratedAt time.Time                        `json:"generated_at"`
	Capacity    int                              `json:"capacity"`
	Periods     map[string]ProductCapacityPeriod `json:"periods"`
}

type ProductCapacityPeriod struct {
	StartedAt       time.Time                    `json:"started_at"`
	EndedAt         time.Time                    `json:"ended_at"`
	ObservationFrom *time.Time                   `json:"observation_from,omitempty"`
	Samples         int                          `json:"samples"`
	LowData         bool                         `json:"low_data"`
	ActiveTime      []ProductCapacityActiveShare `json:"active_time"`
	AverageBusy     *float64                     `json:"average_busy"`
	QueueP90        *float64                     `json:"queue_p90"`
	Underload       []ProductCapacityReasonShare `json:"underload"`
}

type ProductCapacityActiveShare struct {
	Active  int      `json:"active"`
	Seconds float64  `json:"seconds"`
	Share   *float64 `json:"share"`
}

type ProductCapacityReasonShare struct {
	Reason  string   `json:"reason"`
	Seconds float64  `json:"seconds"`
	Share   *float64 `json:"share"`
}

type capacitySample struct {
	at             time.Time
	active, queued int
	reason         string
}

var capacityReasons = []string{"no_ready_work", "owner_question", "provider_limit", "repository_conflict", "release_lock", "unknown"}

func (s *Store) ProductCapacity(ctx context.Context) (ProductCapacitySummary, error) {
	now := s.now().UTC().Truncate(time.Minute)
	periods := make(map[string]ProductCapacityPeriod, 2)
	for key, duration := range map[string]time.Duration{metricsWindow24Hours: 24 * time.Hour, metricsWindow7Days: 7 * 24 * time.Hour} {
		period, err := s.productCapacityPeriod(ctx, now.Add(-duration), now)
		if err != nil {
			return ProductCapacitySummary{}, err
		}
		periods[key] = period
	}
	return ProductCapacitySummary{GeneratedAt: now, Capacity: productCapacity, Periods: periods}, nil
}

// RunProductCapacitySampler records durable observations independently from
// the metrics endpoint. It returns only after ctx is cancelled.
func (s *Store) RunProductCapacitySampler(ctx context.Context, logger *slog.Logger) {
	s.runProductCapacitySampler(ctx, logger, capacitySampleResolution)
}

func (s *Store) runProductCapacitySampler(ctx context.Context, logger *slog.Logger, every time.Duration) {
	if logger == nil {
		logger = slog.Default()
	}
	ticker := time.NewTicker(every)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			now := s.now().UTC().Truncate(capacitySampleResolution)
			if err := s.recordProductCapacitySample(ctx, now); err != nil && ctx.Err() == nil {
				logger.Error("product_capacity_sample_failed", "error_class", "storage_unavailable")
			}
		}
	}
}

func (s *Store) recordProductCapacitySample(ctx context.Context, now time.Time) error {
	var latest int64
	if err := s.db.QueryRowContext(ctx, `SELECT COALESCE(MAX(sampled_at), 0) FROM product_capacity_samples`).Scan(&latest); err != nil {
		return unavailable(err)
	}
	if latest > 0 && now.UnixMilli()-latest < capacitySampleResolution.Milliseconds() {
		return nil
	}
	active, queued, err := s.currentProductWorkCounts(ctx)
	if err != nil {
		return err
	}
	reason := "none"
	if active < productCapacity {
		switch {
		case queued == 0 && hasOpenOwnerQuestion():
			reason = "owner_question"
		case queued == 0:
			reason = "no_ready_work"
		default:
			reason = "unknown" // The control plane has no durable proof for the queued blockage yet.
		}
	}
	if _, err := s.db.ExecContext(ctx, `INSERT INTO product_capacity_samples(sampled_at, active_works, queued_works, underload_reason) VALUES (?, ?, ?, ?)`, now.UnixMilli(), active, queued, reason); err != nil {
		return unavailable(err)
	}
	cutoff := now.Add(-capacityRetention).UnixMilli()
	if _, err := s.db.ExecContext(ctx, `DELETE FROM product_capacity_samples WHERE sampled_at < ?`, cutoff); err != nil {
		return unavailable(err)
	}
	if _, err := s.db.ExecContext(ctx, `DELETE FROM product_capacity_samples WHERE sampled_at NOT IN (SELECT sampled_at FROM product_capacity_samples ORDER BY sampled_at DESC LIMIT ?)`, capacitySampleLimit); err != nil {
		return unavailable(err)
	}
	return nil
}

func (s *Store) currentProductWorkCounts(ctx context.Context) (int, int, error) {
	rows, err := s.db.QueryContext(ctx, `
		SELECT t.title, e.state,
		       CASE WHEN COUNT(a.id) > 0 THEN 1 ELSE 0 END,
		       CASE WHEN SUM(CASE WHEN a.trigger_type = 'schedule' THEN 1 ELSE 0 END) > 0 THEN 1 ELSE 0 END,
		       COALESCE(GROUP_CONCAT(a.title, ' '), ''),
		       COALESCE(GROUP_CONCAT(a.context, ' '), '')
		FROM executions e JOIN tasks t ON t.id = e.task_id
		LEFT JOIN automation_occurrences o ON o.task_id = t.id
		LEFT JOIN automations a ON a.id = o.automation_id
		WHERE e.state IN ('queued', 'preparing', 'running')
		GROUP BY t.id, t.title, e.state`)
	if err != nil {
		return 0, 0, unavailable(err)
	}
	defer rows.Close()
	active, queued := 0, 0
	for rows.Next() {
		var title, state, automationName, automationText string
		var automationLinked, scheduled int
		if err := rows.Scan(&title, &state, &automationLinked, &scheduled, &automationName, &automationText); err != nil {
			return 0, 0, unavailable(err)
		}
		if classifyWork(workClassificationFacts{
			title: title, automationLinked: automationLinked != 0, scheduled: scheduled != 0,
			automationName: automationName, automationText: automationText,
		}) != workClassProduct {
			continue
		}
		if state == "queued" {
			queued++
		} else {
			active++
		}
	}
	if err := rows.Err(); err != nil {
		return 0, 0, unavailable(err)
	}
	if active > productCapacity {
		active = productCapacity
	}
	return active, queued, nil
}

func hasOpenOwnerQuestion() bool {
	entries, err := os.ReadDir(questionsDir())
	if err != nil {
		return false
	}
	for _, entry := range entries {
		if entry.IsDir() || filepath.Ext(entry.Name()) != ".json" {
			continue
		}
		data, err := os.ReadFile(filepath.Join(questionsDir(), entry.Name()))
		if err != nil {
			continue
		}
		var question struct {
			Status    string `json:"status"`
			Authority string `json:"authority"`
			OwnerOnly bool   `json:"owner_only"`
		}
		if json.Unmarshal(data, &question) == nil && question.Status == "open" &&
			(question.Authority != "admin" || question.OwnerOnly) {
			return true
		}
	}
	return false
}

func (s *Store) productCapacityPeriod(ctx context.Context, start, end time.Time) (ProductCapacityPeriod, error) {
	period := ProductCapacityPeriod{StartedAt: start, EndedAt: end, ActiveTime: make([]ProductCapacityActiveShare, productCapacity+1)}
	for i := range period.ActiveTime {
		period.ActiveTime[i].Active = i
	}
	rows, err := s.db.QueryContext(ctx, `SELECT sampled_at, active_works, queued_works, underload_reason FROM product_capacity_samples WHERE sampled_at <= ? ORDER BY sampled_at`, end.UnixMilli())
	if err != nil {
		return period, unavailable(err)
	}
	defer rows.Close()
	samples := []capacitySample{}
	queueValues := []float64{}
	observedReasons := make(map[string]bool)
	for rows.Next() {
		var raw int64
		var sample capacitySample
		if err := rows.Scan(&raw, &sample.active, &sample.queued, &sample.reason); err != nil {
			return period, unavailable(err)
		}
		sample.at = time.UnixMilli(raw).UTC()
		samples = append(samples, sample)
		if sample.reason != "none" {
			observedReasons[sample.reason] = true
		}
		if !sample.at.Before(start) && !sample.at.After(end) {
			period.Samples++
			queueValues = append(queueValues, float64(sample.queued))
		}
	}
	if err := rows.Err(); err != nil {
		return period, unavailable(err)
	}
	if len(samples) == 0 {
		period.LowData = true
		return period, nil
	}
	first := samples[0].at
	period.ObservationFrom = &first
	underloadSeconds := make(map[string]float64)
	var total, busy float64
	for i, sample := range samples {
		next := end
		if i+1 < len(samples) {
			next = samples[i+1].at
		}
		left, right := sample.at, next
		if left.Before(start) {
			left = start
		}
		if right.After(end) {
			right = end
		}
		if !right.After(left) {
			continue
		}
		seconds := right.Sub(left).Seconds()
		total += seconds
		busy += seconds * float64(sample.active)
		period.ActiveTime[sample.active].Seconds += seconds
		if sample.active < productCapacity && sample.reason != "none" {
			underloadSeconds[sample.reason] += seconds
		}
	}
	if total == 0 {
		period.LowData = true
		return period, nil
	}
	for i := range period.ActiveTime {
		value := period.ActiveTime[i].Seconds / total
		period.ActiveTime[i].Share = &value
	}
	for _, reason := range capacityReasons {
		if !observedReasons[reason] {
			continue
		}
		value := underloadSeconds[reason] / total
		period.Underload = append(period.Underload, ProductCapacityReasonShare{
			Reason: reason, Seconds: underloadSeconds[reason], Share: &value,
		})
	}
	average := busy / total
	period.AverageBusy = &average
	sort.Float64s(queueValues)
	if len(queueValues) > 0 {
		value := queueValues[int(math.Ceil(float64(len(queueValues))*0.9))-1]
		period.QueueP90 = &value
	}
	period.LowData = period.Samples < 2 || first.After(start)
	return period, nil
}
