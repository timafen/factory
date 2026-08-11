package controlplane

import (
	"context"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"net/url"
	"slices"
	"sort"
	"strings"
	"time"
	"unicode"

	"github.com/owainlewis/factory/internal/protocol"
)

var requiredProjectChecks = []string{"build", "secret-scan", "static-typecheck", "tests"}

type projectPolicy struct {
	remoteIdentity  string
	executorGroup   string
	releaseAdapter  string
	rollbackAdapter string
	stagingHost     string
}

var projectPolicies = map[string]projectPolicy{
	protocol.ProjectTypeFactorySingleInstance: {
		remoteIdentity: "github.com/timafen/factory", executorGroup: "factory",
		releaseAdapter: "fx-factory-release", rollbackAdapter: "fx-factory-rollback",
		stagingHost: "factory.timafen.com",
	},
	protocol.ProjectTypeTarserOperationsStaging: {
		remoteIdentity: "github.com/timafen/tarser-operations", executorGroup: "automation-ebay-staging",
		releaseAdapter: "tarser-staging-deploy-release", rollbackAdapter: "tarser-staging-auto-rollback",
		stagingHost: "staging-automation.tarser.net",
	},
}

func projectPolicyFor(projectType, remoteIdentity string) (projectPolicy, error) {
	policy, ok := projectPolicies[projectType]
	if !ok {
		return projectPolicy{}, invalid("unsupported_project_type", "project type is not enabled in the v1 server allowlist")
	}
	if remoteIdentity != policy.remoteIdentity {
		return projectPolicy{}, invalid("project_policy_mismatch", "canonical repository does not match the server policy for this project type")
	}
	return policy, nil
}

func validProjectName(value string) bool {
	return value != "" && len([]rune(value)) <= 120 && !strings.ContainsAny(value, "\r\n\x00")
}

func validProjectToken(value string) bool {
	if value == "" || len(value) > 100 || strings.HasPrefix(value, "-") || strings.HasSuffix(value, "-") {
		return false
	}
	for _, r := range value {
		if !(unicode.IsLetter(r) || unicode.IsDigit(r) || strings.ContainsRune("._/-", r)) {
			return false
		}
	}
	return !strings.Contains(value, "..")
}

func validSecretName(value string) bool {
	if value == "" || len(value) > 128 || value[0] < 'A' || value[0] > 'Z' {
		return false
	}
	for _, r := range value {
		if !(r >= 'A' && r <= 'Z') && !(r >= '0' && r <= '9') && r != '_' {
			return false
		}
	}
	return true
}

func validExactFQDN(host string) bool {
	if len(host) > 253 || !strings.Contains(host, ".") {
		return false
	}
	for _, label := range strings.Split(host, ".") {
		if label == "" || len(label) > 63 || label[0] == '-' || label[len(label)-1] == '-' {
			return false
		}
		for _, character := range label {
			if !(character >= 'a' && character <= 'z') && !(character >= '0' && character <= '9') && character != '-' {
				return false
			}
		}
	}
	return true
}

func exactHTTPSURL(raw string) (*url.URL, error) {
	parsed, err := url.Parse(raw)
	if err != nil || parsed.Scheme != "https" || parsed.User != nil || parsed.Host == "" || parsed.Fragment != "" {
		return nil, invalid("invalid_project_url", "environment and health URLs must be absolute HTTPS URLs without credentials or fragments")
	}
	host := strings.ToLower(parsed.Hostname())
	if !validExactFQDN(host) || net.ParseIP(host) != nil {
		return nil, invalid("invalid_project_host", "project hosts must be exact FQDNs; wildcards and IP addresses are forbidden")
	}
	return parsed, nil
}

