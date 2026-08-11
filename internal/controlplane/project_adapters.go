package controlplane

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"net/http"
	"os/exec"
	"time"

	"github.com/owainlewis/factory/internal/protocol"
)

type projectCommandRunner interface {
	Run(context.Context, string, []string, []string) error
	Output(context.Context, string, []string, []string) ([]byte, error)
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

type projectHealthChecker interface {
	Check(context.Context, string) error
}
type httpProjectHealthChecker struct{ client *http.Client }

func (checker httpProjectHealthChecker) Check(ctx context.Context, rawURL string) error {
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
		if err := health.Check(ctx, environment.HealthURL); err != nil {
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
