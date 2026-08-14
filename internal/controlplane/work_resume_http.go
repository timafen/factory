package controlplane

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"github.com/owainlewis/factory/internal/protocol"
)

var resumeStageTitle = regexp.MustCompile(`^\[auto\]\s*\[(\d+)/(\d+)\s+([^\]]+)\]\s*(.*)$`)

type resumeWorkRequest struct {
	Title string `json:"title"`
}

type resumeWorkResponse struct {
	Task    protocol.Task `json:"task"`
	Stage   string        `json:"stage"`
	Resumed bool          `json:"resumed"`
}

type resumedStageTask struct {
	protocol.Task
	stage string
}

// resumeWorkMetadata is written by Pilot when a work deliberately starts after
// the first pipeline stage.  It is provenance, rather than an inference from
// a missing task: a low-complexity work that starts at Implement must not be
// sent back to a Triage task that was never required.
type resumeWorkMetadata struct {
	StartStage string   `json:"start_stage"`
	Skipped    []string `json:"skipped"`
}

// resumeWork turns an owner pause into one concrete queued task.  The mutex is
// deliberately at the API boundary: two browser clicks must inspect exactly
// the same history and share one deterministic request key.
func (a *API) resumeWork(w http.ResponseWriter, r *http.Request) {
	if a.pilotConfig == nil {
		writeError(w, &ServiceError{Code: "pilot_config_unavailable", Message: "pilot settings are not configured", Status: http.StatusServiceUnavailable})
		return
	}
	if !prepareMutation(w, r, protocol.MaxBodyBytes) {
		return
	}
	var input resumeWorkRequest
	if !decodeJSON(w, r, &input) {
		return
	}
	base := strings.TrimSpace(input.Title)
	if base == "" || len([]rune(base)) > 160 {
		writeError(w, invalid("invalid_work_title", "work title is required and limited to 160 Unicode characters"))
		return
	}

	a.resumeMu.Lock()
	defer a.resumeMu.Unlock()
	response, err := a.resumePausedWork(r.Context(), base)
	if err != nil {
		writeError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, response)
}

func (a *API) resumePausedWork(ctx context.Context, base string) (resumeWorkResponse, error) {
	settingsResponse, err := a.pilotConfig.Read()
	if err != nil {
		return resumeWorkResponse{}, err
	}
	settings := settingsResponse.Settings
	pausedAt := pausedPipelineIndex(settings.StoppedPipelines, base)

	tasks, err := a.pipelineTasks(ctx, base)
	if err != nil {
		return resumeWorkResponse{}, err
	}
	if len(tasks) == 0 {
		return resumeWorkResponse{}, &ServiceError{Code: "work_not_found", Message: "paused work has no canonical pipeline history", Status: http.StatusNotFound}
	}
	if live := firstLivePipelineTask(tasks); live != nil {
		if pausedAt >= 0 {
			settings.StoppedPipelines = removePipeline(settings.StoppedPipelines, pausedAt)
			if _, err := a.pilotConfig.Write(settingsResponse.Version, settings); err != nil {
				return resumeWorkResponse{}, err
			}
		}
		return resumeWorkResponse{Task: live.Task, Stage: live.stage, Resumed: false}, nil
	}
	if pausedAt < 0 {
		return resumeWorkResponse{}, conflict("work_not_paused", "this work is not owner-paused")
	}

	metadata := readResumeWorkMetadata(base)
	target, source := resumeTarget(tasks, settings.Stages, metadata)
	if target == "" || source == nil {
		if pausedAt >= 0 {
			settings.StoppedPipelines = removePipeline(settings.StoppedPipelines, pausedAt)
			if _, err := a.pilotConfig.Write(settingsResponse.Version, settings); err != nil {
				return resumeWorkResponse{}, err
			}
		}
		return resumeWorkResponse{}, conflict("pipeline_completed", "all required pipeline stages have already completed")
	}
	worker, err := a.resumeWorker(ctx, settings, target, source.RepositoryID)
	if err != nil {
		return resumeWorkResponse{}, err
	}
	revisionID, err := a.resumeWorkflowRevision(ctx, target)
	if err != nil {
		return resumeWorkResponse{}, err
	}
	detail, err := a.store.Task(ctx, source.ID)
	if err != nil {
		return resumeWorkResponse{}, err
	}
	if detail.Context == "" || detail.Workflow == nil {
		return resumeWorkResponse{}, conflict("resume_history_incomplete", "the paused stage has no reusable workflow context")
	}
	key := resumeRequestKey(base, source.ID, target)
	created, _, err := a.store.CreateTask(ctx, protocol.CreateTaskRequest{
		RequestKey:                 key,
		Title:                      fmt.Sprintf("[auto] [%d/%d %s] %s", stageIndex(settings.Stages, target)+1, len(settings.Stages), target, base),
		Context:                    resumeContext(detail.Context, target),
		ContextProvided:            true,
		WorkerID:                   worker.ID,
		RepositoryID:               source.RepositoryID,
		TimeoutSeconds:             int(settings.TimeoutSeconds),
		WorkflowRevisionID:         revisionID,
		WorkflowRevisionIDProvided: true,
		ParentTaskID:               source.ID,
	})
	if err != nil {
		return resumeWorkResponse{}, err
	}

	// The task was accepted with a stable request key before the pause is
	// removed. If writing settings fails, the pause remains visible and a retry
	// reuses this exact task rather than creating another one.
	settings.StoppedPipelines = removePipeline(settings.StoppedPipelines, pausedAt)
	if _, err := a.pilotConfig.Write(settingsResponse.Version, settings); err != nil {
		return resumeWorkResponse{}, err
	}
	return resumeWorkResponse{Task: created.Task, Stage: target, Resumed: true}, nil
}