func normalizeProjectRequest(input protocol.CreateProjectRequest) (protocol.CreateProjectRequest, projectPolicy, error) {
	input.Name = strings.TrimSpace(input.Name)
	input.MainBranch = strings.TrimSpace(input.MainBranch)
	input.ProjectType = strings.TrimSpace(input.ProjectType)
	remote, err := normalizeManagedGitHubRemote(input.RemoteIdentity)
	if err != nil {
		return input, projectPolicy{}, err
	}
	input.RemoteIdentity = remote
	policy, err := projectPolicyFor(input.ProjectType, remote)
	if err != nil {
		return input, projectPolicy{}, err
	}
	if !validProjectName(input.Name) || !validProjectToken(input.MainBranch) {
		return input, projectPolicy{}, invalid("invalid_project", "name and main_branch are required and must use safe characters")
	}
	checks := append([]string(nil), input.RequiredChecks...)
	sort.Strings(checks)
	if strings.Join(checks, "\x00") != strings.Join(requiredProjectChecks, "\x00") {
		return input, projectPolicy{}, invalid("invalid_project_checks", "required_checks must contain exactly secret-scan, static-typecheck, tests, and build")
	}
	input.RequiredChecks = checks
	if len(input.Environments) == 0 || len(input.Environments) > 2 {
		return input, projectPolicy{}, invalid("invalid_environments", "exactly one staging and at most one production environment are allowed")
	}
	seenEnvironment := map[string]bool{}
	for i := range input.Environments {
		environment := &input.Environments[i]
		environment.Name = strings.TrimSpace(environment.Name)
		if seenEnvironment[environment.Name] || (environment.Name != "staging" && environment.Name != "production") {
			return input, projectPolicy{}, invalid("invalid_environment", "environment names must be unique staging or production")
		}
		seenEnvironment[environment.Name] = true
		if environment.Name == "staging" && environment.Blocked {
			return input, projectPolicy{}, invalid("staging_blocked", "staging cannot be blocked")
		}
		if environment.Name == "production" && !environment.Blocked {
			return input, projectPolicy{}, invalid("production_not_blocked", "production must be blocked when the project is created")
		}
		if environment.Name == "production" && input.ProjectType == protocol.ProjectTypeTarserOperationsStaging {
			return input, projectPolicy{}, invalid("production_not_supported", "tarser production is outside the v1 project type")
		}
		baseURL, err := exactHTTPSURL(environment.URL)
		if err != nil {
			return input, projectPolicy{}, err
		}
		healthURL, err := exactHTTPSURL(environment.HealthURL)
		if err != nil || !strings.EqualFold(baseURL.Hostname(), healthURL.Hostname()) {
			return input, projectPolicy{}, invalid("invalid_health_url", "health_url must be HTTPS on the environment host")
		}
		if environment.Name == "staging" && !strings.EqualFold(baseURL.Hostname(), policy.stagingHost) {
			return input, projectPolicy{}, invalid("project_policy_mismatch", "staging host does not match the server project allowlist")
		}
		if environment.ReleaseAdapter != policy.releaseAdapter || environment.RollbackAdapter != policy.rollbackAdapter {
			return input, projectPolicy{}, invalid("adapter_not_allowed", "release and rollback adapters must match the named server allowlist")
		}
		if len(environment.RequiredSecrets) == 0 || len(environment.WebHosts) == 0 {
			return input, projectPolicy{}, invalid("incomplete_environment", "required_secrets and web_hosts cannot be empty")
		}
		sort.Strings(environment.RequiredSecrets)
		sort.Strings(environment.WebHosts)
		seenSecret, seenHost := map[string]bool{}, map[string]bool{}
		for _, name := range environment.RequiredSecrets {
			if !validSecretName(name) || seenSecret[name] {
				return input, projectPolicy{}, invalid("invalid_secret_name", "secret names must be unique uppercase environment names")
			}
			seenSecret[name] = true
		}
		for _, host := range environment.WebHosts {
			parsed, hostErr := exactHTTPSURL("https://" + host)
			canonical := strings.ToLower(parsedHostname(parsed))
			if hostErr != nil || host != canonical || seenHost[canonical] {
				return input, projectPolicy{}, invalid("invalid_web_host", "web_hosts must contain unique lowercase exact FQDNs")
			}
			seenHost[canonical] = true
		}
		if !seenHost[strings.ToLower(baseURL.Hostname())] {
			return input, projectPolicy{}, invalid("host_not_allowed", "the environment host must be present in web_hosts")
		}
	}
	if !seenEnvironment["staging"] {
		return input, projectPolicy{}, invalid("staging_required", "staging is required")
	}
	sort.Slice(input.Environments, func(i, j int) bool { return input.Environments[i].Name < input.Environments[j].Name })
	return input, policy, nil
}

func parsedHostname(value *url.URL) string {
	if value == nil {
		return ""
	}
	return value.Hostname()
}

