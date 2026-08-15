package controlplane

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"runtime"
	"strings"
	"testing"

	"github.com/owainlewis/factory/internal/protocol"
)

type recordedProjectCommand struct {
	executable  string
	args        []string
	environment []string
	output      bool
	unit        string
	durable     bool
}
type fakeProjectRunner struct {
	calls                   []recordedProjectCommand
	failFirst               bool
	runCalls                int
	outputs                 []string
	outputCalls             int
	durableStartResponseErr error
	durableStatus           projectDurableStatus
}

func (runner *fakeProjectRunner) Run(_ context.Context, executable string, args, environment []string) error {
	runner.calls = append(runner.calls, recordedProjectCommand{executable: executable, args: append([]string(nil), args...), environment: append([]string(nil), environment...)})
	runner.runCalls++
	if runner.failFirst && runner.runCalls == 1 {
		return errors.New("release failed")
	}
	return nil
}

func (runner *fakeProjectRunner) Output(_ context.Context, executable string, args, environment []string) ([]byte, error) {
	runner.calls = append(runner.calls, recordedProjectCommand{executable: executable, args: append([]string(nil), args...), environment: append([]string(nil), environment...), output: true})
	if runner.outputCalls >= len(runner.outputs) {
		return nil, errors.New("unexpected output call")
	}
	output := runner.outputs[runner.outputCalls]
	runner.outputCalls++
	return []byte(output), nil
}

func (runner *fakeProjectRunner) StartDurable(_ context.Context, unit, executable string, args []string) error {
	runner.calls = append(runner.calls, recordedProjectCommand{executable: executable, args: append([]string(nil), args...), unit: unit, durable: true})
	runner.runCalls++
	if runner.durableStartResponseErr != nil {
		return runner.durableStartResponseErr
	}
	if runner.failFirst && runner.runCalls == 1 {
		return errors.New("durable start failed")
	}
	return nil
}

func (runner *fakeProjectRunner) DurableStatus(context.Context, string) (projectDurableStatus, error) {
	return runner.durableStatus, nil
}

type fakeHealth struct{ err error }

func (health fakeHealth) Check(context.Context, string, []string) error { return health.err }

type sequenceHealth struct {
	errors []error
	calls  int
}

func (health *sequenceHealth) Check(context.Context, string, []string) error {
	var err error
	if health.calls < len(health.errors) {
		err = health.errors[health.calls]
	}
	health.calls++
	return err
}

type recordingRoundTripper struct{ called bool }

func (transport *recordingRoundTripper) RoundTrip(*http.Request) (*http.Response, error) {
	transport.called = true
	return nil, errors.New("network should not be reached")
}

func TestProjectHealthCheckEnforcesExactWebHostAllowlist(t *testing.T) {
	transport := &recordingRoundTripper{}
	checker := httpProjectHealthChecker{client: &http.Client{Transport: transport}}
	err := checker.Check(context.Background(), "https://blocked.example/health", []string{"factory.timafen.com"})
	if err == nil || !strings.Contains(err.Error(), "outside the exact project web host allowlist") {
		t.Fatalf("unexpected allowlist error: %v", err)
	}
	if transport.called {
		t.Fatal("health checker reached the network for a host outside web_hosts")
	}
}

func TestProjectAdapterRegistryUsesFixedArgvWithoutShell(t *testing.T) {
	invocation, err := projectAdapterInvocation("fx-factory-release", projectSHA)
	if err != nil || invocation.executable != "/usr/local/bin/fx" || !reflect.DeepEqual(invocation.args, []string{"factory", "release", projectSHA}) {
		t.Fatalf("fixed invocation=%+v err=%v", invocation, err)
	}
	if _, err := projectAdapterInvocation("sh -c anything", projectSHA); errorCode(err) != "adapter_not_allowed" {
		t.Fatalf("unknown adapter error = %v", err)
	}
	if err := (execProjectCommandRunner{}).Run(context.Background(), "/usr/local/bin/fx", []string{"factory", "rollback"}, nil); err == nil {
		t.Fatal("control-plane was allowed to execute privileged fx directly")
	}
}