func (a *API) pipelineTasks(ctx context.Context, base string) ([]resumedStageTask, error) {
	rows, err := a.store.db.QueryContext(ctx, `
		SELECT t.id, t.request_key, t.title, t.repository_id, t.timeout_seconds,
		       e.assigned_worker_id, e.state, t.read_only, t.created_at,
		       t.work_id, t.parent_task_id, t.correction_kind,
		       CASE WHEN COUNT(a.id) > 0 THEN 1 ELSE 0 END,
		       CASE WHEN SUM(CASE WHEN a.trigger_type = 'schedule' THEN 1 ELSE 0 END) > 0 THEN 1 ELSE 0 END,
		       COALESCE(GROUP_CONCAT(a.title, ' '), ''), COALESCE(GROUP_CONCAT(a.context, ' '), '')
		FROM tasks t JOIN executions e ON e.task_id=t.id
		LEFT JOIN automation_occurrences o ON o.task_id = t.id
		LEFT JOIN automations a ON a.id = o.automation_id
		GROUP BY t.id, t.request_key, t.title, t.repository_id, t.timeout_seconds,
		         e.assigned_worker_id, e.state, t.read_only, t.created_at,
		         t.work_id, t.parent_task_id, t.correction_kind
		ORDER BY t.created_at, t.id`)
	if err != nil {
		return nil, unavailable(err)
	}
	defer rows.Close()
	var result []resumedStageTask
	for rows.Next() {
		task, err := scanTask(rows, false)
		if err != nil {
			return nil, unavailable(err)
		}
		match := resumeStageTitle.FindStringSubmatch(task.Title)
		if match == nil || strings.TrimSpace(match[4]) != base {
			continue
		}
		result = append(result, resumedStageTask{Task: task, stage: strings.TrimSpace(match[3])})
	}
	if err := rows.Err(); err != nil {
		return nil, unavailable(err)
	}
	return result, nil
}

func firstLivePipelineTask(tasks []resumedStageTask) *resumedStageTask {
	for i := range tasks {
		if tasks[i].State == "queued" || tasks[i].State == "running" || tasks[i].State == "preparing" {
			return &tasks[i]
		}
	}
	return nil
}

// resumeTarget returns the first required stage that has not actually passed.
// Execution success is enough for ordinary stages, but it is not evidence that
// a Review or Verify passed: Pilot writes their decision to verdicts/<task>.json
// and only action=advance clears those gates.  A stop at either gate returns to
// implementation, because the verdict means the implementation needs work.
func resumeTarget(tasks []resumedStageTask, stages []protocol.PilotStage, metadata resumeWorkMetadata) (string, *resumedStageTask) {
	latest := map[string]*resumedStageTask{}
	for i := range tasks {
		latest[tasks[i].stage] = &tasks[i]
	}
	required := resumeRequiredStages(stages, metadata)
	implementation := ""
	for _, route := range stages {
		if route.Workflow == "Implement + Test" {
			implementation = route.Workflow
			break
		}
	}
	implementationTask := latest[implementation]
	reviewTask := latest["Review"]
	var source *resumedStageTask
	for _, route := range required {
		current := latest[route.Workflow]
		if current == nil {
			return route.Workflow, source
		}
		if current.State != "succeeded" {
			return route.Workflow, current
		}
		if route.Workflow == "Review" || route.Workflow == "Verify" {
			action := resumeVerdictAction(current.ID)
			if action == "stop" && implementation != "" {
				// A later implementation is the response to this old stop. It
				// must be reviewed again, rather than being sent back through an
				// already completed rework task forever.
				if route.Workflow == "Review" && implementationTask != nil && implementationTask.CreatedAt.After(current.CreatedAt) {
					return route.Workflow, implementationTask
				}
				// Verify can only be retried after a fresh Review. If it already
				// has an advancing review after this stop, the missing task is a
				// new Verify; otherwise the first unfinished gate is Review.
				if route.Workflow == "Verify" && implementationTask != nil && implementationTask.CreatedAt.After(current.CreatedAt) {
					if reviewTask != nil && reviewTask.CreatedAt.After(current.CreatedAt) {
						return route.Workflow, reviewTask
					}
					return "Review", implementationTask
				}
				return implementation, current
			}
			if action != "advance" {
				return route.Workflow, current
			}
		}
		source = current
	}
	return "", nil
}

