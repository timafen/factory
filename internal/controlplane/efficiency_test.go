package controlplane

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"net/http"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/owainlewis/factory/internal/protocol"
)

func TestEfficiencyUsesMergedProductWorkAndHonestDenominators(t *testing.T) {
	store := newTestStore(t)
	now := time.Date(2026, time.August, 10, 12, 0, 0, 0, time.UTC)
	store.now = func() time.Time { return now }
	home := t.TempDir()
	t.Setenv("FACTORY_DATA_HOME", home)
	if err := os.MkdirAll(filepath.Join(home, "pilot"), 0o755); err != nil {
		t.Fatal(err)
	}

	repository := createManagedTestRepository(t, store, "github.com/example/product")
	if _, err := store.RegisterWorker(context.Background(), "efficiency-worker", protocol.WorkerRegistration{
		Name: "efficiency-worker", WorkerVersion: "test", RuntimeVersion: "test",
		Capacity: 1, Health: "healthy", AcceptsManagedRepositories: true,
		ManagedRepositoryIDs: []string{repository.ID},
	}); err != nil {
		t.Fatal(err)
	}

	seedEfficiencyTask(t, store, repository.ID, "triage", "[auto] [1/5 Triage] Честный обзор", "succeeded", now.Add(-5*time.Hour), now.Add(-4*time.Hour-50*time.Minute), now.Add(-4*time.Hour-40*time.Minute))
	seedEfficiencyTask(t, store, repository.ID, "implement", "[auto] [3/5 Implement + Test] Честный обзор", "succeeded", now.Add(-4*time.Hour-30*time.Minute), now.Add(-4*time.Hour-20*time.Minute), now.Add(-3*time.Hour-40*time.Minute))
	seedEfficiencyTask(t, store, repository.ID, "review-cancelled", "[auto] [4/5 Review] Честный обзор", "cancelled", now.Add(-3*time.Hour-30*time.Minute), now.Add(-3*time.Hour-20*time.Minute), now.Add(-3*time.Hour))
	if _, err := store.db.Exec(`UPDATE attempts SET started_at = NULL WHERE id = 'attempt-review-cancelled'`); err != nil {
		t.Fatal(err)
	}
	seedEfficiencyTask(t, store, repository.ID, "review-pass", "[auto] [4/5 Review] Честный обзор", "succeeded", now.Add(-2*time.Hour-50*time.Minute), now.Add(-2*time.Hour-40*time.Minute), now.Add(-2*time.Hour-20*time.Minute))
	seedEfficiencyTask(t, store, repository.ID, "verify-fail", "[auto] [5/5 Verify] Честный обзор", "failed", now.Add(-2*time.Hour-10*time.Minute), now.Add(-2*time.Hour), now.Add(-time.Hour-50*time.Minute))
	seedEfficiencyTask(t, store, repository.ID, "verify-pass", "[auto] [5/5 Verify] Честный обзор", "succeeded", now.Add(-time.Hour-40*time.Minute), now.Add(-time.Hour-30*time.Minute), now.Add(-time.Hour-10*time.Minute))
	seedEfficiencyTask(t, store, repository.ID, "dead-end", "[auto] [3/5 Implement + Test] Окончательный тупик", "failed", now.Add(-90*time.Minute), now.Add(-80*time.Minute), now.Add(-70*time.Minute))
	patrolID := seedEfficiencyTask(t, store, repository.ID, "patrol", "[auto] [1/5 Triage] Патруль", "succeeded", now.Add(-80*time.Minute), now.Add(-75*time.Minute), now.Add(-65*time.Minute))
	scheduledID := seedEfficiencyTask(t, store, repository.ID, "scheduled", "Плановое обслуживание", "succeeded", now.Add(-75*time.Minute), now.Add(-70*time.Minute), now.Add(-62*time.Minute))
	seedEfficiencyTask(t, store, repository.ID, "helper", "[helper] обновить индекс", "succeeded", now.Add(-70*time.Minute), now.Add(-65*time.Minute), now.Add(-60*time.Minute))
	seedEfficiencyTask(t, store, repository.ID, "debug", "[debug] проверить runner", "succeeded", now.Add(-69*time.Minute), now.Add(-64*time.Minute), now.Add(-59*time.Minute))
	seedEfficiencyTask(t, store, repository.ID, "service", "[service] очистить кэш", "succeeded", now.Add(-68*time.Minute), now.Add(-63*time.Minute), now.Add(-58*time.Minute))
	linkEfficiencySchedule(t, store, repository.ID, patrolID, "patrol", PipelinePatrolInstruction, now)
	linkEfficiencySchedule(t, store, repository.ID, scheduledID, "maintenance", "Run scheduled maintenance.", now)

	writeJSONLines(t, filepath.Join(home, "pilot", "merges.jsonl"), []any{
		map[string]any{"task_id": "task-verify-pass", "base": "Честный обзор", "at": now.Add(-time.Hour).Format(time.RFC3339)},
		// A duplicate receipt must not inflate throughput.
		map[string]any{"task_id": "task-verify-pass", "base": "Честный обзор", "at": now.Add(-59 * time.Minute).Format(time.RFC3339)},
	})
	writeJSONLines(t, filepath.Join(home, "pilot", "release-events.jsonl"), []any{
		map[string]any{"id": "factory-7", "at": now.Add(-30 * time.Minute).Format(time.RFC3339), "kind": "failed_release", "rollback": true},
		map[string]any{"id": "factory-7", "at": now.Add(-29 * time.Minute).Format(time.RFC3339), "kind": "failed_release", "rollback": true},
	})

	summary, err := store.Efficiency(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if summary.ReleaseObservationStartedAt == nil {
		t.Fatal("release observation start is missing")
	}
	day := summary.Periods[metricsWindow24Hours]
	if day.Assessment != "low_data" {
		t.Fatalf("small sample assessment = %q", day.Assessment)
	}
	got := day.Current
	if got.CompletedWorks != 1 || got.LeadTimeSeconds.Sample != 1 {
		t.Fatalf("merged work sample = %#v", got)
	}
	if got.ReviewFirstPass.Count != 0 || got.ReviewFirstPass.Total != 1 ||
		got.VerifyFirstPass.Count != 0 || got.VerifyFirstPass.Total != 1 {
		t.Fatalf("first-pass rates = review %#v verify %#v", got.ReviewFirstPass, got.VerifyFirstPass)
	}
	if got.Rounds.Sample != 1 || got.Rounds.Median == nil || *got.Rounds.Median != 2 ||
		got.Rounds.P90 == nil || *got.Rounds.P90 != 2 {
		t.Fatalf("round distribution = %#v", got.Rounds)
	}
	if got.AutomaticRecoveries != 2 {
		t.Fatalf("automatic recoveries = %d, want cancelled Review + failed Verify", got.AutomaticRecoveries)
	}
	if got.FinalDeadEnds.Count != 1 || got.FinalDeadEnds.Total != 2 ||
		got.FinalDeadEnds.Rate == nil || math.Abs(*got.FinalDeadEnds.Rate-0.5) > 0.000001 {
		t.Fatalf("dead-end denominator = %#v", got.FinalDeadEnds)
	}
	if got.ProductStageTasks != 7 || got.Excluded.Patrol != 1 || got.Excluded.Scheduled != 1 || got.Excluded.Helper != 3 || got.Excluded.Total != 5 {
		t.Fatalf("product/service split = product %d excluded %#v", got.ProductStageTasks, got.Excluded)
	}
	if got.ReleaseFailures != 1 || got.Rollbacks != 1 {
		t.Fatalf("release incidents = failures %d rollbacks %d", got.ReleaseFailures, got.Rollbacks)
	}
	var shareTotal float64
	shares := make(map[string]EfficiencyTimeShare)
	for _, share := range got.TimeShares {
		if share.Share == nil || share.DenominatorSeconds != 4*time.Hour.Seconds() {
			t.Fatalf("time share denominator = %#v", share)
		}
		shareTotal += *share.Share
		shares[share.Key] = share
	}
	if math.Abs(shareTotal-1) > 0.000001 {
		t.Fatalf("time shares total = %f", shareTotal)
	}
	if got.UnclassifiedThreshold != efficiencyUnclassifiedThreshold || !got.UnclassifiedTooHigh {
		t.Fatalf("unclassified signal = threshold %f high=%v", got.UnclassifiedThreshold, got.UnclassifiedTooHigh)
	}
	if shares["stage_handoff_wait"].Seconds != 30*time.Minute.Seconds() ||
		shares["merge_release_wait"].Seconds != 10*time.Minute.Seconds() ||
		shares["unclassified"].Seconds != 50*time.Minute.Seconds() ||
		shares["unclassified"].Sample != 2 {
		t.Fatalf("diagnostic waits = %#v", shares)
	}
	for _, share := range got.TimeShares {
		if share.Definition == "" {
			t.Fatalf("time share %q has no API definition", share.Key)
		}
	}
}

func TestEfficiencyTargetComparesCurrentAndPreviousStageHandoffShares(t *testing.T) {
	period := func(completedWorks int, value float64) EfficiencyPeriod {
		return EfficiencyPeriod{CompletedWorks: completedWorks, TimeShares: []EfficiencyTimeShare{{
			Key: "stage_handoff_wait", Share: &value,
		}}}
	}

	for _, completedWorks := range []int{0, 1, 4} {
		t.Run(fmt.Sprintf("low sample %d", completedWorks), func(t *testing.T) {
			got := efficiencyStageHandoffWaitTarget(period(completedWorks, 0.08), period(5, 0.25))
			if got.CurrentShare == nil || *got.CurrentShare != 0.08 || got.Met != nil {
				t.Fatalf("low sample must keep the measured share without claiming success = %#v", got)
			}
		})
	}

	met := efficiencyStageHandoffWaitTarget(period(5, 0.10), period(5, 0.25))
	if met.MaximumShare != 0.10 || met.CurrentShare == nil || *met.CurrentShare != 0.10 ||
		met.PreviousShare == nil || *met.PreviousShare != 0.25 || met.Met == nil || !*met.Met {
		t.Fatalf("met target = %#v", met)
	}

	missed := efficiencyStageHandoffWaitTarget(period(5, 0.11), EfficiencyPeriod{})
	if missed.Met == nil || *missed.Met || missed.PreviousShare != nil {
		t.Fatalf("missed target = %#v", missed)
	}

	unknown := efficiencyStageHandoffWaitTarget(EfficiencyPeriod{CompletedWorks: 5}, period(5, 0.25))
	if unknown.CurrentShare != nil || unknown.Met != nil {
		t.Fatalf("unknown target must not claim success = %#v", unknown)
	}
}

func TestEfficiencyWorkSharesClassifiesOnlyProvenIntervals(t *testing.T) {
	start := time.Date(2026, time.August, 10, 8, 0, 0, 0, time.UTC)
	at := func(minutes int) *time.Time {
		value := start.Add(time.Duration(minutes) * time.Minute)
		return &value
	}
	work := efficiencyWork{mergeAt: start.Add(100 * time.Minute), mergedTaskID: "review", tasks: []*efficiencyTask{
		{id: "triage", stage: "Triage", createdAt: start, attempts: []efficiencyAttempt{{startedAt: at(10), completedAt: at(20)}}},
		{id: "review", stage: "Review", createdAt: start.Add(40 * time.Minute), attempts: []efficiencyAttempt{{startedAt: at(50), completedAt: at(70)}}},
	}}
	facts := efficiencyWorkShares(work, start, []efficiencyQuestion{{
		taskID: "triage", askedAt: *at(22), answeredAt: *at(30),
	}})
	wantMinutes := map[string]float64{
		"queue": 20, "Triage": 10, "Review": 20, "stage_handoff_wait": 12,
		"owner_decision_wait": 8, "merge_release_wait": 30, "unclassified": 0,
	}
	for key, minutes := range wantMinutes {
		if got := facts.seconds[key]; got != minutes*time.Minute.Seconds() {
			t.Errorf("%s seconds = %v, want %v", key, got, minutes*time.Minute.Seconds())
		}
	}
	if facts.samples["owner_decision_wait"] != 1 || facts.samples["stage_handoff_wait"] != 2 {
		t.Fatalf("proven interval samples = %#v", facts.samples)
	}
}

func TestEfficiencyIncompleteLegacyTimestampsStayUnclassified(t *testing.T) {
	start := time.Date(2026, time.August, 10, 8, 0, 0, 0, time.UTC)
	work := efficiencyWork{mergeAt: start.Add(time.Hour), mergedTaskID: "legacy", tasks: []*efficiencyTask{{
		id: "legacy", stage: "Verify", createdAt: start,
		attempts: []efficiencyAttempt{{startedAt: nil, completedAt: nil}},
	}}}
	facts := efficiencyWorkShares(work, start, nil)
	if facts.seconds["unclassified"] != time.Hour.Seconds() || facts.samples["unclassified"] != 1 ||
		facts.seconds["queue"] != 0 || facts.seconds["Verify"] != 0 || facts.seconds["merge_release_wait"] != 0 {
		t.Fatalf("incomplete legacy facts were guessed: seconds=%#v samples=%#v", facts.seconds, facts.samples)
	}
	shares := efficiencyTimeShares(facts.seconds, facts.samples, time.Hour.Seconds())
	if shares[len(shares)-1].Key != "unclassified" || shares[len(shares)-1].Share == nil || *shares[len(shares)-1].Share != 1 {
		t.Fatalf("legacy unclassified share = %#v", shares[len(shares)-1])
	}
}

func TestLoadEfficiencyQuestionsIgnoresOldOrAutomatedRecords(t *testing.T) {
	home := t.TempDir()
	t.Setenv("FACTORY_DATA_HOME", home)
	directory := filepath.Join(home, "pilot", "questions")
	if err := os.MkdirAll(directory, 0o755); err != nil {
		t.Fatal(err)
	}
	records := map[string]string{
		"old.json":          `{"task_id":"old","answered_by":"owner","asked_at":"2026-08-10T08:00:00Z"}`,
		"automated.json":    `{"task_id":"auto","answered_by":"orchestrator","asked_at":"2026-08-10T08:00:00Z","answered_at":"2026-08-10T08:10:00Z"}`,
		"owner.json":        `{"task_id":"owner","answered_by":"owner","asked_at":"2026-08-10T08:00:00Z","answered_at":"2026-08-10T08:10:00Z"}`,
		"out-of-order.json": `{"task_id":"bad","answered_by":"owner","asked_at":"2026-08-10T08:10:00Z","answered_at":"2026-08-10T08:00:00Z"}`,
	}
	for name, value := range records {
		if err := os.WriteFile(filepath.Join(directory, name), []byte(value), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	questions, err := loadEfficiencyQuestions()
	if err != nil || len(questions) != 1 || questions[0].taskID != "owner" {
		t.Fatalf("loaded questions = %#v, %v", questions, err)
	}
}

func TestAnswerQuestionRecordsOwnerTimingProof(t *testing.T) {
	home := t.TempDir()
	t.Setenv("FACTORY_DATA_HOME", home)
	directory := filepath.Join(home, "pilot", "questions")
	if err := os.MkdirAll(directory, 0o755); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(directory, "question-1.json")
	if err := os.WriteFile(path, []byte(`{"id":"question-1","task_id":"task-1","status":"open","asked_at":"2026-08-10T08:00:00Z"}`), 0o644); err != nil {
		t.Fatal(err)
	}
	fixture := newHTTPFixture(t)
	now := time.Date(2026, time.August, 10, 8, 12, 0, 0, time.UTC)
	fixture.store.now = func() time.Time { return now }
	response := fixture.request(http.MethodPost, "/api/v1/questions/question-1/answer", "application/json", "", map[string]string{"answer": "Продолжай"})
	requireStatus(t, response, http.StatusOK)
	response.Body.Close()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var record map[string]any
	if json.Unmarshal(data, &record) != nil || record["answered_by"] != "owner" ||
		record["answered_at"] != now.Format(time.RFC3339) {
		t.Fatalf("answer proof = %#v", record)
	}
}

func TestEfficiencyUsesRealLegacyMergeJournalLine(t *testing.T) {
	store := newTestStore(t)
	originalLocal := time.Local
	time.Local = time.FixedZone("Factory local", -5*60*60)
	t.Cleanup(func() { time.Local = originalLocal })

	now := time.Date(2026, time.August, 10, 19, 0, 0, 0, time.UTC)
	store.now = func() time.Time { return now }
	home := t.TempDir()
	t.Setenv("FACTORY_DATA_HOME", home)
	if err := os.MkdirAll(filepath.Join(home, "pilot"), 0o755); err != nil {
		t.Fatal(err)
	}
	repository := createManagedTestRepository(t, store, "github.com/example/product")
	if _, err := store.RegisterWorker(context.Background(), "efficiency-worker", protocol.WorkerRegistration{
		Name: "efficiency-worker", WorkerVersion: "test", RuntimeVersion: "test",
		Capacity: 1, Health: "healthy", AcceptsManagedRepositories: true,
		ManagedRepositoryIDs: []string{repository.ID},
	}); err != nil {
		t.Fatal(err)
	}

	mergeAt := time.Date(2026, time.August, 10, 18, 30, 26, 0, time.UTC)
	seedEfficiencyTaskWithID(t, store, repository.ID,
		"ea6b7c68-13de-4455-ad78-311ab8dd65e0", "legacy-merge",
		"[auto] [5/5 Verify] Настройки Пилота не раскрывают канал уведомлений локальным воркерам",
		"succeeded", mergeAt.Add(-time.Hour), mergeAt.Add(-50*time.Minute), mergeAt.Add(-10*time.Minute))
	journal := []byte("{\"task_id\": \"ea6b7c68-13de-4455-ad78-311ab8dd65e0\", \"base\": \"Настройки Пилота не раскрывают канал уведомлений локальным воркерам\", \"at\": \"2026-08-10 13:30:26\"}\n")
	if err := os.WriteFile(filepath.Join(home, "pilot", "merges.jsonl"), journal, 0o644); err != nil {
		t.Fatal(err)
	}

	merges, err := loadEfficiencyMerges()
	if err != nil {
		t.Fatal(err)
	}
	if len(merges) != 1 || !merges[0].at.Equal(mergeAt) || merges[0].at.Location() != time.UTC {
		t.Fatalf("legacy merge parsed as %#v, want %s UTC", merges, mergeAt)
	}
	summary, err := store.Efficiency(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	got := summary.Periods[metricsWindow24Hours].Current
	if got.CompletedWorks != 1 || got.LeadTimeSeconds.Sample != 1 ||
		got.LeadTimeSeconds.Median == nil || *got.LeadTimeSeconds.Median != time.Hour.Seconds() {
		t.Fatalf("legacy journal metrics = %#v", got)
	}
}

func TestEfficiencyUsesPersistedMergeRoundsAndLegacyFallback(t *testing.T) {
	home := t.TempDir()
	t.Setenv("FACTORY_DATA_HOME", home)
	if err := os.MkdirAll(filepath.Join(home, "pilot"), 0o755); err != nil {
		t.Fatal(err)
	}
	now := time.Date(2026, time.August, 12, 12, 0, 0, 0, time.UTC)
	journalPath := filepath.Join(home, "pilot", "merges.jsonl")
	writeJSONLines(t, journalPath, []any{
		map[string]any{"task_id": "new-verify", "base": "New", "at": now.Add(-time.Hour).Format(time.RFC3339), "actor": "owner", "actor_id": nil, "rounds": 5},
		map[string]any{"task_id": "legacy-verify", "base": "Legacy", "at": now.Add(-30 * time.Minute).Format(time.RFC3339)},
	})
	original, err := os.ReadFile(journalPath)
	if err != nil {
		t.Fatal(err)
	}
	merges, err := loadEfficiencyMerges()
	if err != nil {
		t.Fatal(err)
	}
	if len(merges) != 2 || merges[0].actor != "owner" || merges[0].rounds != 5 ||
		merges[1].actor != "automatic" || merges[1].rounds != 0 {
		t.Fatalf("merge compatibility = %#v", merges)
	}
	tasks := []*efficiencyTask{
		{id: "new-verify", base: "New", stage: "Verify", repositoryID: "repo", state: "succeeded", createdAt: now.Add(-2 * time.Hour)},
		{id: "legacy-implement-1", base: "Legacy", stage: "Implement + Test", repositoryID: "repo", state: "failed", createdAt: now.Add(-50 * time.Minute)},
		{id: "legacy-implement-2", base: "Legacy", stage: "Implement + Test", repositoryID: "repo", state: "succeeded", createdAt: now.Add(-40 * time.Minute)},
		{id: "legacy-verify", base: "Legacy", stage: "Verify", repositoryID: "repo", state: "succeeded", createdAt: now.Add(-35 * time.Minute)},
	}
	works, tails := buildEfficiencyWorks(tasks, merges)
	period := summarizeEfficiencyPeriod(now.Add(-24*time.Hour), now, tasks, works, tails, nil, nil)
	if period.Rounds.Sample != 2 || period.Rounds.Median == nil || *period.Rounds.Median != 3.5 ||
		period.Rounds.P90 == nil || *period.Rounds.P90 != 5 {
		t.Fatalf("persisted and legacy rounds = %#v", period.Rounds)
	}
	after, err := os.ReadFile(journalPath)
	if err != nil || string(after) != string(original) {
		t.Fatalf("legacy journal was rewritten: err=%v", err)
	}
}

func TestEfficiencyEmptyPeriodsDoNotInventRatesOrGreenStatus(t *testing.T) {
	store := newTestStore(t)
	now := time.Date(2026, time.August, 10, 12, 0, 0, 0, time.UTC)
	store.now = func() time.Time { return now }
	t.Setenv("FACTORY_DATA_HOME", t.TempDir())

	summary, err := store.Efficiency(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	for _, key := range []string{metricsWindow24Hours, metricsWindow7Days} {
		period := summary.Periods[key]
		if period.Assessment != "low_data" || period.Current.CompletedWorks != 0 ||
			period.Current.LeadTimeSeconds.Median != nil || period.Current.ReviewFirstPass.Rate != nil ||
			period.Current.FinalDeadEnds.Rate != nil {
			t.Fatalf("empty %s metrics = %#v", key, period)
		}
	}
}

func TestEfficiencyComparisonReportsProgressAndDegradationOnlyWithEnoughData(t *testing.T) {
	rate := func(value float64) EfficiencyRate {
		return EfficiencyRate{Count: int(value * 10), Total: 10, Rate: &value}
	}
	distribution := func(p90 float64) EfficiencyDistribution {
		return EfficiencyDistribution{Sample: 6, Median: &p90, P90: &p90}
	}
	previous := EfficiencyPeriod{
		CompletedWorks: 5, LeadTimeSeconds: distribution(100),
		ReviewFirstPass: rate(0.7), VerifyFirstPass: rate(0.8), FinalDeadEnds: rate(0.2),
	}
	improved := EfficiencyPeriod{
		CompletedWorks: 6, LeadTimeSeconds: distribution(90),
		ReviewFirstPass: rate(0.8), VerifyFirstPass: rate(0.9), FinalDeadEnds: rate(0.1),
	}
	if got := compareEfficiencyPeriods(improved, previous); got != "improved" {
		t.Fatalf("improved comparison = %q", got)
	}
	degraded := EfficiencyPeriod{
		CompletedWorks: 5, LeadTimeSeconds: distribution(120),
		ReviewFirstPass: rate(0.6), VerifyFirstPass: rate(0.7), FinalDeadEnds: rate(0.3),
	}
	if got := compareEfficiencyPeriods(degraded, EfficiencyPeriod{
		CompletedWorks: 6, LeadTimeSeconds: distribution(100),
		ReviewFirstPass: rate(0.7), VerifyFirstPass: rate(0.8), FinalDeadEnds: rate(0.2),
	}); got != "degraded" {
		t.Fatalf("degraded comparison = %q", got)
	}
	improved.CompletedWorks = efficiencyMinimumSample - 1
	if got := compareEfficiencyPeriods(improved, previous); got != "low_data" {
		t.Fatalf("small improved sample = %q", got)
	}
}

func TestEfficiencyDistributionUsesNearestRankP90(t *testing.T) {
	distribution := efficiencyDistribution([]float64{10, 1, 5, 4, 8, 3, 9, 2, 7, 6})
	if distribution.Median == nil || *distribution.Median != 5.5 || distribution.P90 == nil || *distribution.P90 != 9 {
		t.Fatalf("distribution = %#v", distribution)
	}
}

func TestHTTPEfficiencyReturnsBothFixedComparablePeriods(t *testing.T) {
	fixture := newHTTPFixture(t)
	t.Setenv("FACTORY_DATA_HOME", t.TempDir())
	response := fixture.request(http.MethodGet, "/api/v1/metrics/efficiency", "", "", nil)
	requireStatus(t, response, http.StatusOK)
	summary := decodeResponse[EfficiencySummary](t, response)
	if summary.MinimumSample != efficiencyMinimumSample || len(summary.Periods) != 2 ||
		summary.Periods[metricsWindow24Hours].Assessment != "low_data" ||
		summary.Periods[metricsWindow7Days].Assessment != "low_data" {
		t.Fatalf("efficiency response = %#v", summary)
	}
	day := summary.Periods[metricsWindow24Hours].Current
	if len(day.TimeShares) != 10 || day.UnclassifiedThreshold != efficiencyUnclassifiedThreshold ||
		day.TimeShares[len(day.TimeShares)-1].Key != "unclassified" ||
		day.TimeShares[len(day.TimeShares)-1].Definition == "" {
		t.Fatalf("efficiency diagnostics contract = %#v", day)
	}

	response = fixture.request(http.MethodGet, "/api/v1/metrics/efficiency?window=all", "", "", nil)
	requireStatus(t, response, http.StatusBadRequest)
	response.Body.Close()
}

func TestEfficiencyFactColumnsAreIndexed(t *testing.T) {
	store := newTestStore(t)
	for _, name := range []string{"tasks_efficiency_created_title", "attempts_efficiency_execution_order"} {
		var count int
		if err := store.db.QueryRow(`SELECT COUNT(*) FROM sqlite_master WHERE type = 'index' AND name = ?`, name).Scan(&count); err != nil {
			t.Fatal(err)
		}
		if count != 1 {
			t.Fatalf("efficiency index %q count = %d", name, count)
		}
	}
}

func seedEfficiencyTask(t *testing.T, store *Store, repositoryID, id, title, state string, createdAt, startedAt, updatedAt time.Time) string {
	t.Helper()
	taskID := "task-" + id
	return seedEfficiencyTaskWithID(t, store, repositoryID, taskID, id, title, state, createdAt, startedAt, updatedAt)
}

func seedEfficiencyTaskWithID(t *testing.T, store *Store, repositoryID, taskID, id, title, state string, createdAt, startedAt, updatedAt time.Time) string {
	t.Helper()
	executionID := "execution-" + id
	if _, err := store.db.Exec(`
		INSERT INTO tasks(id, request_key, title, description, repository_id, timeout_seconds, created_at)
		VALUES (?, ?, ?, 'efficiency fixture', ?, 3600, ?)
	`, taskID, "request-"+id, title, repositoryID, createdAt.UnixMilli()); err != nil {
		t.Fatal(err)
	}
	if _, err := store.db.Exec(`
		INSERT INTO executions(id, task_id, assigned_worker_id, required_runtime, state,
			cancellation_requested, retry_count, created_at, updated_at)
		VALUES (?, ?, 'efficiency-worker', 'codex', ?, 0, 0, ?, ?)
	`, executionID, taskID, state, createdAt.UnixMilli(), updatedAt.UnixMilli()); err != nil {
		t.Fatal(err)
	}
	if _, err := store.db.Exec(`
		INSERT INTO attempts(id, execution_id, worker_id, attempt_number, state, lease_digest,
			lease_expires_at, started_at, completed_at, created_at)
		VALUES (?, ?, 'efficiency-worker', 1, ?, X'00', ?, ?, ?, ?)
	`, "attempt-"+id, executionID, state, updatedAt.UnixMilli(), startedAt.UnixMilli(), updatedAt.UnixMilli(), createdAt.UnixMilli()); err != nil {
		t.Fatal(err)
	}
	return taskID
}

func linkEfficiencySchedule(t *testing.T, store *Store, repositoryID, taskID, suffix, contextText string, now time.Time) {
	t.Helper()
	workflow := createTestWorkflow(t, store, suffix+"-workflow", "Schedule "+suffix, "Inspect pipelines.")
	detail, _, err := store.CreateAutomation(context.Background(), protocol.CreateAutomationRequest{
		RequestKey: suffix + "-automation", Title: "Schedule " + suffix,
		WorkflowID: workflow.Workflow.ID, RepositoryID: repositoryID,
		Context: contextText, TimeoutSeconds: 3600,
		Trigger: protocol.AutomationTrigger{Type: protocol.AutomationTriggerSchedule, Cron: "0 * * * *", Timezone: "UTC"},
	})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := store.db.Exec(`
		INSERT INTO automation_occurrences(
			id, automation_id, automation_version, automation_title, workflow_revision_id,
			repository_id, repository_identity, context, timeout_seconds, state,
			task_request_key, task_id, task_id_snapshot, created_at, updated_at
		) VALUES (?, ?, ?, ?, ?, ?, 'github.com/example/product', ?, 3600,
			'dispatched', ?, ?, ?, ?, ?)
	`, "occurrence-"+suffix, detail.Automation.ID, detail.Automation.Version, detail.Automation.Title,
		workflow.Workflow.CurrentRevision.ID, repositoryID, contextText,
		"occurrence-task-"+suffix, taskID, taskID,
		now.Add(-80*time.Minute).UnixMilli(), now.Add(-60*time.Minute).UnixMilli()); err != nil {
		t.Fatal(err)
	}
}

func writeJSONLines(t *testing.T, path string, values []any) {
	t.Helper()
	file, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	encoder := json.NewEncoder(file)
	for _, value := range values {
		if err := encoder.Encode(value); err != nil {
			file.Close()
			t.Fatal(err)
		}
	}
	if err := file.Close(); err != nil {
		t.Fatal(err)
	}
}
