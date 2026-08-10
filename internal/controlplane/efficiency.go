package controlplane

import (
	"bufio"
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"math"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"
)

const (
	efficiencyMinimumSample = 5
	efficiencyDeadEndGrace  = 10 * time.Minute
	efficiencyLegacyTime    = "2006-01-02 15:04:05"
)

var efficiencyStageTitle = regexp.MustCompile(`^\[auto\]\s*\[\d+/\d+\s+([^\]]+)\]\s*(.+)$`)

var efficiencyStages = []string{"Triage", "Specification", "Implement + Test", "Review", "Verify"}

type EfficiencySummary struct {
	GeneratedAt                 time.Time                             `json:"generated_at"`
	MinimumSample               int                                   `json:"minimum_sample"`
	ReleaseObservationStartedAt *time.Time                            `json:"release_observation_started_at,omitempty"`
	Periods                     map[string]EfficiencyPeriodComparison `json:"periods"`
}

type EfficiencyPeriodComparison struct {
	Assessment string           `json:"assessment"`
	Current    EfficiencyPeriod `json:"current"`
	Previous   EfficiencyPeriod `json:"previous"`
}

type EfficiencyPeriod struct {
	StartedAt           time.Time                   `json:"started_at"`
	EndedAt             time.Time                   `json:"ended_at"`
	CompletedWorks      int                         `json:"completed_works"`
	ProductStageTasks   int                         `json:"product_stage_tasks"`
	LeadTimeSeconds     EfficiencyDistribution      `json:"lead_time_seconds"`
	TimeShares          []EfficiencyTimeShare       `json:"time_shares"`
	ReviewFirstPass     EfficiencyRate              `json:"review_first_pass"`
	VerifyFirstPass     EfficiencyRate              `json:"verify_first_pass"`
	Rounds              EfficiencyDistribution      `json:"rounds"`
	FinalDeadEnds       EfficiencyRate              `json:"final_dead_ends"`
	AutomaticRecoveries int                         `json:"automatic_recoveries"`
	ReleaseFailures     int                         `json:"release_failures"`
	Rollbacks           int                         `json:"rollbacks"`
	Excluded            EfficiencyExcludedBreakdown `json:"excluded"`
}

type EfficiencyDistribution struct {
	Sample int      `json:"sample"`
	Median *float64 `json:"median"`
	P90    *float64 `json:"p90"`
}

type EfficiencyRate struct {
	Count int      `json:"count"`
	Total int      `json:"total"`
	Rate  *float64 `json:"rate"`
}

type EfficiencyTimeShare struct {
	Key                string   `json:"key"`
	Seconds            float64  `json:"seconds"`
	DenominatorSeconds float64  `json:"denominator_seconds"`
	Share              *float64 `json:"share"`
}

type EfficiencyExcludedBreakdown struct {
	Patrol    int `json:"patrol"`
	Scheduled int `json:"scheduled"`
	Helper    int `json:"helper"`
	Other     int `json:"other"`
	Total     int `json:"total"`
}

type efficiencyTask struct {
	id               string
	base             string
	stage            string
	title            string
	repositoryID     string
	state            string
	createdAt        time.Time
	updatedAt        time.Time
	automationLinked bool
	scheduled        bool
	automationName   string
	automationText   string
	attempts         []efficiencyAttempt
}

type efficiencyAttempt struct {
	startedAt   *time.Time
	completedAt *time.Time
}

type efficiencyMerge struct {
	taskID string
	at     time.Time
}

type efficiencyReleaseEvent struct {
	ID       string `json:"id"`
	At       string `json:"at"`
	Kind     string `json:"kind"`
	Rollback bool   `json:"rollback"`
}

type efficiencyWork struct {
	mergeAt time.Time
	tasks   []*efficiencyTask
}

type efficiencyInterval struct {
	start time.Time
	end   time.Time
	key   string
}

