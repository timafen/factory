package controlplane

import (
	"bytes"
	"context"
	"database/sql"
	"errors"
	"fmt"
	"net/http"
	"os/exec"
	"strings"
	"time"

	"github.com/owainlewis/factory/internal/protocol"
)

type projectCommandRunner interface {
	Run(context.Context, string, []string, []string) error
	Output(context.Context, string, []string, []string) ([]byte, error)
	StartDurable(context.Context, string, string, []string) error
	DurableStatus(context.Context, string) (projectDurableStatus, error)
}

type projectDurableStatus struct {
	Running bool
	Success bool
}
type execProjectCommandRunner struct{}

func projectAdapterBaselineEnvironment() []string {
	return []string{
		"LANG=C.UTF-8",
		"LC_ALL=C.UTF-8",
		"PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
	}
}

func (execProjectCommandRunner) Run(ctx context.Context, executable string, args, environment []string) error {
	command := exec.CommandContext(ctx, executable, args...)
	command.Env = append(projectAdapterBaselineEnvironment(), environment...)
	return command.Run()
}

func (execProjectCommandRunner) Output(ctx context.Context, executable string, args, environment []string) ([]byte, error) {
	command := exec.CommandContext(ctx, executable, args...)
	command.Env = append(projectAdapterBaselineEnvironment(), environment...)
	return command.Output()
}

func (execProjectCommandRunner) StartDurable(ctx context.Context, unit, executable string, args []string) error {
	if executable != "/usr/local/bin/fx" || len(args) != 3 || args[0] != "factory" || args[1] != "release" || !validCommitSHA(args[2]) {
		return errors.New("durable broker accepts only a fixed Factory release invocation")
	}
	command := exec.CommandContext(ctx, "/usr/local/bin/fx", "factory", "release-job", args[2], unit)
	command.Env = projectAdapterBaselineEnvironment()
	return command.Run()
}

func (execProjectCommandRunner) DurableStatus(ctx context.Context, unit string) (projectDurableStatus, error) {
	command := exec.CommandContext(ctx, "/usr/local/bin/fx", "factory", "release-job-status", unit)
	command.Env = projectAdapterBaselineEnvironment()
	output, err := command.Output()
	if err != nil {
		return projectDurableStatus{}, err
	}
	switch strings.TrimSpace(string(output)) {
	case "running":
		return projectDurableStatus{Running: true}, nil
	case "succeeded":
		return projectDurableStatus{Success: true}, nil
	case "failed":
		return projectDurableStatus{}, nil
	default:
		return projectDurableStatus{}, errors.New("durable release broker returned an unknown status")
	}
}

type projectHealthChecker interface {
	Check(context.Context, string, []string) error
}
type httpProjectHealthChecker struct{ client *http.Client }

func (checker httpProjectHealthChecker) Check(ctx context.Context, rawURL string, allowedHosts []string) error {
	parsed, err := exactHTTPSURL(rawURL)
	if err != nil {
		return errors.New("health URL is not an exact HTTPS URL")
	}
	allowed := false
	for _, host := range allowedHosts {
		if parsedHostname(parsed) == host {
			allowed = true
			break
		}
	}
	if !allowed {
		return errors.New("health URL host is outside the exact project web host allowlist")
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, rawURL, nil)
	if err != nil {
		return err
	}
	response, err := checker.client.Do(request)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return fmt.Errorf("health check returned HTTP %d", response.StatusCode)
	}
	return nil
}

type adapterInvocation struct {
	executable        string
	args              []string
	automaticRollback bool
}

