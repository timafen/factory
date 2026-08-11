package controlplane

import (
	"context"
	"errors"
	"reflect"
	"testing"

	"github.com/owainlewis/factory/internal/protocol"
)

type recordedProjectCommand struct {
	executable string
	args       []string
}
type fakeProjectRunner struct {
	calls     []recordedProjectCommand
	failFirst bool
}

func (runner *fakeProjectRunner) Run(_ context.Context, executable string, args ...string) error {
	runner.calls = append(runner.calls, recordedProjectCommand{executable: executable, args: append([]string(nil), args...)})
	if runner.failFirst && len(runner.calls) == 1 {
		return errors.New("release failed")
	}
	return nil
}

type fakeHealth struct{ err error }

func (health fakeHealth) Check(context.Context, string) error { return health.err }

func TestProjectAdapterRegistryUsesFixedArgvWithoutShell(t *testing.T) {
	runner := &fakeProjectRunner{}
	if _, err := runProjectAdapter(context.Background(), runner, "fx-factory-release", projectSHA); err != nil {
		t.Fatal(err)
	}
	want := recordedProjectCommand{executable: "/usr/local/bin/fx", args: []string{"factory", "release", projectSHA}}
	if !reflect.DeepEqual(runner.calls[0], want) {
		t.Fatalf("argv = %+v", runner.calls[0])
	}
	if _, err := runProjectAdapter(context.Background(), runner, "sh -c anything", projectSHA); errorCode(err) != "adapter_not_allowed" {
		t.Fatalf("unknown adapter error = %v", err)
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