func TestProjectAdapterProcessDoesNotInheritControlPlaneSecrets(t *testing.T) {
	t.Setenv("CONTROL_PLANE_SECRET_SHOULD_NOT_LEAK", "control-plane-secret")
	output, err := (execProjectCommandRunner{}).Output(context.Background(), "/usr/bin/env", nil, []string{"GITHUB_TOKEN=project-secret"})
	if err != nil {
		t.Fatal(err)
	}
	environment := string(output)
	if strings.Contains(environment, "CONTROL_PLANE_SECRET_SHOULD_NOT_LEAK") || strings.Contains(environment, "control-plane-secret") {
		t.Fatal("adapter inherited an unrelated control-plane secret")
	}
	for _, expected := range []string{"LANG=C.UTF-8", "LC_ALL=C.UTF-8", "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", "GITHUB_TOKEN=project-secret"} {
		if !strings.Contains(environment, expected) {
			t.Fatalf("adapter environment is missing %q: %s", expected, environment)
		}
	}
}

func createTarserProject(t *testing.T, store *Store) protocol.Project {
	t.Helper()
	input := factoryProjectRequest()
	input.Name = "Tarser staging"
	input.RemoteIdentity = "github.com/timafen/tarser-operations"
	input.ProjectType = protocol.ProjectTypeTarserOperationsStaging
	input.Environments[0].URL = "https://staging-automation.tarser.net"
	input.Environments[0].HealthURL = "https://staging-automation.tarser.net/ops/health/"
	input.Environments[0].ReleaseAdapter = "tarser-staging-deploy-release"
	input.Environments[0].RollbackAdapter = "tarser-staging-auto-rollback"
	input.Environments[0].WebHosts = []string{"staging-automation.tarser.net"}
	project, created, err := store.CreateProject(context.Background(), input)
	if err != nil || !created {
		t.Fatalf("create Tarser project: created=%v err=%v", created, err)
	}
	return project
}

func readyTarserProject(t *testing.T) (*Store, protocol.Project) {
	t.Helper()
	store := newTestStore(t)
	project := createTarserProject(t, store)
	gates := allPassingGates()
	gates.webHosts = []string{"staging-automation.tarser.net"}
	if err := store.recordTrustedProjectGateResults(context.Background(), project.ID, gates); err != nil {
		t.Fatal(err)
	}
	registerReadyProjectWorker(t, store, project)
	provisionTestProjectSecrets(t, store, project, "GITHUB_TOKEN=tarser-secret\n")
	return store, project
}

func TestTarserReleaseFailureVerifiesAutomaticRollback(t *testing.T) {
	store, project := readyTarserProject(t)
	runner := &fakeProjectRunner{durableStatus: projectDurableStatus{Outcome: "release_failed_rolled_back"}}
	operation, err := store.RunProjectOperation(context.Background(), runner, fakeHealth{}, project.ID, "staging", "release", structProjectOperationRequest())
	if err != nil {
		t.Fatal(err)
	}
	operation, err = store.ProjectOperation(context.Background(), runner, fakeHealth{}, project.ID, operation.ID)
	if err != nil || operation.Status != "release_failed_rolled_back" || len(runner.calls) != 1 {
		t.Fatalf("status=%q call count=%d", operation.Status, len(runner.calls))
	}
	wantRelease := recordedProjectCommand{executable: "/usr/local/bin/fx", args: []string{"staging", "release", projectSHA}, unit: factoryProjectOperationUnit(operation.ID), durable: true}
	if !reflect.DeepEqual(runner.calls[0], wantRelease) {
		t.Fatal("Tarser release did not invoke the fixed durable broker operation")
	}
}

