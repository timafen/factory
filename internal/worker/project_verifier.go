package worker

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"syscall"

	"github.com/owainlewis/factory/internal/protocol"
)

type ProjectVerificationOptions struct {
	ProjectID     string
	RepositoryKey string
	ReportPath    string
	GitExecutable string
}

type projectCheckReport struct {
	CommitSHA string          `json:"commit_sha"`
	Checks    map[string]bool `json:"checks"`
	WebHosts  []string        `json:"web_hosts"`
}

// VerifyProject is the worker-side trusted verifier path. It binds an atomic
// check report to the configured repository's real remote main-branch head and
// sends the attestation through the worker endpoint.
func VerifyProject(ctx context.Context, config Config, options ProjectVerificationOptions) error {
	options.ProjectID = strings.TrimSpace(options.ProjectID)
	options.RepositoryKey = strings.TrimSpace(options.RepositoryKey)
	if options.ProjectID == "" || options.RepositoryKey == "" || options.ReportPath == "" {
		return errors.New("project, repository, and report are required")
	}
	if options.GitExecutable == "" {
		options.GitExecutable = "git"
	}
	repositoryConfig, ok := config.Repositories[options.RepositoryKey]
	if !ok {
		return fmt.Errorf("repository %q is not configured on this worker", options.RepositoryKey)
	}
	report, err := readTrustedProjectCheckReport(options.ReportPath)
	if err != nil {
		return err
	}
	workerID, err := ResolveWorkerID(config)
	if err != nil {
		return err
	}
	client := newClient(config.Server, nil)
	project, err := client.project(ctx, options.ProjectID)
	if err != nil {
		return fmt.Errorf("load project contract: %w", err)
	}
	repository, err := resolveRepository(options.RepositoryKey, repositoryConfig.Path, options.GitExecutable)
	if err != nil {
		return fmt.Errorf("verify configured repository: %w", err)
	}
	if !sameRemoteIdentity(repository.RemoteIdentity, project.RemoteIdentity) {
		return errors.New("configured repository remote does not match the project contract")
	}
	command := exec.CommandContext(ctx, options.GitExecutable, "-C", repository.Path, "ls-remote", "--exit-code", "origin", "refs/heads/"+project.MainBranch)
	command.Env = []string{"LANG=C.UTF-8", "LC_ALL=C.UTF-8", "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"}
	output, err := command.Output()
	if err != nil {
		return fmt.Errorf("configured main branch does not exist or is inaccessible: %w", err)
	}
	fields := bytes.Fields(output)
	if len(fields) < 2 || string(fields[1]) != "refs/heads/"+project.MainBranch {
		return errors.New("Git did not return the configured main branch")
	}
	branchHead := strings.ToLower(string(fields[0]))
	if report.CommitSHA != branchHead {
		return errors.New("check report commit is not the configured main branch head")
	}
	hosts := append([]string(nil), report.WebHosts...)
	sort.Strings(hosts)
	request := protocol.ProjectVerificationRequest{
		Environment: "staging", MainBranch: project.MainBranch, BranchHeadSHA: branchHead,
		CommitSHA: report.CommitSHA, Checks: report.Checks, WebHosts: hosts,
	}
	if err := client.verifyProject(ctx, workerID, project.ID, request); err != nil {
		return fmt.Errorf("publish project verification: %w", err)
	}
	return nil
}

func readTrustedProjectCheckReport(path string) (projectCheckReport, error) {
	absolute, err := filepath.Abs(path)
	if err != nil {
		return projectCheckReport{}, fmt.Errorf("resolve check report: %w", err)
	}
	info, err := os.Lstat(absolute)
	if err != nil {
		return projectCheckReport{}, fmt.Errorf("inspect check report: %w", err)
	}
	stat, ok := info.Sys().(*syscall.Stat_t)
	if !ok || !info.Mode().IsRegular() || info.Mode()&os.ModeSymlink != 0 || info.Mode().Perm()&0o022 != 0 || (stat.Uid != 0 && stat.Uid != uint32(os.Getuid())) {
		return projectCheckReport{}, errors.New("check report must be a trusted regular file that is not group/world writable")
	}
	body, err := os.ReadFile(absolute)
	if err != nil {
		return projectCheckReport{}, fmt.Errorf("read check report: %w", err)
	}
	var report projectCheckReport
	decoder := json.NewDecoder(bytes.NewReader(body))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&report); err != nil {
		return projectCheckReport{}, fmt.Errorf("decode check report: %w", err)
	}
	if len(report.CommitSHA) != 40 && len(report.CommitSHA) != 64 {
		return projectCheckReport{}, errors.New("check report has an invalid commit SHA")
	}
	return report, nil
}