func (s *Store) Efficiency(ctx context.Context) (EfficiencySummary, error) {
	now := s.now().UTC()
	var releaseObservationStartedAt *time.Time
	var migrationAppliedAt sql.NullInt64
	if err := s.db.QueryRowContext(ctx, `SELECT applied_at FROM schema_migrations WHERE version = 18`).Scan(&migrationAppliedAt); err != nil && !errors.Is(err, sql.ErrNoRows) {
		return EfficiencySummary{}, unavailable(err)
	}
	if migrationAppliedAt.Valid {
		value := time.UnixMilli(migrationAppliedAt.Int64).UTC()
		releaseObservationStartedAt = &value
	}
	tasks, err := s.loadEfficiencyTasks(ctx)
	if err != nil {
		return EfficiencySummary{}, unavailable(err)
	}
	merges, err := loadEfficiencyMerges()
	if err != nil {
		return EfficiencySummary{}, unavailable(err)
	}
	releases, err := loadEfficiencyReleaseEvents()
	if err != nil {
		return EfficiencySummary{}, unavailable(err)
	}
	works, tails := buildEfficiencyWorks(tasks, merges)
	periods := make(map[string]EfficiencyPeriodComparison, 2)
	for key, duration := range map[string]time.Duration{
		metricsWindow24Hours: 24 * time.Hour,
		metricsWindow7Days:   7 * 24 * time.Hour,
	} {
		start := now.Add(-duration)
		previousStart := start.Add(-duration)
		current := summarizeEfficiencyPeriod(start, now, tasks, works, tails, releases)
		previous := summarizeEfficiencyPeriod(previousStart, start, tasks, works, tails, releases)
		periods[key] = EfficiencyPeriodComparison{
			Assessment: compareEfficiencyPeriods(current, previous),
			Current:    current, Previous: previous,
		}
	}
	return EfficiencySummary{
		GeneratedAt: now, MinimumSample: efficiencyMinimumSample,
		ReleaseObservationStartedAt: releaseObservationStartedAt, Periods: periods,
	}, nil
}