func TestTarserHealthFailureRunsAndVerifiesNamedRollback(t *testing.T) {
	store, project := readyTarserProject(t)
	runner := &fakeProjectRunner{durableStatus: projectDurableStatus{Outcome: "succeeded"}}
	health := &sequenceHealth{errors: []error{errors.New("down"), nil}}
	operation, err := store.RunProjectOperation(context.Background(), runner, health, project.ID, "staging", "release", structProjectOperationRequest())
	if err != nil {
		t.Fatal(err)
	}
	operation, err = store.ProjectOperation(context.Background(), runner, health, project.ID, operation.ID)
	if err != nil || operation.Status != "running" {
		t.Fatalf("first poll operation=%+v err=%v", operation, err)
	}
	operation, err = store.ProjectOperation(context.Background(), runner, health, project.ID, operation.ID)
	if err != nil || operation.Status != "health_failed_rolled_back" || len(runner.calls) != 2 || health.calls != 2 {
		t.Fatalf("status=%q command calls=%d health calls=%d", operation.Status, len(runner.calls), health.calls)
	}
	wantRollback := recordedProjectCommand{executable: "/usr/local/bin/fx", args: []string{"staging", "rollback"}, unit: projectRollbackOperationUnit(operation.ID), durable: true}
	if !reflect.DeepEqual(runner.calls[1], wantRollback) {
		t.Fatal("Tarser health failure did not invoke the fixed durable rollback operation")
	}
}

func TestTarserNeverClaimsAnUnverifiedRollback(t *testing.T) {
	for _, test := range []struct {
		name      string
		failFirst bool
		health    error
	}{
		{name: "release error", failFirst: true},
		{name: "health error", health: errors.New("down")},
	} {
		t.Run(test.name, func(t *testing.T) {
			store, project := readyTarserProject(t)
			outcome := "succeeded"
			if test.failFirst {
				outcome = "rollback_failed"
			}
			runner := &fakeProjectRunner{durableStatus: projectDurableStatus{Outcome: outcome}}
			operation, err := store.RunProjectOperation(context.Background(), runner, fakeHealth{err: test.health}, project.ID, "staging", "release", structProjectOperationRequest())
			if err != nil {
				t.Fatal(err)
			}
			operation, err = store.ProjectOperation(context.Background(), runner, fakeHealth{err: test.health}, project.ID, operation.ID)
			if err != nil {
				t.Fatal(err)
			}
			if operation.Status == "running" {
				operation, err = store.ProjectOperation(context.Background(), runner, fakeHealth{err: test.health}, project.ID, operation.ID)
				if err != nil {
					t.Fatal(err)
				}
			}
			if operation.Status != "rollback_failed" {
				t.Fatalf("status=%q, want rollback_failed", operation.Status)
			}
		})
	}
}

func TestProjectSecretsReachOnlyTheAllowedProcess(t *testing.T) {
	store := newTestStore(t)
	project := createFactoryProject(t, store)
	if err := store.recordTrustedProjectGateResults(context.Background(), project.ID, allPassingGates()); err != nil {
		t.Fatal(err)
	}
	registerReadyProjectWorker(t, store, project)
	const secret = "super-secret-value"
	provisionTestProjectSecrets(t, store, project, "GITHUB_TOKEN="+secret+"\nUNDECLARED_SECRET=must-not-pass\n")
	runner := &fakeProjectRunner{}
	operation, err := store.RunProjectOperation(context.Background(), runner, fakeHealth{}, project.ID, "staging", "release", structProjectOperationRequest())
	if err != nil {
		t.Fatal(err)
	}
	if len(runner.calls) != 1 || !runner.calls[0].durable || len(runner.calls[0].environment) != 0 {
		t.Fatal("external self-release did not start without copying secrets into transient unit metadata")
	}
	apiBody, err := json.Marshal(operation)
	if err != nil {
		t.Fatal(err)
	}
	var status, message string
	if err := store.db.QueryRow(`SELECT status,message FROM project_operations WHERE id=?`, operation.ID).Scan(&status, &message); err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(apiBody), secret) || strings.Contains(status+message, secret) {
		t.Fatal("secret value escaped the adapter process into API or database state")
	}
}