func projectAdapterInvocation(adapter, sha string) (adapterInvocation, error) {
	switch adapter {
	case "fx-factory-release":
		return adapterInvocation{executable: "/usr/local/bin/fx", args: []string{"factory", "release", sha}}, nil
	case "fx-factory-rollback":
		return adapterInvocation{executable: "/usr/local/bin/fx", args: []string{"factory", "rollback"}}, nil
	case "tarser-staging-deploy-release":
		return adapterInvocation{executable: "/usr/local/bin/fx", args: []string{"staging", "release", sha}, automaticRollback: true}, nil
	case "tarser-staging-auto-rollback":
		return adapterInvocation{executable: "/usr/local/bin/fx", args: []string{"staging", "rollback"}}, nil
	default:
		return adapterInvocation{}, invalid("adapter_not_allowed", "adapter is not present in the v1 server registry")
	}
}

func runProjectAdapter(ctx context.Context, runner projectCommandRunner, adapter, sha string, environment []string) (bool, error) {
	invocation, err := projectAdapterInvocation(adapter, sha)
	if err != nil {
		return false, err
	}
	return invocation.automaticRollback, runner.Run(ctx, invocation.executable, invocation.args, environment)
}

func tarserStagingReleaseState(ctx context.Context, runner projectCommandRunner) (string, error) {
	output, err := runner.Output(ctx, "/usr/bin/readlink", []string{"-f", "/srv/automation-ebay-operations/staging/current"}, nil)
	if err != nil {
		return "", err
	}
	state := string(bytes.TrimSpace(output))
	if state == "" {
		return "", errors.New("staging release state is empty")
	}
	return state, nil
}

func environmentFor(project protocol.Project, name string) (protocol.ProjectEnvironment, error) {
	for _, environment := range project.Environments {
		if environment.Name == name {
			return environment, nil
		}
	}
	return protocol.ProjectEnvironment{}, ErrNotFound
}

func (s *Store) beginProjectOperation(ctx context.Context, project protocol.Project, environment, kind, sha string, ownerConfirmed bool) (protocol.ProjectOperation, error) {
	id, err := newID()
	if err != nil {
		return protocol.ProjectOperation{}, unavailable(err)
	}
	now := s.now()
	operation := protocol.ProjectOperation{ID: id, ProjectID: project.ID, Environment: environment, Kind: kind, CommitSHA: sha, Status: "running", Message: "operation started", OwnerConfirmed: ownerConfirmed, CreatedAt: now, UpdatedAt: now}
	_, err = s.db.ExecContext(ctx, `INSERT INTO project_operations(id,project_id,environment,kind,commit_sha,status,message,owner_confirmed,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)`, id, project.ID, environment, kind, sha, operation.Status, operation.Message, boolInt(ownerConfirmed), now.UnixMilli(), now.UnixMilli())
	if err != nil {
		return protocol.ProjectOperation{}, unavailable(err)
	}
	return operation, nil
}

func (s *Store) finishProjectOperation(ctx context.Context, operation protocol.ProjectOperation, status, message string) (protocol.ProjectOperation, error) {
	operation.Status, operation.Message, operation.UpdatedAt = status, message, s.now()
	_, err := s.db.ExecContext(ctx, `UPDATE project_operations SET status=?,message=?,updated_at=? WHERE id=?`, status, message, operation.UpdatedAt.UnixMilli(), operation.ID)
	if err != nil {
		return operation, unavailable(err)
	}
	return operation, nil
}

func factoryProjectOperationUnit(operationID string) string {
	return "factory-project-release-" + strings.ReplaceAll(operationID, "-", "")
}