func (s *Store) loadEfficiencyTasks(ctx context.Context) ([]*efficiencyTask, error) {
	rows, err := s.db.QueryContext(ctx, `
		SELECT task.id, task.title, task.repository_id, execution.state,
		       execution.created_at, execution.updated_at,
		       CASE WHEN COUNT(automation.id) > 0 THEN 1 ELSE 0 END,
		       CASE WHEN SUM(CASE WHEN automation.trigger_type = 'schedule' THEN 1 ELSE 0 END) > 0 THEN 1 ELSE 0 END,
		       COALESCE(GROUP_CONCAT(automation.title, ' '), ''),
		       COALESCE(GROUP_CONCAT(automation.context, ' '), '')
		FROM tasks task
		JOIN executions execution ON execution.task_id = task.id
		LEFT JOIN automation_occurrences occurrence ON occurrence.task_id = task.id
		LEFT JOIN automations automation ON automation.id = occurrence.automation_id
		GROUP BY task.id, task.title, task.repository_id, execution.state,
		         execution.created_at, execution.updated_at
		ORDER BY execution.created_at, task.id
	`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	tasks := make([]*efficiencyTask, 0)
	byID := make(map[string]*efficiencyTask)
	for rows.Next() {
		var task efficiencyTask
		var createdAt, updatedAt int64
		var automationLinked, scheduled int
		if err := rows.Scan(&task.id, &task.title, &task.repositoryID, &task.state,
			&createdAt, &updatedAt, &automationLinked, &scheduled, &task.automationName,
			&task.automationText); err != nil {
			return nil, err
		}
		task.automationLinked = automationLinked != 0
		task.scheduled = scheduled != 0
		task.createdAt = time.UnixMilli(createdAt).UTC()
		task.updatedAt = time.UnixMilli(updatedAt).UTC()
		if match := efficiencyStageTitle.FindStringSubmatch(task.title); match != nil {
			task.stage, task.base = strings.TrimSpace(match[1]), strings.TrimSpace(match[2])
		}
		tasks = append(tasks, &task)
		byID[task.id] = &task
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	attemptRows, err := s.db.QueryContext(ctx, `
		SELECT execution.task_id, attempt.started_at, attempt.completed_at
		FROM attempts attempt
		JOIN executions execution ON execution.id = attempt.execution_id
		JOIN tasks task ON task.id = execution.task_id
		WHERE task.title LIKE '[auto] [%'
		ORDER BY execution.task_id, attempt.attempt_number
	`)
	if err != nil {
		return nil, err
	}
	defer attemptRows.Close()
	for attemptRows.Next() {
		var taskID string
		var startedAt, completedAt sql.NullInt64
		if err := attemptRows.Scan(&taskID, &startedAt, &completedAt); err != nil {
			return nil, err
		}
		task := byID[taskID]
		if task == nil {
			continue
		}
		attempt := efficiencyAttempt{}
		if startedAt.Valid {
			value := time.UnixMilli(startedAt.Int64).UTC()
			attempt.startedAt = &value
		}
		if completedAt.Valid {
			value := time.UnixMilli(completedAt.Int64).UTC()
			attempt.completedAt = &value
		}
		task.attempts = append(task.attempts, attempt)
	}
	return tasks, attemptRows.Err()
}

func efficiencyDataHome() string {
	home := os.Getenv("FACTORY_DATA_HOME")
	if home == "" {
		home = "/opt/factory-data"
	}
	return home
}

func loadEfficiencyMerges() ([]efficiencyMerge, error) {
	path := filepath.Join(efficiencyDataHome(), "pilot", "merges.jsonl")
	file, err := os.Open(path)
	if errors.Is(err, os.ErrNotExist) {
		return []efficiencyMerge{}, nil
	}
	if err != nil {
		return nil, err
	}
	defer file.Close()
	seen := make(map[string]struct{})
	merges := make([]efficiencyMerge, 0)
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		var raw struct {
			TaskID string `json:"task_id"`
			At     string `json:"at"`
		}
		if json.Unmarshal(scanner.Bytes(), &raw) != nil || raw.TaskID == "" {
			continue
		}
		at, err := parseEfficiencyMergeTime(raw.At)
		if err != nil {
			continue
		}
		if _, duplicate := seen[raw.TaskID]; duplicate {
			continue
		}
		seen[raw.TaskID] = struct{}{}
		merges = append(merges, efficiencyMerge{taskID: raw.TaskID, at: at.UTC()})
	}
	if err := scanner.Err(); err != nil {
		return nil, err
	}
	sort.Slice(merges, func(i, j int) bool { return merges[i].at.Before(merges[j].at) })
	return merges, nil
}

func parseEfficiencyMergeTime(value string) (time.Time, error) {
	if at, err := time.Parse(time.RFC3339, value); err == nil {
		return at.UTC(), nil
	}
	at, err := time.ParseInLocation(efficiencyLegacyTime, value, time.Local)
	if err != nil {
		return time.Time{}, err
	}
	return at.UTC(), nil
}

func loadEfficiencyReleaseEvents() ([]efficiencyReleaseEvent, error) {
	path := filepath.Join(efficiencyDataHome(), "pilot", "release-events.jsonl")
	file, err := os.Open(path)
	if errors.Is(err, os.ErrNotExist) {
		return []efficiencyReleaseEvent{}, nil
	}
	if err != nil {
		return nil, err
	}
	defer file.Close()
	events := make([]efficiencyReleaseEvent, 0)
	seen := make(map[string]struct{})
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		var event efficiencyReleaseEvent
		if json.Unmarshal(scanner.Bytes(), &event) != nil || event.At == "" {
			continue
		}
		if event.ID != "" {
			if _, duplicate := seen[event.ID]; duplicate {
				continue
			}
			seen[event.ID] = struct{}{}
		}
		events = append(events, event)
	}
	return events, scanner.Err()
}

func isProductEfficiencyTask(task *efficiencyTask) bool {
	if task.base == "" || task.stage == "" || task.automationLinked {
		return false
	}
	for _, stage := range efficiencyStages {
		if task.stage == stage {
			return true
		}
	}
	return false
}

func efficiencyWorkKey(task *efficiencyTask) string {
	return task.repositoryID + "\x00" + task.base
}