func (s *Store) CreateProject(ctx context.Context, raw protocol.CreateProjectRequest) (protocol.Project, bool, error) {
	input, _, err := normalizeProjectRequest(raw)
	if err != nil {
		return protocol.Project{}, false, err
	}
	contract, err := json.Marshal(input)
	if err != nil {
		return protocol.Project{}, false, unavailable(err)
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return protocol.Project{}, false, unavailable(err)
	}
	defer tx.Rollback()
	var repositoryID, projectID, existingContract string
	err = tx.QueryRowContext(ctx, `SELECT p.id, p.repository_id, p.contract_json FROM projects p JOIN repositories r ON r.id=p.repository_id WHERE lower(r.remote_identity)=lower(?)`, input.RemoteIdentity).Scan(&projectID, &repositoryID, &existingContract)
	if err == nil {
		if existingContract != string(contract) {
			return protocol.Project{}, false, conflict("project_contract_conflict", "repository is already connected with a different project contract")
		}
		if err := tx.Commit(); err != nil {
			return protocol.Project{}, false, unavailable(err)
		}
		project, err := s.Project(ctx, projectID)
		return project, false, err
	}
	if !errors.Is(err, sql.ErrNoRows) {
		return protocol.Project{}, false, unavailable(err)
	}
	err = tx.QueryRowContext(ctx, `SELECT id FROM repositories WHERE lower(remote_identity)=lower(?)`, input.RemoteIdentity).Scan(&repositoryID)
	if errors.Is(err, sql.ErrNoRows) {
		repositoryID, err = newID()
		if err == nil {
			now := s.now().UnixMilli()
			_, err = tx.ExecContext(ctx, `INSERT INTO repositories(id,remote_identity,enabled,centrally_managed,created_at,updated_at) VALUES(?,?,1,1,?,?)`, repositoryID, input.RemoteIdentity, now, now)
		}
	}
	if err != nil {
		return protocol.Project{}, false, unavailable(err)
	}
	projectID, err = newID()
	if err != nil {
		return protocol.Project{}, false, unavailable(err)
	}
	now := s.now().UnixMilli()
	if _, err = tx.ExecContext(ctx, `INSERT INTO projects(id,repository_id,name,main_branch,project_type,contract_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)`, projectID, repositoryID, input.Name, input.MainBranch, input.ProjectType, string(contract), now, now); err != nil {
		return protocol.Project{}, false, unavailable(err)
	}
	if _, err = tx.ExecContext(ctx, `INSERT INTO project_runtime_readiness(project_id,updated_at) VALUES(?,?)`, projectID, now); err != nil {
		return protocol.Project{}, false, unavailable(err)
	}
	for _, environment := range input.Environments {
		if _, err = tx.ExecContext(ctx, `INSERT INTO project_environments(project_id,name,url,health_url,blocked,release_adapter,rollback_adapter) VALUES(?,?,?,?,?,?,?)`, projectID, environment.Name, environment.URL, environment.HealthURL, boolInt(environment.Blocked), environment.ReleaseAdapter, environment.RollbackAdapter); err != nil {
			return protocol.Project{}, false, unavailable(err)
		}
		for _, name := range environment.RequiredSecrets {
			if _, err = tx.ExecContext(ctx, `INSERT INTO project_required_secrets(project_id,environment,name) VALUES(?,?,?)`, projectID, environment.Name, name); err != nil {
				return protocol.Project{}, false, unavailable(err)
			}
		}
		for _, host := range environment.WebHosts {
			if _, err = tx.ExecContext(ctx, `INSERT INTO project_hosts(project_id,environment,host) VALUES(?,?,?)`, projectID, environment.Name, host); err != nil {
				return protocol.Project{}, false, unavailable(err)
			}
		}
	}
	if err := tx.Commit(); err != nil {
		return protocol.Project{}, false, unavailable(err)
	}
	project, err := s.Project(ctx, projectID)
	return project, true, err
}

func scanProjectRow(row scanner) (protocol.Project, string, error) {
	var project protocol.Project
	var contract string
	var created, updated int64
	err := row.Scan(&project.ID, &project.RepositoryID, &project.RemoteIdentity, &project.Name, &project.MainBranch, &project.ProjectType, &contract, &created, &updated)
	if err != nil {
		return project, contract, err
	}
	project.ExecutorGroup = projectPolicies[project.ProjectType].executorGroup
	project.CreatedAt, project.UpdatedAt = fromMillis(created), fromMillis(updated)
	var input protocol.CreateProjectRequest
	if err := json.Unmarshal([]byte(contract), &input); err != nil {
		return project, contract, err
	}
	project.RequiredChecks = input.RequiredChecks
	project.Environments = make([]protocol.ProjectEnvironment, len(input.Environments))
	for i, environment := range input.Environments {
		project.Environments[i] = protocol.ProjectEnvironment(environment)
	}
	return project, contract, nil
}