func (s *Store) ProjectOperation(ctx context.Context, runner projectCommandRunner, projectID, operationID string) (protocol.ProjectOperation, error) {
	var operation protocol.ProjectOperation
	var ownerConfirmed int
	var createdAt, updatedAt int64
	err := s.db.QueryRowContext(ctx, `SELECT id,project_id,environment,kind,commit_sha,status,message,owner_confirmed,created_at,updated_at FROM project_operations WHERE id=? AND project_id=?`, operationID, projectID).Scan(
		&operation.ID, &operation.ProjectID, &operation.Environment, &operation.Kind, &operation.CommitSHA,
		&operation.Status, &operation.Message, &ownerConfirmed, &createdAt, &updatedAt,
	)
	if errors.Is(err, sql.ErrNoRows) {
		return protocol.ProjectOperation{}, ErrNotFound
	}
	if err != nil {
		return protocol.ProjectOperation{}, unavailable(err)
	}
	operation.OwnerConfirmed = ownerConfirmed != 0
	operation.CreatedAt = fromMillis(createdAt)
	operation.UpdatedAt = fromMillis(updatedAt)
	if operation.Status != "running" || operation.Kind != "release" {
		return operation, nil
	}
	project, err := s.Project(ctx, projectID)
	if err != nil {
		return operation, err
	}
	environment, err := environmentFor(project, operation.Environment)
	if err != nil || environment.ReleaseAdapter != "fx-factory-release" {
		return operation, err
	}
	status, err := runner.DurableStatus(ctx, factoryProjectOperationUnit(operation.ID))
	if err != nil {
		return operation, unavailable(err)
	}
	if status.Running {
		return operation, nil
	}
	if status.Success {
		return s.finishProjectOperation(ctx, operation, "succeeded", "external self-release completed and survived the server restart")
	}
	return s.finishProjectOperation(ctx, operation, "rollback_failed", "external self-release failed; inspect the durable unit for rollback evidence")
}

func (s *Store) ReconcileProjectOperations(ctx context.Context, runner projectCommandRunner) error {
	rows, err := s.db.QueryContext(ctx, `
		SELECT operation.project_id, operation.id
		FROM project_operations operation
		JOIN project_environments environment
		  ON environment.project_id=operation.project_id AND environment.name=operation.environment
		WHERE operation.status='running' AND operation.kind='release'
		  AND environment.release_adapter='fx-factory-release'
	`)
	if err != nil {
		return unavailable(err)
	}
	defer rows.Close()
	type pendingOperation struct{ projectID, operationID string }
	var pending []pendingOperation
	for rows.Next() {
		var value pendingOperation
		if err := rows.Scan(&value.projectID, &value.operationID); err != nil {
			return unavailable(err)
		}
		pending = append(pending, value)
	}
	if err := rows.Err(); err != nil {
		return unavailable(err)
	}
	var reconcileErr error
	for _, value := range pending {
		_, err := s.ProjectOperation(ctx, runner, value.projectID, value.operationID)
		reconcileErr = errors.Join(reconcileErr, err)
	}
	return reconcileErr
}

