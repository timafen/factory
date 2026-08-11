package controlplane

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"

	"github.com/owainlewis/factory/internal/protocol"
)

const projectSHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

func errorCode(err error) string {
	var service *ServiceError
	if errors.As(err, &service) {
		return service.Code
	}
	return ""
}

func factoryProjectRequest() protocol.CreateProjectRequest {
	return protocol.CreateProjectRequest{
		Name: "Factory", RemoteIdentity: "github.com/timafen/factory", MainBranch: "main",
		ProjectType:    protocol.ProjectTypeFactorySingleInstance,
		RequiredChecks: []string{"tests", "build", "secret-scan", "static-typecheck"},
		Environments: []protocol.ProjectEnvironmentInput{{
			Name: "staging", URL: "https://factory.timafen.com", HealthURL: "https://factory.timafen.com/api/v1/dashboard",
			ReleaseAdapter: "fx-factory-release", RollbackAdapter: "fx-factory-rollback",
			RequiredSecrets: []string{"GITHUB_TOKEN"}, WebHosts: []string{"factory.timafen.com"},
		}},
	}
}

func createFactoryProject(t *testing.T, store *Store) protocol.Project {
	t.Helper()
	project, created, err := store.CreateProject(context.Background(), factoryProjectRequest())
	if err != nil {
		t.Fatal(err)
	}
	if !created {
		t.Fatal("expected new project")
	}
	return project
}

func TestProjectCreateUsesServerAllowlistAndIsIdempotent(t *testing.T) {
	store := newTestStore(t)
	project := createFactoryProject(t, store)
	if project.RemoteIdentity != "github.com/timafen/factory" || project.ExecutorGroup != "factory" {
		t.Fatalf("unexpected server policy: %+v", project)
	}
	duplicate, created, err := store.CreateProject(context.Background(), factoryProjectRequest())
	if err != nil || created || duplicate.ID != project.ID {
		t.Fatalf("idempotent create = %+v, %v, %v", duplicate, created, err)
	}
	changed := factoryProjectRequest()
	changed.Name = "Other"
	if _, _, err := store.CreateProject(context.Background(), changed); errorCode(err) != "project_contract_conflict" {
		t.Fatalf("changed contract error = %v", err)
	}

	invalidCases := []protocol.CreateProjectRequest{}
	unknown := factoryProjectRequest()
	unknown.ProjectType = "shell"
	invalidCases = append(invalidCases, unknown)
	mismatch := factoryProjectRequest()
	mismatch.RemoteIdentity = "github.com/timafen/tarser-operations"
	invalidCases = append(invalidCases, mismatch)
	command := factoryProjectRequest()
	command.Environments[0].ReleaseAdapter = "sh -c deploy"
	invalidCases = append(invalidCases, command)
	wildcard := factoryProjectRequest()
	wildcard.Environments[0].WebHosts = []string{"*.timafen.com"}
	invalidCases = append(invalidCases, wildcard)
	missing := factoryProjectRequest()
	missing.Environments[0].RequiredSecrets = nil
	invalidCases = append(invalidCases, missing)
	missingName := factoryProjectRequest()
	missingName.Name = ""
	invalidCases = append(invalidCases, missingName)
	missingRepository := factoryProjectRequest()
	missingRepository.RemoteIdentity = ""
	invalidCases = append(invalidCases, missingRepository)
	missingBranch := factoryProjectRequest()
	missingBranch.MainBranch = ""
	invalidCases = append(invalidCases, missingBranch)
	missingChecks := factoryProjectRequest()
	missingChecks.RequiredChecks = missingChecks.RequiredChecks[:3]
	invalidCases = append(invalidCases, missingChecks)
	missingURL := factoryProjectRequest()
	missingURL.Environments[0].URL = ""
	invalidCases = append(invalidCases, missingURL)
	missingHealth := factoryProjectRequest()
	missingHealth.Environments[0].HealthURL = ""
	invalidCases = append(invalidCases, missingHealth)
	missingRollback := factoryProjectRequest()
	missingRollback.Environments[0].RollbackAdapter = ""
	invalidCases = append(invalidCases, missingRollback)
	missingHosts := factoryProjectRequest()
	missingHosts.Environments[0].WebHosts = nil
	invalidCases = append(invalidCases, missingHosts)
	for index, input := range invalidCases {
		if _, _, err := store.CreateProject(context.Background(), input); err == nil {
			t.Fatalf("invalid case %d accepted", index)
		}
	}
}

func TestProductionIsBlockedAtCreationAndCannotBeReleasedByClientFlag(t *testing.T) {
	store := newTestStore(t)
	input := factoryProjectRequest()
	production := input.Environments[0]
	production.Name = "production"
	production.URL = "https://factory-production.timafen.com"
	production.HealthURL = "https://factory-production.timafen.com/health"
	production.WebHosts = []string{"factory-production.timafen.com"}
	input.Environments = append(input.Environments, production)
	if _, _, err := store.CreateProject(context.Background(), input); errorCode(err) != "production_not_blocked" {
		t.Fatalf("unblocked production error = %v", err)
	}
	input.Environments[1].Blocked = true
	project, _, err := store.CreateProject(context.Background(), input)
	if err != nil {
		t.Fatal(err)
	}
	_, err = store.RunProjectOperation(context.Background(), &fakeProjectRunner{}, fakeHealth{}, project.ID, "production", "release", protocol.ProjectOperationRequest{CommitSHA: projectSHA, OwnerConfirmed: true})
	if errorCode(err) != "production_confirmation_required" {
		t.Fatalf("client confirmation released production: %v", err)
	}
}

func TestTarserV1RejectsProductionAndUsesOnlyStagingPolicy(t *testing.T) {
	store := newTestStore(t)
	input := factoryProjectRequest()
	input.Name = "Tarser staging"
	input.RemoteIdentity = "github.com/timafen/tarser-operations"
	input.ProjectType = protocol.ProjectTypeTarserOperationsStaging
	input.Environments[0].URL = "https://staging-automation.tarser.net"
	input.Environments[0].HealthURL = "https://staging-automation.tarser.net/ops/health/"
	input.Environments[0].ReleaseAdapter = "tarser-staging-deploy-release"
	input.Environments[0].RollbackAdapter = "tarser-staging-auto-rollback"
	input.Environments[0].WebHosts = []string{"staging-automation.tarser.net"}
	project, _, err := store.CreateProject(context.Background(), input)
	if err != nil || project.ExecutorGroup != "automation-ebay-staging" {
		t.Fatalf("tarser staging = %+v, %v", project, err)
	}
	production := input.Environments[0]
	production.Name = "production"
	production.Blocked = true
	production.URL = "https://automation.tarser.net"
	production.HealthURL = "https://automation.tarser.net/ops/health/"
	production.WebHosts = []string{"automation.tarser.net"}
	input.Environments = append(input.Environments, production)
	if _, _, err := store.CreateProject(context.Background(), input); errorCode(err) != "production_not_supported" {
		t.Fatalf("production error = %v", err)
	}
}

func TestProjectJSONContainsSecretNamesButNeverValues(t *testing.T) {
	store := newTestStore(t)
	project := createFactoryProject(t, store)
	body, err := json.Marshal(project)
	if err != nil {
		t.Fatal(err)
	}
	if string(body) == "" || !json.Valid(body) {
		t.Fatal("invalid project JSON")
	}
	if strings.Contains(string(body), "super-secret-value") {
		t.Fatal("secret value leaked")
	}
}