func (s *Store) Project(ctx context.Context, id string) (protocol.Project, error) {
	project, _, err := scanProjectRow(s.db.QueryRowContext(ctx, `SELECT p.id,p.repository_id,r.remote_identity,p.name,p.main_branch,p.project_type,p.contract_json,p.created_at,p.updated_at FROM projects p JOIN repositories r ON r.id=p.repository_id WHERE p.id=?`, strings.TrimSpace(id)))
	if errors.Is(err, sql.ErrNoRows) {
		return protocol.Project{}, ErrNotFound
	}
	if err != nil {
		return protocol.Project{}, unavailable(err)
	}
	return project, nil
}

func (s *Store) Projects(ctx context.Context) ([]protocol.Project, error) {
	rows, err := s.db.QueryContext(ctx, `SELECT p.id,p.repository_id,r.remote_identity,p.name,p.main_branch,p.project_type,p.contract_json,p.created_at,p.updated_at FROM projects p JOIN repositories r ON r.id=p.repository_id ORDER BY p.name`)
	if err != nil {
		return nil, unavailable(err)
	}
	defer rows.Close()
	projects := []protocol.Project{}
	for rows.Next() {
		project, _, err := scanProjectRow(rows)
		if err != nil {
			return nil, unavailable(err)
		}
		projects = append(projects, project)
	}
	if err := rows.Err(); err != nil {
		return nil, unavailable(err)
	}
	return projects, nil
}

func validCommitSHA(value string) bool {
	if len(value) != 40 && len(value) != 64 {
		return false
	}
	_, err := hex.DecodeString(value)
	return err == nil && strings.ToLower(value) == value
}

// trustedProjectGateResults is deliberately package-private: check results may
// only enter readiness from a server-controlled verifier, never from project API input.
type trustedProjectGateResults struct {
	workerID      string
	mainBranch    string
	branchHeadSHA string
	commitSHA     string
	checks        map[string]bool
	webHosts      []string
}

func (s *Store) RecordProjectVerification(ctx context.Context, workerID, projectID string, input protocol.ProjectVerificationRequest) error {
	project, err := s.Project(ctx, projectID)
	if err != nil {
		return err
	}
	if input.Environment != "staging" {
		return invalid("invalid_environment", "v1 verification is available only for staging")
	}
	if input.MainBranch != project.MainBranch || input.MainBranch == "" {
		return invalid("main_branch_not_verified", "the worker did not verify the configured main branch")
	}
	if !validCommitSHA(input.BranchHeadSHA) || input.BranchHeadSHA != input.CommitSHA {
		return invalid("commit_not_on_main_branch", "the verified commit must be the current head of the configured main branch")
	}
	managed, err := s.ManagedRepositoryReadiness(ctx, project.RepositoryID)
	if err != nil {
		return err
	}
	workerReady := false
	for _, worker := range managed.Workers {
		if worker.ID == workerID && worker.Ready {
			workerReady = true
			break
		}
	}
	if !workerReady {
		return conflict("worker_not_ready", "the reporting worker is not ready for this project repository")
	}
	environment, err := environmentFor(project, input.Environment)
	if err != nil {
		return err
	}
	hosts := append([]string(nil), input.WebHosts...)
	sort.Strings(hosts)
	if !slices.Equal(hosts, environment.WebHosts) {
		return invalid("web_hosts_not_applied", "the worker did not apply the project's exact web host allowlist")
	}
	return s.recordTrustedProjectGateResults(ctx, projectID, trustedProjectGateResults{
		workerID: workerID, mainBranch: input.MainBranch, branchHeadSHA: input.BranchHeadSHA,
		commitSHA: input.CommitSHA, checks: input.Checks, webHosts: hosts,
	})
}