func TestFactoryBrokerLostPOSTResponseStaysRunningUntilGETConfirmsOutcome(t *testing.T) {
	store := newTestStore(t)
	project := createFactoryProject(t, store)
	if err := store.recordTrustedProjectGateResults(context.Background(), project.ID, allPassingGates()); err != nil {
		t.Fatal(err)
	}
	registerReadyProjectWorker(t, store, project)
	provisionTestProjectSecrets(t, store, project, "GITHUB_TOKEN=value\n")
	runner := &fakeProjectRunner{
		durableStartResponseErr: errors.New("broker accepted POST but its response was lost"),
		durableStatus:           projectDurableStatus{Running: true},
	}
	operation, err := store.RunProjectOperation(context.Background(), runner, fakeHealth{}, project.ID, "staging", "release", structProjectOperationRequest())
	if err != nil || operation.Status != "running" || !strings.Contains(operation.Message, "result is unknown") {
		t.Fatalf("lost POST response: operation=%+v err=%v", operation, err)
	}
	if len(runner.calls) != 1 || !runner.calls[0].durable {
		t.Fatalf("broker POST was not attempted exactly once: calls=%+v", runner.calls)
	}

	if _, err := store.RunProjectOperation(context.Background(), runner, fakeHealth{}, project.ID, "staging", "rollback", structProjectOperationRequest()); errorCode(err) != "project_operation_running" {
		t.Fatalf("second operation was not blocked after lost broker response: %v", err)
	}
	if len(runner.calls) != 1 {
		t.Fatalf("second operation reached the broker: calls=%+v", runner.calls)
	}

	polled, err := store.ProjectOperation(context.Background(), runner, fakeHealth{}, project.ID, operation.ID)
	if err != nil || polled.Status != "running" {
		t.Fatalf("running broker GET finalized operation: operation=%+v err=%v", polled, err)
	}
	runner.durableStatus = projectDurableStatus{Outcome: "succeeded"}
	completed, err := store.ProjectOperation(context.Background(), runner, fakeHealth{}, project.ID, operation.ID)
	if err != nil || completed.Status != "succeeded" {
		t.Fatalf("final broker GET did not complete operation: operation=%+v err=%v", completed, err)
	}
}

func TestBrokerDefinitiveRejectionDoesNotLeaveOperationRunning(t *testing.T) {
	store := newTestStore(t)
	project := createFactoryProject(t, store)
	if err := store.recordTrustedProjectGateResults(context.Background(), project.ID, allPassingGates()); err != nil {
		t.Fatal(err)
	}
	registerReadyProjectWorker(t, store, project)
	provisionTestProjectSecrets(t, store, project, "GITHUB_TOKEN=value\n")
	runner := &fakeProjectRunner{durableStartResponseErr: &projectReleaseBrokerHTTPError{method: http.MethodPost, path: "/v1/operations", status: http.StatusConflict}}
	operation, err := store.RunProjectOperation(context.Background(), runner, fakeHealth{}, project.ID, "staging", "release", structProjectOperationRequest())
	if err != nil || operation.Status != "rollback_failed" || !strings.Contains(operation.Message, "rejected") {
		t.Fatalf("operation=%+v err=%v", operation, err)
	}
}

func TestHealthFailureRollsBackAndHealthyReleaseSucceeds(t *testing.T) {
	for _, test := range []struct {
		name       string
		health     error
		wantStatus string
		wantCalls  int
	}{{"healthy", nil, "running", 1}, {"unhealthy", errors.New("down"), "running", 1}} {
		t.Run(test.name, func(t *testing.T) {
			store := newTestStore(t)
			project := createFactoryProject(t, store)
			if err := store.recordTrustedProjectGateResults(context.Background(), project.ID, allPassingGates()); err != nil {
				t.Fatal(err)
			}
			registerReadyProjectWorker(t, store, project)
			provisionTestProjectSecrets(t, store, project, "GITHUB_TOKEN=value\n")
			runner := &fakeProjectRunner{}
			operation, err := store.RunProjectOperation(context.Background(), runner, fakeHealth{err: test.health}, project.ID, "staging", "release", structProjectOperationRequest())
			if err != nil || operation.Status != test.wantStatus || len(runner.calls) != test.wantCalls {
				t.Fatalf("operation=%+v calls=%+v err=%v", operation, runner.calls, err)
			}
		})
	}
}