func resumeRequiredStages(stages []protocol.PilotStage, metadata resumeWorkMetadata) []protocol.PilotStage {
	start := 0
	if want := strings.TrimSpace(metadata.StartStage); want != "" {
		for i, route := range stages {
			if route.Workflow == want {
				start = i
				break
			}
		}
	}
	skipped := map[string]bool{}
	for _, stage := range metadata.Skipped {
		skipped[strings.TrimSpace(stage)] = true
	}
	required := make([]protocol.PilotStage, 0, len(stages)-start)
	for i, route := range stages {
		if i >= start && !skipped[route.Workflow] {
			required = append(required, route)
		}
	}
	return required
}

func readResumeWorkMetadata(base string) resumeWorkMetadata {
	data, err := os.ReadFile(worksPath())
	if err != nil {
		return resumeWorkMetadata{}
	}
	works := map[string]resumeWorkMetadata{}
	if json.Unmarshal(data, &works) != nil {
		return resumeWorkMetadata{}
	}
	return works[base]
}

func resumeVerdictAction(taskID string) string {
	data, err := os.ReadFile(filepath.Join(verdictsDir(), taskID+".json"))
	if err != nil {
		return ""
	}
	var verdict struct {
		Action string `json:"action"`
	}
	if json.Unmarshal(data, &verdict) != nil {
		return ""
	}
	return verdict.Action
}

func (a *API) resumeWorker(ctx context.Context, settings protocol.PilotSettings, stage, repositoryID string) (protocol.Worker, error) {
	workers, err := a.store.Workers(ctx)
	if err != nil {
		return protocol.Worker{}, err
	}
	byName := map[string]protocol.Worker{}
	for _, worker := range workers {
		byName[worker.Name] = worker
	}
	for _, route := range settings.Stages {
		if route.Workflow != stage {
			continue
		}
		for _, name := range []string{route.Workers.Medium, route.Workers.High, route.Workers.Low} {
			worker := byName[name]
			if worker.ID == "" || !worker.Online || worker.Health != "healthy" {
				continue
			}
			for _, repo := range worker.Repositories {
				if repo.ID == repositoryID && repo.RetainedCount < 10 {
					return worker, nil
				}
			}
		}
	}
	return protocol.Worker{}, conflict("resume_worker_unavailable", "no healthy configured worker can resume this repository")
}

func (a *API) resumeWorkflowRevision(ctx context.Context, stage string) (string, error) {
	page, err := a.store.Workflows(ctx, protocol.WorkflowPageRequest{Limit: protocol.MaxWorkflowPageSize, Title: stage})
	if err != nil {
		return "", err
	}
	for _, workflow := range page.Workflows {
		if workflow.Enabled && workflow.CurrentRevision.Title == stage {
			return workflow.CurrentRevision.ID, nil
		}
	}
	return "", conflict("resume_workflow_unavailable", "the required workflow is not enabled")
}

func pausedPipelineIndex(values []string, base string) int {
	for i, value := range values {
		if strings.EqualFold(strings.TrimSpace(value), base) {
			return i
		}
	}
	return -1
}
func removePipeline(values []string, index int) []string {
	return append(append([]string{}, values[:index]...), values[index+1:]...)
}
func stageIndex(stages []protocol.PilotStage, want string) int {
	for i, stage := range stages {
		if stage.Workflow == want {
			return i
		}
	}
	return 0
}
func resumeRequestKey(base, taskID, stage string) string {
	sum := sha256.Sum256([]byte(base + "\x00" + taskID + "\x00" + stage))
	return "resume:" + hex.EncodeToString(sum[:])
}
func resumeContext(context, stage string) string {
	prefix := "Продолжение остановленной владельцем работы. Выполни этап «" + stage + "»; обязательные Review и Verify не пропускай.\n\n"
	return (prefix + context)[:min(len(prefix)+len(context), 60000)]
}