func (s *Store) RunProjectOperation(ctx context.Context, runner projectCommandRunner, health projectHealthChecker, projectID, environmentName, kind string, request protocol.ProjectOperationRequest) (protocol.ProjectOperation, error) {
	if !validCommitSHA(request.CommitSHA) {
		return protocol.ProjectOperation{}, invalid("invalid_commit_sha", "commit_sha must be a lowercase 40 or 64 character hexadecimal SHA")
	}
	if kind != "release" && kind != "rollback" {
		return protocol.ProjectOperation{}, invalid("invalid_operation", "operation must be release or rollback")
	}
	project, err := s.Project(ctx, projectID)
	if err != nil {
		return protocol.ProjectOperation{}, err
	}
	environment, err := environmentFor(project, environmentName)
	if err != nil {
		return protocol.ProjectOperation{}, err
	}
	if environment.Name == "production" {
		return protocol.ProjectOperation{}, conflict("production_confirmation_required", "production remains blocked until a separate server-side owner approval is implemented")
	}
	readiness, err := s.ProjectReadiness(ctx, projectID, environmentName)
	if err != nil {
		return protocol.ProjectOperation{}, err
	}
	if !readiness.Ready || readiness.CommitSHA != request.CommitSHA {
		return protocol.ProjectOperation{}, conflict("project_not_ready", "all readiness gates and secrets must pass on the requested commit")
	}
	_, processEnvironment, err := s.resolveProjectSecretEnvironment(project, environmentName)
	if err != nil {
		return protocol.ProjectOperation{}, conflict("project_not_ready", "required secrets changed after readiness was checked")
	}
	adapter := environment.ReleaseAdapter
	if kind == "rollback" {
		adapter = environment.RollbackAdapter
	}
	invocation, err := projectAdapterInvocation(adapter, request.CommitSHA)
	if err != nil {
		return protocol.ProjectOperation{}, err
	}
	rollbackState := ""
	if kind == "release" && invocation.automaticRollback {
		rollbackState, err = tarserStagingReleaseState(ctx, runner)
		if err != nil {
			return protocol.ProjectOperation{}, conflict("rollback_confirmation_unavailable", "release is blocked because the current staging release cannot be verified")
		}
	}
	operation, err := s.beginProjectOperation(ctx, project, environmentName, kind, request.CommitSHA, request.OwnerConfirmed)
	if err != nil {
		return operation, err
	}
	if kind == "release" && adapter == "fx-factory-release" {
		if err := runner.StartDurable(ctx, factoryProjectOperationUnit(operation.ID), "/usr/local/bin/fx", []string{"factory", "release", request.CommitSHA}); err != nil {
			return s.finishProjectOperation(ctx, operation, "rollback_failed", "external self-release could not be started")
		}
		operation.Message = "external self-release started; poll this operation after the server restart"
		if _, err := s.db.ExecContext(ctx, `UPDATE project_operations SET message=?,updated_at=? WHERE id=?`, operation.Message, s.now().UnixMilli(), operation.ID); err != nil {
			return operation, unavailable(err)
		}
		operation.UpdatedAt = s.now()
		return operation, nil
	}
	automatic, runErr := runProjectAdapter(ctx, runner, adapter, request.CommitSHA, processEnvironment)
	if runErr != nil {
		if kind == "release" {
			if automatic {
				currentState, stateErr := tarserStagingReleaseState(ctx, runner)
				if stateErr == nil && currentState == rollbackState {
					return s.finishProjectOperation(ctx, operation, "release_failed_rolled_back", "release failed; automatic rollback to the previous release was verified")
				}
				return s.finishProjectOperation(ctx, operation, "rollback_failed", "release failed; automatic rollback could not be verified")
			}
			_, rollbackErr := runProjectAdapter(ctx, runner, environment.RollbackAdapter, request.CommitSHA, processEnvironment)
			if rollbackErr == nil {
				return s.finishProjectOperation(ctx, operation, "release_failed_rolled_back", "release failed; named rollback completed")
			}
			return s.finishProjectOperation(ctx, operation, "rollback_failed", "release and named rollback failed")
		}
		return s.finishProjectOperation(ctx, operation, "rollback_failed", "named rollback failed")
	}
	if kind == "release" {
		if err := health.Check(ctx, environment.HealthURL, environment.WebHosts); err != nil {
			_, rollbackErr := runProjectAdapter(ctx, runner, environment.RollbackAdapter, request.CommitSHA, processEnvironment)
			if rollbackErr != nil {
				return s.finishProjectOperation(ctx, operation, "rollback_failed", "health check and named rollback failed")
			}
			if automatic {
				currentState, stateErr := tarserStagingReleaseState(ctx, runner)
				if stateErr != nil || currentState != rollbackState {
					return s.finishProjectOperation(ctx, operation, "rollback_failed", "health check failed; rollback to the previous release could not be verified")
				}
			}
			return s.finishProjectOperation(ctx, operation, "health_failed_rolled_back", "health check failed; named rollback completed")
		}
	}
	label := "Release"
	if kind == "rollback" {
		label = "Rollback"
	}
	return s.finishProjectOperation(ctx, operation, "succeeded", label+" completed and health was verified")
}

func defaultProjectHealthChecker() projectHealthChecker {
	return httpProjectHealthChecker{client: &http.Client{Timeout: 30 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return errors.New("health redirects are forbidden") }}}
}