func TestFactorySelfReleaseHealthFailureRollsBackAndVerifiesRestoredHealth(t *testing.T) {
	store := newTestStore(t)
	project := createFactoryProject(t, store)
	if err := store.recordTrustedProjectGateResults(context.Background(), project.ID, allPassingGates()); err != nil {
		t.Fatal(err)
	}
	registerReadyProjectWorker(t, store, project)
	provisionTestProjectSecrets(t, store, project, "GITHUB_TOKEN=value\n")
	started, err := store.RunProjectOperation(context.Background(), &fakeProjectRunner{}, fakeHealth{}, project.ID, "staging", "release", structProjectOperationRequest())
	if err != nil {
		t.Fatal(err)
	}
	runner := &fakeProjectRunner{durableStatus: projectDurableStatus{Outcome: "succeeded"}}
	health := &sequenceHealth{errors: []error{errors.New("new release is unhealthy"), nil}}
	completed, err := store.ProjectOperation(context.Background(), runner, health, project.ID, started.ID)
	if err != nil {
		t.Fatal(err)
	}
	if completed.Status != "running" || health.calls != 1 {
		t.Fatalf("first poll operation=%+v health calls=%d", completed, health.calls)
	}
	completed, err = store.ProjectOperation(context.Background(), runner, health, project.ID, started.ID)
	if err != nil || completed.Status != "health_failed_rolled_back" || health.calls != 2 {
		t.Fatalf("operation=%+v health calls=%d", completed, health.calls)
	}
	wantRollback := recordedProjectCommand{executable: "/usr/local/bin/fx", args: []string{"factory", "rollback"}, unit: projectRollbackOperationUnit(completed.ID), durable: true}
	if len(runner.calls) != 1 || !reflect.DeepEqual(runner.calls[0], wantRollback) {
		t.Fatalf("self-release rollback calls=%+v", runner.calls)
	}
}

func TestFactoryAutomaticRollbackRequiresRestoredHealth(t *testing.T) {
	for _, test := range []struct {
		name        string
		health      error
		wantStatus  string
		wantMessage string
	}{
		{
			name:        "restored health",
			wantStatus:  "release_failed_rolled_back",
			wantMessage: "Factory автоматически вернула предыдущую версию, восстановление подтверждено health-проверкой",
		},
		{
			name:        "failed health check",
			health:      errors.New("still down"),
			wantStatus:  "rollback_failed",
			wantMessage: "Factory сообщила об автоматическом откате, но health-проверка не подтвердила восстановление",
		},
	} {
		t.Run(test.name, func(t *testing.T) {
			store := newTestStore(t)
			project := createFactoryProject(t, store)
			if err := store.recordTrustedProjectGateResults(context.Background(), project.ID, allPassingGates()); err != nil {
				t.Fatal(err)
			}
			registerReadyProjectWorker(t, store, project)
			provisionTestProjectSecrets(t, store, project, "GITHUB_TOKEN=value\n")
			health := &sequenceHealth{errors: []error{test.health}}
			runner := &fakeProjectRunner{durableStatus: projectDurableStatus{Outcome: "release_failed_rolled_back"}}
			operation, err := store.RunProjectOperation(context.Background(), runner, health, project.ID, "staging", "release", structProjectOperationRequest())
			if err == nil {
				operation, err = store.ProjectOperation(context.Background(), runner, health, project.ID, operation.ID)
			}
			if err != nil || operation.Status != test.wantStatus || health.calls != 1 || !strings.Contains(operation.Message, test.wantMessage) {
				t.Fatalf("operation=%+v health calls=%d err=%v", operation, health.calls, err)
			}
		})
	}
}

func TestManualRollbackRequiresHealthyResultBeforeSuccess(t *testing.T) {
	for _, test := range []struct {
		name       string
		health     error
		wantStatus string
	}{
		{name: "healthy", wantStatus: "succeeded"},
		{name: "unhealthy", health: errors.New("still down"), wantStatus: "rollback_failed"},
	} {
		t.Run(test.name, func(t *testing.T) {
			store := newTestStore(t)
			project := createFactoryProject(t, store)
			if err := store.recordTrustedProjectGateResults(context.Background(), project.ID, allPassingGates()); err != nil {
				t.Fatal(err)
			}
			registerReadyProjectWorker(t, store, project)
			provisionTestProjectSecrets(t, store, project, "GITHUB_TOKEN=value\n")
			health := &sequenceHealth{errors: []error{test.health}}
			runner := &fakeProjectRunner{durableStatus: projectDurableStatus{Outcome: "succeeded"}}
			operation, err := store.RunProjectOperation(context.Background(), runner, health, project.ID, "staging", "rollback", structProjectOperationRequest())
			if err == nil {
				operation, err = store.ProjectOperation(context.Background(), runner, health, project.ID, operation.ID)
			}
			if err != nil || operation.Status != test.wantStatus || health.calls != 1 {
				t.Fatalf("operation=%+v health calls=%d err=%v", operation, health.calls, err)
			}
		})
	}
}

