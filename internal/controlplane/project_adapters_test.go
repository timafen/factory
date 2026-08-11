package controlplane

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"reflect"
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
	calls         []recordedProjectCommand
	failFirst     bool
	runCalls      int
	outputs       []string
	outputCalls   int
	durableStatus projectDurableStatus
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
	runner := &fakeProjectRunner{}
	if _, err := runProjectAdapter(context.Background(), runner, "fx-factory-release", projectSHA, nil); err != nil {
		t.Fatal(err)
	}
	want := recordedProjectCommand{executable: "/usr/local/bin/fx", args: []string{"factory", "release", projectSHA}}
	if !reflect.DeepEqual(runner.calls[0], want) {
		t.Fatalf("argv = %+v", runner.calls[0])
	}
	if _, err := runProjectAdapter(context.Background(), runner, "sh -c anything", projectSHA, nil); errorCode(err) != "adapter_not_allowed" {
		t.Fatalf("unknown adapter error = %v", err)
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
	runner := &fakeProjectRunner{failFirst: true, outputs: []string{"/srv/automation-ebay-operations/staging/releases/previous\n", "/srv/automation-ebay-operations/staging/releases/previous\n"}}
	operation, err := store.RunProjectOperation(context.Background(), runner, fakeHealth{}, project.ID, "staging", "release", structProjectOperationRequest())
	if err != nil {
		t.Fatal(err)
	}
	if operation.Status != "release_failed_rolled_back" || len(runner.calls) != 3 {
		t.Fatalf("status=%q call count=%d", operation.Status, len(runner.calls))
	}
	wantRelease := recordedProjectCommand{executable: "/usr/local/bin/fx", args: []string{"staging", "release", projectSHA}, environment: []string{"GITHUB_TOKEN=tarser-secret"}}
	if !reflect.DeepEqual(runner.calls[1], wantRelease) {
		t.Fatal("Tarser release did not invoke the fixed staging release operation with the allowed environment")
	}
}

func TestTarserHealthFailureRunsAndVerifiesNamedRollback(t *testing.T) {
	store, project := readyTarserProject(t)
	runner := &fakeProjectRunner{outputs: []string{"/srv/automation-ebay-operations/staging/releases/previous\n", "/srv/automation-ebay-operations/staging/releases/previous\n"}}
	operation, err := store.RunProjectOperation(context.Background(), runner, fakeHealth{err: errors.New("down")}, project.ID, "staging", "release", structProjectOperationRequest())
	if err != nil {
		t.Fatal(err)
	}
	if operation.Status != "health_failed_rolled_back" || len(runner.calls) != 4 {
		t.Fatalf("status=%q call count=%d", operation.Status, len(runner.calls))
	}
	wantRollback := recordedProjectCommand{executable: "/usr/local/bin/fx", args: []string{"staging", "rollback"}, environment: []string{"GITHUB_TOKEN=tarser-secret"}}
	if !reflect.DeepEqual(runner.calls[2], wantRollback) {
		t.Fatal("Tarser health failure did not invoke the fixed rollback command with the allowed environment")
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
			runner := &fakeProjectRunner{failFirst: test.failFirst, outputs: []string{"/srv/automation-ebay-operations/staging/releases/previous\n", "/srv/automation-ebay-operations/staging/releases/unexpected\n"}}
			operation, err := store.RunProjectOperation(context.Background(), runner, fakeHealth{err: test.health}, project.ID, "staging", "release", structProjectOperationRequest())
			if err != nil {
				t.Fatal(err)
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

func TestFailedReleaseInvokesNamedRollbackAndPersistsStatus(t *testing.T) {
	store := newTestStore(t)
	project := createFactoryProject(t, store)
	if err := store.recordTrustedProjectGateResults(context.Background(), project.ID, allPassingGates()); err != nil {
		t.Fatal(err)
	}
	registerReadyProjectWorker(t, store, project)
	provisionTestProjectSecrets(t, store, project, "GITHUB_TOKEN=value\n")
	runner := &fakeProjectRunner{failFirst: true}
	operation, err := store.RunProjectOperation(context.Background(), runner, fakeHealth{}, project.ID, "staging", "release", structProjectOperationRequest())
	if err != nil {
		t.Fatal(err)
	}
	if operation.Status != "rollback_failed" || len(runner.calls) != 1 || !runner.calls[0].durable {
		t.Fatalf("operation=%+v calls=%+v", operation, runner.calls)
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
	if err := store.ReconcileProjectOperations(context.Background(), restarted); err != nil {
		t.Fatal(err)
	}
	recovered, err := store.ProjectOperation(context.Background(), restarted, project.ID, operation.ID)
	if err != nil || recovered.Status != "succeeded" || !strings.Contains(recovered.Message, "survived the server restart") {
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
			completed, err := store.ProjectOperation(context.Background(), &fakeProjectRunner{durableStatus: projectDurableStatus{Outcome: test.brokerStatus}}, project.ID, started.ID)
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
	if err == nil || !strings.Contains(err.Error(), "POST /v1/releases") {
		t.Fatalf("missing broker error = %v", err)
	}
}

func structProjectOperationRequest() protocol.ProjectOperationRequest {
	return protocol.ProjectOperationRequest{CommitSHA: projectSHA}
}