func (s *Store) recordTrustedProjectGateResults(ctx context.Context, projectID string, input trustedProjectGateResults) error {
	if !validCommitSHA(input.commitSHA) {
		return invalid("invalid_commit_sha", "commit_sha must be a lowercase 40 or 64 character hexadecimal SHA")
	}
	if len(input.checks) != len(requiredProjectChecks) {
		return invalid("invalid_project_checks", "all four required checks must be reported together")
	}
	for _, gate := range requiredProjectChecks {
		if _, ok := input.checks[gate]; !ok {
			return invalid("invalid_project_checks", "all four required checks must be reported together")
		}
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return unavailable(err)
	}
	defer tx.Rollback()
	now := s.now().UnixMilli()
	encodedHosts, err := json.Marshal(input.webHosts)
	if err != nil {
		return invalid("invalid_web_hosts", "web_hosts could not be encoded")
	}
	result, err := tx.ExecContext(ctx, `UPDATE project_runtime_readiness SET worker_id=?,main_branch=?,branch_head_sha=?,commit_sha=?,web_hosts_json=?,updated_at=? WHERE project_id=?`, input.workerID, input.mainBranch, input.branchHeadSHA, input.commitSHA, encodedHosts, now, projectID)
	if err != nil {
		return unavailable(err)
	}
	if count, _ := result.RowsAffected(); count == 0 {
		return ErrNotFound
	}
	for _, gate := range requiredProjectChecks {
		if _, err = tx.ExecContext(ctx, `INSERT INTO project_gate_results(project_id,gate,commit_sha,passed,checked_at) VALUES(?,?,?,?,?) ON CONFLICT(project_id,gate) DO UPDATE SET commit_sha=excluded.commit_sha,passed=excluded.passed,checked_at=excluded.checked_at`, projectID, gate, input.commitSHA, boolInt(input.checks[gate]), now); err != nil {
			return unavailable(err)
		}
	}
	if err := tx.Commit(); err != nil {
		return unavailable(err)
	}
	return nil
}

func gate(name string, ready bool, reason, sha string, checked int64) protocol.ProjectGate {
	result := protocol.ProjectGate{Name: name, Ready: ready, Reason: reason, CommitSHA: sha}
	if checked > 0 {
		result.CheckedAt = fromMillis(checked)
	}
	return result
}

type projectVerificationState struct {
	workerID      string
	mainBranch    string
	branchHeadSHA string
	commitSHA     string
	webHosts      []string
	updatedAt     int64
}

func (s *Store) projectDatabaseReadiness(ctx context.Context, project protocol.Project) (protocol.SecureProjectReadiness, projectVerificationState, error) {
	var workerID, mainBranch, branchHeadSHA, sha, encodedHosts string
	var updated int64
	if err := s.db.QueryRowContext(ctx, `SELECT worker_id,main_branch,branch_head_sha,commit_sha,web_hosts_json,updated_at FROM project_runtime_readiness WHERE project_id=?`, project.ID).Scan(&workerID, &mainBranch, &branchHeadSHA, &sha, &encodedHosts, &updated); err != nil {
		return protocol.SecureProjectReadiness{}, projectVerificationState{}, unavailable(err)
	}
	state := projectVerificationState{workerID: workerID, mainBranch: mainBranch, branchHeadSHA: branchHeadSHA, commitSHA: sha, updatedAt: updated}
	if err := json.Unmarshal([]byte(encodedHosts), &state.webHosts); err != nil {
		return protocol.SecureProjectReadiness{}, state, unavailable(err)
	}
	result := protocol.SecureProjectReadiness{Ready: true, CommitSHA: sha}
	rows, err := s.db.QueryContext(ctx, `SELECT gate,commit_sha,passed,checked_at FROM project_gate_results WHERE project_id=?`, project.ID)
	if err != nil {
		return result, state, unavailable(err)
	}
	defer rows.Close()
	found := map[string]protocol.ProjectGate{}
	for rows.Next() {
		var name, checkSHA string
		var passed int
		var checked int64
		if err := rows.Scan(&name, &checkSHA, &passed, &checked); err != nil {
			return result, state, unavailable(err)
		}
		ready := passed != 0 && checkSHA == sha && sha != "" && projectCheckFresh(fromMillis(checked), s.now())
		reason := "check is missing, stale, failed, or belongs to another commit"
		found[name] = gate(name, ready, reason, checkSHA, checked)
	}
	for _, name := range requiredProjectChecks {
		item, ok := found[name]
		if !ok {
			item = gate(name, false, "check result is missing", "", 0)
		}
		result.Gates = append(result.Gates, item)
	}
	for _, item := range result.Gates {
		if !item.Ready {
			result.Ready = false
			if result.RoutingReason == "" {
				result.RoutingReason = item.Reason
			}
		}
	}
	return result, state, rows.Err()
}