func TestFactorySelfReleaseRunsOutsideServerAndRecoversAfterRestart(t *testing.T) {
	store := newTestStore(t)
	project := createFactoryProject(t, store)
	if err := store.recordTrustedProjectGateResults(context.Background(), project.ID, allPassingGates()); err != nil {
		t.Fatal(err)
	}
	registerReadyProjectWorker(t, store, project)
	provisionTestProjectSecrets(t, store, project, "GITHUB_TOKEN=value\n")
	starter := &fakeProjectRunner{}
	operation, err := store.RunProjectOperation(context.Background(), starter, fakeHealth{}, project.ID, "staging", "release", structProjectOperationRequest())
	if err != nil || operation.Status != "running" || len(starter.calls) != 1 {
		t.Fatalf("external start: operation=%+v calls=%+v err=%v", operation, starter.calls, err)
	}
	call := starter.calls[0]
	if !call.durable || call.executable != "/usr/local/bin/fx" || !reflect.DeepEqual(call.args, []string{"factory", "release", projectSHA}) || call.unit != factoryProjectOperationUnit(operation.ID) {
		t.Fatalf("durable invocation = %+v", call)
	}
	// A fresh runner represents the restarted factory-server process. The unit
	// name is derived from persisted operation state, so no in-memory handle is required.
	restarted := &fakeProjectRunner{durableStatus: projectDurableStatus{Outcome: "succeeded"}}
	health := &sequenceHealth{}
	if err := store.ReconcileProjectOperations(context.Background(), restarted, health); err != nil {
		t.Fatal(err)
	}
	recovered, err := store.ProjectOperation(context.Background(), restarted, health, project.ID, operation.ID)
	if err != nil || recovered.Status != "succeeded" || !strings.Contains(recovered.Message, "health was verified") || health.calls != 1 {
		t.Fatalf("recovered operation=%+v err=%v", recovered, err)
	}
}

func TestFactoryBrokerReportsExactAutomaticRollbackOutcomes(t *testing.T) {
	for _, test := range []struct {
		brokerStatus string
		wantStatus   string
	}{
		{brokerStatus: "release_failed_rolled_back", wantStatus: "release_failed_rolled_back"},
		{brokerStatus: "rollback_failed", wantStatus: "rollback_failed"},
	} {
		t.Run(test.brokerStatus, func(t *testing.T) {
			store := newTestStore(t)
			project := createFactoryProject(t, store)
			if err := store.recordTrustedProjectGateResults(context.Background(), project.ID, allPassingGates()); err != nil {
				t.Fatal(err)
			}
			registerReadyProjectWorker(t, store, project)
			provisionTestProjectSecrets(t, store, project, "GITHUB_TOKEN=value\n")
			started, err := store.RunProjectOperation(context.Background(), &fakeProjectRunner{}, fakeHealth{}, project.ID, "staging", "release", structProjectOperationRequest())
			if err != nil {
				t.Fatal(err)
			}
			completed, err := store.ProjectOperation(context.Background(), &fakeProjectRunner{durableStatus: projectDurableStatus{Outcome: test.brokerStatus}}, fakeHealth{}, project.ID, started.ID)
			if err != nil || completed.Status != test.wantStatus {
				t.Fatalf("broker status %q produced operation=%+v err=%v", test.brokerStatus, completed, err)
			}
		})
	}
	if _, err := parseProjectReleaseBrokerStatus("failed"); err == nil {
		t.Fatal("ambiguous broker status failed was accepted without a rollback outcome")
	}
}