func buildEfficiencyWorks(tasks []*efficiencyTask, merges []efficiencyMerge) ([]efficiencyWork, map[string][]*efficiencyTask) {
	byID := make(map[string]*efficiencyTask)
	groups := make(map[string][]*efficiencyTask)
	for _, task := range tasks {
		if !isProductEfficiencyTask(task) {
			continue
		}
		byID[task.id] = task
		key := efficiencyWorkKey(task)
		groups[key] = append(groups[key], task)
	}
	boundaries := make(map[string]time.Time)
	works := make([]efficiencyWork, 0, len(merges))
	for _, merge := range merges {
		finalTask := byID[merge.taskID]
		if finalTask == nil || merge.at.Before(finalTask.createdAt) {
			continue
		}
		key := efficiencyWorkKey(finalTask)
		boundary := boundaries[key]
		workTasks := make([]*efficiencyTask, 0)
		for _, task := range groups[key] {
			if !boundary.IsZero() && !task.createdAt.After(boundary) {
				continue
			}
			if !task.createdAt.After(merge.at) {
				workTasks = append(workTasks, task)
			}
		}
		if len(workTasks) == 0 {
			continue
		}
		works = append(works, efficiencyWork{mergeAt: merge.at, tasks: workTasks})
		boundaries[key] = merge.at
	}
	tails := make(map[string][]*efficiencyTask)
	for key, group := range groups {
		boundary := boundaries[key]
		for _, task := range group {
			if boundary.IsZero() || task.createdAt.After(boundary) {
				tails[key] = append(tails[key], task)
			}
		}
	}
	return works, tails
}

func summarizeEfficiencyPeriod(start, end time.Time, allTasks []*efficiencyTask, works []efficiencyWork, tails map[string][]*efficiencyTask, releases []efficiencyReleaseEvent) EfficiencyPeriod {
	period := EfficiencyPeriod{StartedAt: start, EndedAt: end}
	selected := make([]efficiencyWork, 0)
	for _, work := range works {
		if inEfficiencyWindow(work.mergeAt, start, end) {
			selected = append(selected, work)
		}
	}
	period.CompletedWorks = len(selected)
	leadValues := make([]float64, 0, len(selected))
	roundValues := make([]float64, 0, len(selected))
	shareSeconds := make(map[string]float64)
	var shareDenominator float64
	for _, work := range selected {
		first := work.tasks[0].createdAt
		for _, task := range work.tasks[1:] {
			if task.createdAt.Before(first) {
				first = task.createdAt
			}
		}
		lead := math.Max(0, work.mergeAt.Sub(first).Seconds())
		leadValues = append(leadValues, lead)
		shareDenominator += lead
		for key, seconds := range efficiencyWorkShares(work, first) {
			shareSeconds[key] += seconds
		}

		stages := make(map[string][]*efficiencyTask)
		for _, task := range work.tasks {
			stages[task.stage] = append(stages[task.stage], task)
		}
		reviews := stages["Review"]
		if len(reviews) > 0 {
			period.ReviewFirstPass.Total++
			if len(reviews) == 1 && reviews[0].state == "succeeded" {
				period.ReviewFirstPass.Count++
			}
		}
		verifies := stages["Verify"]
		if len(verifies) > 0 {
			period.VerifyFirstPass.Total++
			if len(verifies) == 1 && verifies[0].state == "succeeded" {
				period.VerifyFirstPass.Count++
			}
		}
		rounds := 0
		for _, stage := range []string{"Implement + Test", "Review", "Verify"} {
			if len(stages[stage]) > rounds {
				rounds = len(stages[stage])
			}
		}
		if rounds > 0 {
			roundValues = append(roundValues, float64(rounds))
		}
	}
	period.AutomaticRecoveries = countEfficiencyRecoveriesInWindow(works, tails, start, end)
	period.LeadTimeSeconds = efficiencyDistribution(leadValues)
	period.Rounds = efficiencyDistribution(roundValues)
	period.ReviewFirstPass = efficiencyRate(period.ReviewFirstPass.Count, period.ReviewFirstPass.Total)
	period.VerifyFirstPass = efficiencyRate(period.VerifyFirstPass.Count, period.VerifyFirstPass.Total)
	period.TimeShares = efficiencyTimeShares(shareSeconds, shareDenominator)

	deadEnds := 0
	for _, tail := range tails {
		if len(tail) == 0 || hasLiveEfficiencyTask(tail) {
			continue
		}
		latest := tail[len(tail)-1]
		for _, task := range tail[1:] {
			if task.updatedAt.After(latest.updatedAt) {
				latest = task
			}
		}
		if inEfficiencyWindow(latest.updatedAt, start, end) &&
			!latest.updatedAt.After(end.Add(-efficiencyDeadEndGrace)) &&
			isTerminalEfficiencyState(latest.state) {
			deadEnds++
		}
	}
	period.FinalDeadEnds = efficiencyRate(deadEnds, deadEnds+period.CompletedWorks)

	for _, task := range allTasks {
		if !inEfficiencyWindow(task.updatedAt, start, end) || !isTerminalEfficiencyState(task.state) {
			continue
		}
		if isProductEfficiencyTask(task) {
			period.ProductStageTasks++
			continue
		}
		classifyExcludedEfficiencyTask(task, &period.Excluded)
	}
	period.Excluded.Total = period.Excluded.Patrol + period.Excluded.Scheduled + period.Excluded.Helper + period.Excluded.Other

	for _, event := range releases {
		at, err := time.Parse(time.RFC3339, event.At)
		if err != nil || !inEfficiencyWindow(at, start, end) {
			continue
		}
		if event.Kind == "failed_release" {
			period.ReleaseFailures++
		}
		if event.Kind == "rollback" || event.Rollback {
			period.Rollbacks++
		}
	}
	return period
}