func (s *Store) ProjectReadiness(ctx context.Context, projectID, environment string) (protocol.SecureProjectReadiness, error) {
	project, err := s.Project(ctx, projectID)
	if err != nil {
		return protocol.SecureProjectReadiness{}, err
	}
	if environment == "" {
		environment = "staging"
	}
	found := false
	for _, candidate := range project.Environments {
		if candidate.Name == environment {
			found = true
			break
		}
	}
	if !found {
		return protocol.SecureProjectReadiness{}, ErrNotFound
	}
	result, verification, err := s.projectDatabaseReadiness(ctx, project)
	if err != nil {
		return result, err
	}
	managed, err := s.ManagedRepositoryReadiness(ctx, project.RepositoryID)
	if err != nil {
		return result, err
	}
	workerReady := false
	workerReason := "the worker that verified this project is not healthy, online, and ready for its repository"
	for _, worker := range managed.Workers {
		if worker.ID == verification.workerID && worker.Ready {
			workerReady = true
			workerReason = "the concrete verifying worker is healthy, online, and ready"
			break
		}
		if worker.ID == verification.workerID && worker.Reason != "" {
			workerReason = worker.Reason
		}
	}
	branchReady := workerReady && verification.mainBranch == project.MainBranch &&
		verification.branchHeadSHA == verification.commitSHA && validCommitSHA(verification.commitSHA) &&
		projectCheckFresh(fromMillis(verification.updatedAt), s.now())
	branchReason := "configured main branch is missing, stale, or the verified commit is not its head"
	if branchReady {
		branchReason = "configured main branch exists and the verified commit is its head"
	}
	environmentContract, _ := environmentFor(project, environment)
	hostsReady := branchReady && slices.Equal(verification.webHosts, environmentContract.WebHosts)
	hostsReason := "the exact project web host allowlist was not applied by the verifier"
	if hostsReady {
		hostsReason = "the exact project web host allowlist is applied"
	}
	checked := verification.updatedAt
	serverGates := []protocol.ProjectGate{
		gate("branch-access", branchReady, branchReason, result.CommitSHA, checked),
		gate("executor", workerReady, workerReason, result.CommitSHA, checked),
		gate("web-hosts", hostsReady, hostsReason, result.CommitSHA, checked),
	}
	result.Gates = append(serverGates, result.Gates...)
	if !branchReady || !workerReady || !hostsReady {
		result.Ready = false
		result.RoutingReason = branchReason
		if branchReady && !workerReady {
			result.RoutingReason = workerReason
		}
		if branchReady && workerReady && !hostsReady {
			result.RoutingReason = hostsReason
		}
	}
	statuses, secretErr := s.ResolveProjectSecrets(project, environment)
	result.Secrets = statuses
	if secretErr != nil {
		result.Ready = false
		if result.RoutingReason == "" {
			result.RoutingReason = secretErr.Error()
		}
	}
	return result, nil
}

func (s *Store) requireProjectRoutingReady(ctx context.Context, repositoryID, workerID string) error {
	var projectID string
	err := s.db.QueryRowContext(ctx, `SELECT id FROM projects WHERE repository_id=?`, repositoryID).Scan(&projectID)
	if errors.Is(err, sql.ErrNoRows) {
		return nil
	}
	if err != nil {
		return unavailable(err)
	}
	readiness, err := s.ProjectReadiness(ctx, projectID, "staging")
	if err != nil {
		return err
	}
	if !readiness.Ready {
		return conflict("project_not_ready", fmt.Sprintf("safe project readiness is closed: %s", readiness.RoutingReason))
	}
	var verifiedWorkerID string
	if err := s.db.QueryRowContext(ctx, `SELECT worker_id FROM project_runtime_readiness WHERE project_id=?`, projectID).Scan(&verifiedWorkerID); err != nil {
		return unavailable(err)
	}
	if verifiedWorkerID != workerID {
		return conflict("project_worker_not_verified", "the assigned worker did not produce the trusted project verification")
	}
	return nil
}

func (s *Store) verifiedProjectWorker(ctx context.Context, repositoryID string) (string, bool, error) {
	var workerID string
	err := s.db.QueryRowContext(ctx, `
		SELECT readiness.worker_id
		FROM projects project
		JOIN project_runtime_readiness readiness ON readiness.project_id=project.id
		WHERE project.repository_id=?
	`, repositoryID).Scan(&workerID)
	if errors.Is(err, sql.ErrNoRows) {
		return "", false, nil
	}
	if err != nil {
		return "", false, unavailable(err)
	}
	return workerID, true, nil
}

func projectCheckFresh(checked time.Time, now time.Time) bool {
	return !checked.IsZero() && now.Sub(checked) <= 24*time.Hour
}
