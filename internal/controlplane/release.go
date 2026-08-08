package controlplane

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"strings"
	"time"

	"github.com/owainlewis/factory/internal/buildinfo"
	"github.com/owainlewis/factory/internal/protocol"
)

const (
	releaseGitTimeout    = 5 * time.Second
	releaseProbeTimeout  = 4 * time.Second
	defaultReleaseBranch = "main"
)

// getDashboard reports what commit is on the main branch versus what is
// actually running on staging and prod, so the operator can see release
// drift without checking by hand.
func (a *API) getDashboard(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, protocol.DashboardSummary{Release: buildReleaseInfo(r.Context())})
}

// getVersion lets any Factory deployment self-report its own build, so a
// dashboard elsewhere can learn what commit that deployment is running.
func (a *API) getVersion(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, protocol.VersionInfo{Version: buildinfo.Version, Commit: buildinfo.Commit})
}

func buildReleaseInfo(ctx context.Context) protocol.ReleaseInfo {
	root := releaseSourceRoot()
	info := protocol.ReleaseInfo{}

	if head, subject, err := gitLogOne(ctx, root, releaseMainBranch()); err == nil {
		info.MainHead = &head
		info.MainSubject = &subject
	}

	info.StagingRelease, info.StagingHealth = probeRelease(ctx, os.Getenv("FACTORY_RELEASE_STAGING_URL"))
	info.ProdRelease, info.ProdHealth = probeRelease(ctx, os.Getenv("FACTORY_RELEASE_PROD_URL"))

	if info.MainHead != nil {
		info.StagingInMain, _ = commitAncestry(ctx, root, *info.MainHead, info.StagingRelease)
		info.ProdInMain, info.ProdCommitKnown = commitAncestry(ctx, root, *info.MainHead, info.ProdRelease)
	}

	return info
}

func releaseSourceRoot() string {
	if value := strings.TrimSpace(os.Getenv("FACTORY_RELEASE_SOURCE_ROOT")); value != "" {
		return value
	}
	if wd, err := os.Getwd(); err == nil {
		return wd
	}
	return "."
}

func releaseMainBranch() string {
	if value := strings.TrimSpace(os.Getenv("FACTORY_RELEASE_MAIN_BRANCH")); value != "" {
		return value
	}
	return defaultReleaseBranch
}

// commitAncestry reports whether release is reachable from mainHead in the
// local checkout, and whether the release commit is known there at all
// (prod may be running a commit this checkout never fetched).
func commitAncestry(
	ctx context.Context, root, mainHead string, release *protocol.ReleaseCommit,
) (inMain *bool, known *bool) {
	if release == nil || release.Commit == nil || strings.TrimSpace(*release.Commit) == "" {
		return nil, nil
	}
	commit := *release.Commit
	if !gitCommitExists(ctx, root, commit) {
		unknown := false
		return nil, &unknown
	}
	knownTrue := true
	ancestor := gitIsAncestor(ctx, root, commit, mainHead)
	return &ancestor, &knownTrue
}

func gitLogOne(ctx context.Context, root, ref string) (sha string, subject string, err error) {
	out, err := runGit(ctx, root, "log", "-1", "--format=%H%x1f%s", ref)
	if err != nil {
		out, err = runGit(ctx, root, "log", "-1", "--format=%H%x1f%s", "origin/"+ref)
		if err != nil {
			return "", "", err
		}
	}
	sha, subject, ok := strings.Cut(strings.TrimSpace(out), "\x1f")
	if !ok {
		return "", "", errMalformedGitOutput
	}
	return sha, subject, nil
}

func gitCommitExists(ctx context.Context, root, commit string) bool {
	_, err := runGit(ctx, root, "cat-file", "-e", commit+"^{commit}")
	return err == nil
}

func gitIsAncestor(ctx context.Context, root, commit, ref string) bool {
	_, err := runGit(ctx, root, "merge-base", "--is-ancestor", commit, ref)
	return err == nil
}

var errMalformedGitOutput = &ServiceError{Code: "internal_error", Message: "unexpected git output", Status: 500}

func runGit(ctx context.Context, root string, args ...string) (string, error) {
	ctx, cancel := context.WithTimeout(ctx, releaseGitTimeout)
	defer cancel()
	cmd := exec.CommandContext(ctx, "git", args...)
	cmd.Dir = root
	var stdout bytes.Buffer
	cmd.Stdout = &stdout
	if err := cmd.Run(); err != nil {
		return "", err
	}
	return stdout.String(), nil
}

func probeRelease(ctx context.Context, baseURL string) (*protocol.ReleaseCommit, *bool) {
	baseURL = strings.TrimSpace(baseURL)
	if baseURL == "" {
		return nil, nil
	}
	target, err := url.Parse(strings.TrimRight(baseURL, "/") + "/api/v1/version")
	if err != nil || (target.Scheme != "http" && target.Scheme != "https") || target.Host == "" {
		return nil, nil
	}

	ctx, cancel := context.WithTimeout(ctx, releaseProbeTimeout)
	defer cancel()
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, target.String(), nil)
	if err != nil {
		return nil, nil
	}
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		unhealthy := false
		return nil, &unhealthy
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		unhealthy := false
		return nil, &unhealthy
	}
	healthy := true

	var payload protocol.VersionInfo
	if err := json.NewDecoder(io.LimitReader(response.Body, 1<<16)).Decode(&payload); err != nil {
		return nil, &healthy
	}
	commit := strings.TrimSpace(payload.Commit)
	if commit == "" {
		return nil, &healthy
	}
	return &protocol.ReleaseCommit{Commit: &commit}, &healthy
}
