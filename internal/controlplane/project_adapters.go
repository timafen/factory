package controlplane

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os/exec"
	"strings"
	"time"

	"github.com/owainlewis/factory/internal/protocol"
)

type projectCommandRunner interface {
	Output(context.Context, string, []string, []string) ([]byte, error)
	StartDurable(context.Context, string, string, []string) error
	DurableStatus(context.Context, string) (projectDurableStatus, error)
}

type projectDurableStatus struct {
	Running bool
	Outcome string
}

const defaultProjectReleaseBrokerSocket = "/run/factory/project-release-broker.sock"

type execProjectCommandRunner struct{ releaseBrokerSocket string }

type projectReleaseBrokerRequest struct {
	OperationID string `json:"operation_id"`
	Adapter     string `json:"adapter"`
	CommitSHA   string `json:"commit_sha"`
}

type projectReleaseBrokerResponse struct {
	Status string `json:"status"`
}

type projectReleaseBrokerHTTPError struct {
	method string
	path   string
	status int
}

func (err *projectReleaseBrokerHTTPError) Error() string {
	return fmt.Sprintf("external release broker operation %s %s returned HTTP %d", err.method, err.path, err.status)
}

func projectBrokerDefinitelyRejected(err error) bool {
	var responseErr *projectReleaseBrokerHTTPError
	return errors.As(err, &responseErr) && responseErr.status >= 400 && responseErr.status < 500
}

func projectAdapterBaselineEnvironment() []string {
	return []string{
		"LANG=C.UTF-8",
		"LC_ALL=C.UTF-8",
		"PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
	}
}

func (execProjectCommandRunner) Run(ctx context.Context, executable string, args, environment []string) error {
	if executable == "/usr/local/bin/fx" {
		return errors.New("privileged fx operations must use the external release broker")
	}
	command := exec.CommandContext(ctx, executable, args...)
	command.Env = append(projectAdapterBaselineEnvironment(), environment...)
	return command.Run()
}

func (execProjectCommandRunner) Output(ctx context.Context, executable string, args, environment []string) ([]byte, error) {
	command := exec.CommandContext(ctx, executable, args...)
	command.Env = append(projectAdapterBaselineEnvironment(), environment...)
	return command.Output()
}

func (runner execProjectCommandRunner) StartDurable(ctx context.Context, unit, executable string, args []string) error {
	adapter, sha, ok := projectBrokerAdapter(executable, args)
	if !ok {
		return errors.New("durable broker accepts only fixed project release and rollback invocations")
	}
	return runner.callReleaseBroker(ctx, http.MethodPost, "/v1/operations", projectReleaseBrokerRequest{OperationID: unit, Adapter: adapter, CommitSHA: sha}, nil)
}

func (runner execProjectCommandRunner) DurableStatus(ctx context.Context, unit string) (projectDurableStatus, error) {
	var response projectReleaseBrokerResponse
	if err := runner.callReleaseBroker(ctx, http.MethodGet, "/v1/operations/"+url.PathEscape(unit), nil, &response); err != nil {
		return projectDurableStatus{}, err
	}
	return parseProjectReleaseBrokerStatus(response.Status)
}

func projectBrokerAdapter(executable string, args []string) (adapter, sha string, ok bool) {
	if executable != "/usr/local/bin/fx" {
		return "", "", false
	}
	switch {
	case len(args) == 3 && args[0] == "factory" && args[1] == "release" && validCommitSHA(args[2]):
		return "fx-factory-release", args[2], true
	case len(args) == 2 && args[0] == "factory" && args[1] == "rollback":
		return "fx-factory-rollback", strings.Repeat("0", 40), true
	case len(args) == 3 && args[0] == "staging" && args[1] == "release" && validCommitSHA(args[2]):
		return "tarser-staging-deploy-release", args[2], true
	case len(args) == 2 && args[0] == "staging" && args[1] == "rollback":
		return "tarser-staging-auto-rollback", strings.Repeat("0", 40), true
	default:
		return "", "", false
	}
}

func parseProjectReleaseBrokerStatus(status string) (projectDurableStatus, error) {
	switch status {
	case "running":
		return projectDurableStatus{Running: true}, nil
	case "succeeded":
		return projectDurableStatus{Outcome: "succeeded"}, nil
	case "release_failed_rolled_back":
		return projectDurableStatus{Outcome: "release_failed_rolled_back"}, nil
	case "rollback_failed":
		return projectDurableStatus{Outcome: "rollback_failed"}, nil
	default:
		return projectDurableStatus{}, errors.New("durable release broker returned an unknown or ambiguous status")
	}
}