func efficiencyWorkShares(work efficiencyWork, workStart time.Time) map[string]float64 {
	intervals := make([]efficiencyInterval, 0)
	for _, task := range work.tasks {
		end := task.updatedAt
		if end.After(work.mergeAt) {
			end = work.mergeAt
		}
		if !end.After(task.createdAt) {
			continue
		}
		cursor := task.createdAt
		if len(task.attempts) == 0 {
			intervals = append(intervals, efficiencyInterval{start: cursor, end: end, key: "queue"})
			continue
		}
		startedAny := false
		for _, attempt := range task.attempts {
			if attempt.startedAt == nil {
				continue
			}
			startedAny = true
			started := maxEfficiencyTime(*attempt.startedAt, task.createdAt)
			if started.After(end) {
				break
			}
			if started.After(cursor) {
				intervals = append(intervals, efficiencyInterval{start: cursor, end: started, key: "queue"})
			}
			completed := end
			if attempt.completedAt != nil && attempt.completedAt.Before(completed) {
				completed = *attempt.completedAt
			}
			if completed.After(started) {
				intervals = append(intervals, efficiencyInterval{start: started, end: completed, key: task.stage})
			}
			if completed.After(cursor) {
				cursor = completed
			}
		}
		if !startedAny {
			intervals = append(intervals, efficiencyInterval{start: cursor, end: end, key: "queue"})
		}
	}
	boundaries := []time.Time{workStart, work.mergeAt}
	for _, interval := range intervals {
		boundaries = append(boundaries, interval.start, interval.end)
	}
	sort.Slice(boundaries, func(i, j int) bool { return boundaries[i].Before(boundaries[j]) })
	seconds := make(map[string]float64)
	for index := 1; index < len(boundaries); index++ {
		left, right := boundaries[index-1], boundaries[index]
		if !right.After(left) || left.Before(workStart) || right.After(work.mergeAt) {
			continue
		}
		key := "other"
		for _, interval := range intervals {
			if !interval.start.After(left) && !interval.end.Before(right) {
				if interval.key != "queue" || key == "other" {
					key = interval.key
				}
			}
		}
		seconds[key] += right.Sub(left).Seconds()
	}
	return seconds
}

func efficiencyTimeShares(seconds map[string]float64, denominator float64) []EfficiencyTimeShare {
	keys := []string{"queue", "Triage", "Specification", "Implement + Test", "Review", "Verify", "other"}
	shares := make([]EfficiencyTimeShare, 0, len(keys))
	for _, key := range keys {
		entry := EfficiencyTimeShare{Key: key, Seconds: seconds[key], DenominatorSeconds: denominator}
		if denominator > 0 {
			value := seconds[key] / denominator
			entry.Share = &value
		}
		shares = append(shares, entry)
	}
	return shares
}

