package controlplane

import (
	"context"
	"encoding/json"
	"errors"
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
}
type fakeProjectRunner struct {
	calls       []recordedProjectCommand
	failFirst   bool
	runCalls    int
	outputs     []string
	outputCalls int
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

type fakeHealth struct{ err error }

func (health fakeHealth) Check(context.Context, string) error { return health.err }

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
	if err := store.RecordProjectGateResults(context.Background(), project.ID, allPassingGates()); err != nil {
		t.Fatal(err)
	}
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
	if runner.calls[1].executable != "/srv/automation-ebay-operations/staging/current/deploy/staging/scripts/deploy-release" {
		t.Fatalf("release call=%+v", runner.calls[1])
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
	if err := store.RecordProjectGateResults(context.Background(), project.ID, allPassingGates()); err != nil {
		t.Fatal(err)
	}
	const secret = "super-secret-value"
	provisionTestProjectSecrets(t, store, project, "GITHUB_TOKEN="+secret+"\nUNDECLARED_SECRET=must-not-pass\n")
	runner := &fakeProjectRunner{}
	operation, err := store.RunProjectOperation(context.Background(), runner, fakeHealth{}, project.ID, "staging", "release", structProjectOperationRequest())
	if err != nil {
		t.Fatal(err)
	}
	if len(runner.calls) != 1 || !reflect.DeepEqual(runner.calls[0].environment, []string{"GITHUB_TOKEN=" + secret}) {
		t.Fatal("adapter did not receive exactly the declared secret environment")
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
	if err := store.RecordProjectGateResults(context.Background(), project.ID, allPassingGates()); err != nil {
		t.Fatal(err)
	}
	provisionTestProjectSecrets(t, store, project, "GITHUB_TOKEN=value\n")
	runner := &fakeProjectRunner{failFirst: true}
	operation, err := store.RunProjectOperation(context.Background(), runner, fakeHealth{}, project.ID, "staging", "release", structProjectOperationRequest())
	if err != nil {
		t.Fatal(err)
	}
	if operation.Status != "release_failed_rolled_back" || len(runner.calls) != 2 || runner.calls[1].args[1] != "rollback" {
		t.Fatalf("operation=%+v calls=%+v", operation, runner.calls)
	}
}

func TestHealthFailureRollsBackAndHealthyReleaseSucceeds(t *testing.T) {
	for _, test := range []struct {
		name       string
		health     error
		wantStatus string
		wantCalls  int
	}{{"healthy", nil, "succeeded", 1}, {"unhealthy", errors.New("down"), "health_failed_rolled_back", 2}} {
		t.Run(test.name, func(t *testing.T) {
			store := newTestStore(t)
			project := createFactoryProject(t, store)
			if err := store.RecordProjectGateResults(context.Background(), project.ID, allPassingGates()); err != nil {
				t.Fatal(err)
			}
			provisionTestProjectSecrets(t, store, project, "GITHUB_TOKEN=value\n")
			runner := &fakeProjectRunner{}
			operation, err := store.RunProjectOperation(context.Background(), runner, fakeHealth{err: test.health}, project.ID, "staging", "release", structProjectOperationRequest())
			if err != nil || operation.Status != test.wantStatus || len(runner.calls) != test.wantCalls {
				t.Fatalf("operation=%+v calls=%+v err=%v", operation, runner.calls, err)
			}
		})
	}
}

func structProjectOperationRequest() protocol.ProjectOperationRequest {
	return protocol.ProjectOperationRequest{CommitSHA: projectSHA}
}