func TestProjectOperationRejectsSecondRunningOperationWithConflict(t *testing.T) {
	store := newTestStore(t)
	project := createFactoryProject(t, store)
	if err := store.recordTrustedProjectGateResults(context.Background(), project.ID, allPassingGates()); err != nil {
		t.Fatal(err)
	}
	registerReadyProjectWorker(t, store, project)
	provisionTestProjectSecrets(t, store, project, "GITHUB_TOKEN=value\n")
	runner := &fakeProjectRunner{}
	if _, err := store.RunProjectOperation(context.Background(), runner, fakeHealth{}, project.ID, "staging", "release", structProjectOperationRequest()); err != nil {
		t.Fatal(err)
	}

	body, _ := json.Marshal(structProjectOperationRequest())
	request := httptest.NewRequest(http.MethodPost, "/api/v1/projects/ignored/environments/staging/rollback", bytes.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	request.SetPathValue("project_id", project.ID)
	request.SetPathValue("environment", "staging")
	request.SetPathValue("operation", "rollback")
	response := httptest.NewRecorder()
	api := &API{store: store, projectRunner: runner, projectHealth: fakeHealth{}}
	api.runProjectOperation(response, request)
	if response.Code != http.StatusConflict || !strings.Contains(response.Body.String(), "project_operation_running") {
		t.Fatalf("second operation status=%d body=%s", response.Code, response.Body.String())
	}
	if len(runner.calls) != 1 {
		t.Fatalf("second adapter was launched: calls=%+v", runner.calls)
	}
}

func TestFactorySelfReleaseFailsClosedWhenExternalBrokerIsMissing(t *testing.T) {
	runner := execProjectCommandRunner{releaseBrokerSocket: filepath.Join(t.TempDir(), "missing.sock")}
	err := runner.StartDurable(context.Background(), "factory-project-release-1234567890abcdef1234567890abcdef", "/usr/local/bin/fx", []string{"factory", "release", projectSHA})
	if err == nil || !strings.Contains(err.Error(), "POST /v1/operations") {
		t.Fatalf("missing broker error = %v", err)
	}
}

func TestNoNewPrivilegesServiceCanCallUnixReleaseBroker(t *testing.T) {
	if runtime.GOOS != "linux" {
		t.Skip("NoNewPrivileges and setpriv are Linux service guarantees")
	}
	if os.Getenv("FACTORY_NNP_BROKER_HELPER") == "1" {
		status, err := os.ReadFile("/proc/self/status")
		if err != nil || !strings.Contains(string(status), "NoNewPrivs:\t1") {
			t.Fatalf("helper is not running with NoNewPrivileges: %v", err)
		}
		runner := execProjectCommandRunner{releaseBrokerSocket: os.Getenv("FACTORY_NNP_BROKER_SOCKET")}
		if err := runner.StartDurable(context.Background(), "factory-project-release-nnp", "/usr/local/bin/fx", []string{"factory", "release", projectSHA}); err != nil {
			t.Fatal(err)
		}
		return
	}

	socket := filepath.Join(t.TempDir(), "broker.sock")
	listener, err := net.Listen("unix", socket)
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	received := make(chan projectReleaseBrokerRequest, 1)
	server := &http.Server{Handler: http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		var input projectReleaseBrokerRequest
		if request.Method != http.MethodPost || request.URL.Path != "/v1/operations" || json.NewDecoder(request.Body).Decode(&input) != nil {
			http.Error(response, "bad request", http.StatusBadRequest)
			return
		}
		received <- input
		response.WriteHeader(http.StatusAccepted)
	})}
	defer server.Close()
	go func() { _ = server.Serve(listener) }()

	command := exec.Command("/usr/bin/setpriv", "--no-new-privs", os.Args[0], "-test.run=^TestNoNewPrivilegesServiceCanCallUnixReleaseBroker$")
	command.Env = append(os.Environ(), "FACTORY_NNP_BROKER_HELPER=1", "FACTORY_NNP_BROKER_SOCKET="+socket)
	if output, err := command.CombinedOutput(); err != nil {
		t.Fatalf("NoNewPrivileges helper failed: %v: %s", err, output)
	}
	input := <-received
	if input.OperationID != "factory-project-release-nnp" || input.Adapter != "fx-factory-release" || input.CommitSHA != projectSHA {
		t.Fatalf("broker request=%+v", input)
	}
}

func structProjectOperationRequest() protocol.ProjectOperationRequest {
	return protocol.ProjectOperationRequest{CommitSHA: projectSHA}
}