func (runner execProjectCommandRunner) callReleaseBroker(ctx context.Context, method, path string, input, output any) error {
	socket := runner.releaseBrokerSocket
	if socket == "" {
		socket = defaultProjectReleaseBrokerSocket
	}
	var body bytes.Buffer
	if input != nil {
		if err := json.NewEncoder(&body).Encode(input); err != nil {
			return fmt.Errorf("encode external release broker request: %w", err)
		}
	}
	transport := &http.Transport{DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
		return (&net.Dialer{}).DialContext(ctx, "unix", socket)
	}}
	defer transport.CloseIdleConnections()
	client := &http.Client{Transport: transport, Timeout: 10 * time.Second}
	request, err := http.NewRequestWithContext(ctx, method, "http://release-broker"+path, &body)
	if err != nil {
		return fmt.Errorf("create external release broker request: %w", err)
	}
	request.Header.Set("Content-Type", "application/json")
	response, err := client.Do(request)
	if err != nil {
		return fmt.Errorf("external release broker operation %s %s is unavailable: %w", method, path, err)
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return &projectReleaseBrokerHTTPError{method: method, path: path, status: response.StatusCode}
	}
	if output != nil {
		decoder := json.NewDecoder(io.LimitReader(response.Body, protocol.MaxBodyBytes+1))
		decoder.DisallowUnknownFields()
		if err := decoder.Decode(output); err != nil {
			return fmt.Errorf("decode external release broker response: %w", err)
		}
	}
	return nil
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
	executable string
	args       []string
}