func countEfficiencyRecoveriesInWindow(works []efficiencyWork, tails map[string][]*efficiencyTask, start, end time.Time) int {
	countSegment := func(tasks []*efficiencyTask) int {
		lastByStage := make(map[string]*efficiencyTask)
		count := 0
		for _, task := range tasks {
			if previous := lastByStage[task.stage]; previous != nil &&
				(previous.state == "failed" || previous.state == "cancelled") &&
				inEfficiencyWindow(task.createdAt, start, end) {
				count++
			}
			lastByStage[task.stage] = task
		}
		return count
	}
	count := 0
	for _, work := range works {
		count += countSegment(work.tasks)
	}
	for _, tail := range tails {
		count += countSegment(tail)
	}
	return count
}

func classifyExcludedEfficiencyTask(task *efficiencyTask, excluded *EfficiencyExcludedBreakdown) {
	lower := strings.ToLower(task.title + " " + task.automationName + " " + task.automationText)
	if task.scheduled && strings.Contains(lower, "factory pipeline patrol") {
		excluded.Patrol++
	} else if task.scheduled {
		excluded.Scheduled++
	} else if strings.Contains(lower, "helper") || strings.HasPrefix(lower, "[epic-plan]") {
		excluded.Helper++
	} else {
		excluded.Other++
	}
}

func compareEfficiencyPeriods(current, previous EfficiencyPeriod) string {
	if current.CompletedWorks < efficiencyMinimumSample || previous.CompletedWorks < efficiencyMinimumSample {
		return "low_data"
	}
	improved, degraded := false, false
	compareHigherBetter := func(a, b float64) {
		if a > b {
			improved = true
		} else if a < b {
			degraded = true
		}
	}
	compareLowerBetter := func(a, b float64) {
		if a < b*0.95 {
			improved = true
		} else if a > b*1.05 {
			degraded = true
		}
	}
	compareHigherBetter(float64(current.CompletedWorks), float64(previous.CompletedWorks))
	if current.LeadTimeSeconds.P90 != nil && previous.LeadTimeSeconds.P90 != nil {
		compareLowerBetter(*current.LeadTimeSeconds.P90, *previous.LeadTimeSeconds.P90)
	}
	for _, rates := range [][2]EfficiencyRate{
		{current.ReviewFirstPass, previous.ReviewFirstPass},
		{current.VerifyFirstPass, previous.VerifyFirstPass},
	} {
		if rates[0].Rate != nil && rates[1].Rate != nil {
			compareHigherBetter(*rates[0].Rate, *rates[1].Rate)
		}
	}
	if current.FinalDeadEnds.Rate != nil && previous.FinalDeadEnds.Rate != nil {
		compareLowerBetter(*current.FinalDeadEnds.Rate, *previous.FinalDeadEnds.Rate)
	}
	if degraded && improved {
		return "mixed"
	}
	if degraded {
		return "degraded"
	}
	if improved {
		return "improved"
	}
	return "stable"
}

func efficiencyDistribution(values []float64) EfficiencyDistribution {
	distribution := EfficiencyDistribution{Sample: len(values)}
	if len(values) == 0 {
		return distribution
	}
	sort.Float64s(values)
	median := values[len(values)/2]
	if len(values)%2 == 0 {
		median = (values[len(values)/2-1] + values[len(values)/2]) / 2
	}
	p90 := values[int(math.Ceil(float64(len(values))*0.9))-1]
	distribution.Median, distribution.P90 = &median, &p90
	return distribution
}

func efficiencyRate(count, total int) EfficiencyRate {
	rate := EfficiencyRate{Count: count, Total: total}
	if total > 0 {
		value := float64(count) / float64(total)
		rate.Rate = &value
	}
	return rate
}

func hasLiveEfficiencyTask(tasks []*efficiencyTask) bool {
	for _, task := range tasks {
		if !isTerminalEfficiencyState(task.state) {
			return true
		}
	}
	return false
}

func isTerminalEfficiencyState(state string) bool {
	return state == "succeeded" || state == "failed" || state == "cancelled"
}

func inEfficiencyWindow(value, start, end time.Time) bool {
	return !value.Before(start) && value.Before(end)
}

func maxEfficiencyTime(a, b time.Time) time.Time {
	if a.After(b) {
		return a
	}
	return b
}