func projectAdapterInvocation(adapter, sha string) (adapterInvocation, error) {
	switch adapter {
	case "fx-factory-release":
		return adapterInvocation{executable: "/usr/local/bin/fx", args: []string{"factory", "release", sha}}, nil
	case "fx-factory-rollback":
		return adapterInvocation{executable: "/usr/local/bin/fx", args: []string{"factory", "rollback"}}, nil
	case "tarser-staging-deploy-release":
		return adapterInvocation{executable: "/usr/local/bin/fx", args: []string{"staging", "release", sha}}, nil
	case "tarser-staging-auto-rollback":
		return adapterInvocation{executable: "/usr/local/bin/fx", args: []string{"staging", "rollback"}}, nil
	default:
		return adapterInvocation{}, invalid("adapter_not_allowed", "adapter is not present in the v1 server registry")
	}
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
		if isSQLiteConstraint(err) {
			return protocol.ProjectOperation{}, conflict("project_operation_running", "another release or rollback is already running for this project environment")
		}
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

func (s *Store) updateRunningProjectOperation(ctx context.Context, operation protocol.ProjectOperation, message string) (protocol.ProjectOperation, error) {
	operation.Message, operation.UpdatedAt = message, s.now()
	_, err := s.db.ExecContext(ctx, `UPDATE project_operations SET message=?,updated_at=? WHERE id=? AND status='running'`, message, operation.UpdatedAt.UnixMilli(), operation.ID)
	if err != nil {
		return operation, unavailable(err)
	}
	return operation, nil
}

func factoryProjectOperationUnit(operationID string) string {
	return "factory-project-release-" + strings.ReplaceAll(operationID, "-", "")
}

func projectRollbackOperationUnit(operationID string) string {
	return factoryProjectOperationUnit(operationID) + "-rollback"
}

const projectBrokerRollbackStarted = "external health check failed; privileged rollback broker started"

func (s *Store) ProjectOperation(ctx context.Context, runner projectCommandRunner, health projectHealthChecker, projectID, operationID string) (protocol.ProjectOperation, error) {
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
	if operation.Status != "running" {
		return operation, nil
	}
	project, err := s.Project(ctx, projectID)
	if err != nil {
		return operation, err
	}
	environment, err := environmentFor(project, operation.Environment)
	if err != nil {
		return operation, err
	}
	unit := factoryProjectOperationUnit(operation.ID)
	if operation.Message == projectBrokerRollbackStarted {
		unit = projectRollbackOperationUnit(operation.ID)
	}
	status, err := runner.DurableStatus(ctx, unit)
	if err != nil {
		return operation, unavailable(err)
	}
	if status.Running {
		return operation, nil
	}
	if operation.Message == projectBrokerRollbackStarted {
		if status.Outcome != "succeeded" {
			return s.finishProjectOperation(ctx, operation, "rollback_failed", "external health check and privileged rollback failed")
		}
		if err := health.Check(ctx, environment.HealthURL, environment.WebHosts); err != nil {
			return s.finishProjectOperation(ctx, operation, "rollback_failed", "privileged rollback completed but restored health could not be verified")
		}
		return s.finishProjectOperation(ctx, operation, "health_failed_rolled_back", "external health check failed; privileged rollback and restored health were verified")
	}
	switch status.Outcome {
	case "succeeded":
		if err := health.Check(ctx, environment.HealthURL, environment.WebHosts); err == nil {
			return s.finishProjectOperation(ctx, operation, "succeeded", "privileged operation completed and health was verified")
		}
		if operation.Kind == "rollback" {
			return s.finishProjectOperation(ctx, operation, "rollback_failed", "privileged rollback completed but health could not be verified")
		}
		rollback, invocationErr := projectAdapterInvocation(environment.RollbackAdapter, operation.CommitSHA)
		if invocationErr != nil {
			return s.finishProjectOperation(ctx, operation, "rollback_failed", "external health check failed and the rollback adapter is unavailable")
		}
		operation, err = s.updateRunningProjectOperation(ctx, operation, projectBrokerRollbackStarted)
		if err != nil {
			return operation, err
		}
		if err := runner.StartDurable(ctx, projectRollbackOperationUnit(operation.ID), rollback.executable, rollback.args); err != nil {
			if projectBrokerDefinitelyRejected(err) {
				return s.finishProjectOperation(ctx, operation, "rollback_failed", "external health check failed and the privileged rollback broker rejected the operation")
			}
			return operation, nil
		}
		return operation, nil
	case "release_failed_rolled_back":
		if err := health.Check(ctx, environment.HealthURL, environment.WebHosts); err != nil {
			return s.finishProjectOperation(ctx, operation, "rollback_failed", "Выпуск не удался; Factory сообщила об автоматическом откате, но health-проверка не подтвердила восстановление")
		}
		return s.finishProjectOperation(ctx, operation, "release_failed_rolled_back", "Выпуск не удался; Factory автоматически вернула предыдущую версию, восстановление подтверждено health-проверкой")
	case "rollback_failed":
		return s.finishProjectOperation(ctx, operation, "rollback_failed", "privileged operation failed without a verified healthy rollback")
	default:
		return operation, unavailable(errors.New("privileged release broker completed without an exact rollback outcome"))
	}
}

func (s *Store) ReconcileProjectOperations(ctx context.Context, runner projectCommandRunner, health projectHealthChecker) error {
	rows, err := s.db.QueryContext(ctx, `
		SELECT operation.project_id, operation.id
		FROM project_operations operation
		JOIN project_environments environment
		  ON environment.project_id=operation.project_id AND environment.name=operation.environment
		WHERE operation.status='running'
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
		_, err := s.ProjectOperation(ctx, runner, health, value.projectID, value.operationID)
		reconcileErr = errors.Join(reconcileErr, err)
	}
	return reconcileErr
}

func RunProjectOperationReconciler(ctx context.Context, store *Store, logger interface {
	Warn(string, ...any)
}) {
	ticker := time.NewTicker(2 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if err := store.ReconcileProjectOperations(ctx, execProjectCommandRunner{}, defaultProjectHealthChecker()); err != nil && ctx.Err() == nil {
				logger.Warn("project_operation_reconciliation_failed", "error_class", "privileged_broker_status")
			}
		}
	}
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
	operation, err := s.beginProjectOperation(ctx, project, environmentName, kind, request.CommitSHA, false)
	if err != nil {
		return operation, err
	}
	_ = processEnvironment // readiness still proves the declared root-owned secret file before broker dispatch.
	if err := runner.StartDurable(ctx, factoryProjectOperationUnit(operation.ID), invocation.executable, invocation.args); err != nil {
		if projectBrokerDefinitelyRejected(err) {
			return s.finishProjectOperation(ctx, operation, "rollback_failed", "privileged broker rejected the operation before it started")
		}
		return s.updateRunningProjectOperation(ctx, operation, "privileged broker POST result is unknown; poll before starting another operation")
	}
	return s.updateRunningProjectOperation(ctx, operation, "privileged release broker accepted the operation")
}

func defaultProjectHealthChecker() projectHealthChecker {
	return httpProjectHealthChecker{client: &http.Client{Timeout: 30 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return errors.New("health redirects are forbidden") }}}
}
