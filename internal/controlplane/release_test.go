package controlplane

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"strings"
	"testing"

	"github.com/owainlewis/factory/internal/protocol"
)

// releaseTestRepo builds a real git repository with an actual "main" branch
// history, so the dashboard endpoint reads real commits instead of fixtures.
type releaseTestRepo struct {
	root        string
	mainHead    string
	mainSubject string
}

func newReleaseTestRepo(t *testing.T) *releaseTestRepo {
	t.Helper()
	root := t.TempDir()
	runReleaseGit(t, root, "init", "-b", "main")
	runReleaseGit(t, root, "config", "user.email", "release-test@example.com")
	runReleaseGit(t, root, "config", "user.name", "Release Test")
	writeReleaseFile(t, root, "README.md", "first")
	runReleaseGit(t, root, "add", "README.md")
	runReleaseGit(t, root, "commit", "-m", "первый коммит")
	writeReleaseFile(t, root, "README.md", "second")
	runReleaseGit(t, root, "add", "README.md")
	runReleaseGit(t, root, "commit", "-m", "актуальный коммит на главной ветке")
	head := strings.TrimSpace(runReleaseGit(t, root, "rev-parse", "HEAD"))
	return &releaseTestRepo{root: root, mainHead: head, mainSubject: "актуальный коммит на главной ветке"}
}

// olderCommit returns a commit that is an ancestor of main (simulating a
// staging deploy that lags behind main).
func (r *releaseTestRepo) olderCommit(t *testing.T) string {
	t.Helper()
	return strings.TrimSpace(runReleaseGit(t, r.root, "rev-parse", "HEAD~1"))
}

func writeReleaseFile(t *testing.T, root, name, contents string) {
	t.Helper()
	if err := os.WriteFile(root+"/"+name, []byte(contents), 0o600); err != nil {
		t.Fatal(err)
	}
}

func runReleaseGit(t *testing.T, root string, args ...string) string {
	t.Helper()
	cmd := exec.Command("git", args...)
	cmd.Dir = root
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("git %v: %v: %s", args, err, out)
	}
	return string(out)
}

func newVersionServer(t *testing.T, commit string) *httptest.Server {
	t.Helper()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/version" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(protocol.VersionInfo{Version: "test", Commit: commit})
	}))
	t.Cleanup(server.Close)
	return server
}

func TestHTTPDashboardReadsMainHeadFromLocalGit(t *testing.T) {
	repo := newReleaseTestRepo(t)
	t.Setenv("FACTORY_RELEASE_SOURCE_ROOT", repo.root)

	fixture := newHTTPFixture(t)
	response := fixture.request(http.MethodGet, "/api/v1/dashboard", "", "", nil)
	requireStatus(t, response, http.StatusOK)
	summary := decodeResponse[protocol.DashboardSummary](t, response)

	if summary.Release.MainHead == nil || *summary.Release.MainHead != repo.mainHead {
		t.Fatalf("main_head = %#v, want %s", summary.Release.MainHead, repo.mainHead)
	}
	if summary.Release.MainSubject == nil || *summary.Release.MainSubject != repo.mainSubject {
		t.Fatalf("main_subject = %#v, want %s", summary.Release.MainSubject, repo.mainSubject)
	}
	if summary.Release.StagingRelease != nil || summary.Release.StagingHealth != nil {
		t.Fatalf("staging should be unset when FACTORY_RELEASE_STAGING_URL is unset: %#v", summary.Release)
	}
	if summary.Release.ProdRelease != nil || summary.Release.ProdHealth != nil {
		t.Fatalf("prod should be unset when FACTORY_RELEASE_PROD_URL is unset: %#v", summary.Release)
	}
}

func TestHTTPDashboardProbesStagingAndProdOverRealHTTP(t *testing.T) {
	repo := newReleaseTestRepo(t)
	t.Setenv("FACTORY_RELEASE_SOURCE_ROOT", repo.root)

	staging := newVersionServer(t, repo.olderCommit(t))
	prod := newVersionServer(t, "0000000000000000000000000000000000dead")
	t.Setenv("FACTORY_RELEASE_STAGING_URL", staging.URL)
	t.Setenv("FACTORY_RELEASE_PROD_URL", prod.URL)

	fixture := newHTTPFixture(t)
	response := fixture.request(http.MethodGet, "/api/v1/dashboard", "", "", nil)
	requireStatus(t, response, http.StatusOK)
	summary := decodeResponse[protocol.DashboardSummary](t, response)
	release := summary.Release

	if release.StagingHealth == nil || !*release.StagingHealth {
		t.Fatalf("staging_health = %#v, want true (real HTTP probe reached %s)", release.StagingHealth, staging.URL)
	}
	if release.StagingRelease == nil || release.StagingRelease.Commit == nil ||
		*release.StagingRelease.Commit != repo.olderCommit(t) {
		t.Fatalf("staging_release = %#v", release.StagingRelease)
	}
	if release.StagingInMain == nil || !*release.StagingInMain {
		t.Fatalf("staging_in_main = %#v, want true: staging commit is an ancestor of main", release.StagingInMain)
	}

	if release.ProdHealth == nil || !*release.ProdHealth {
		t.Fatalf("prod_health = %#v, want true (real HTTP probe reached %s)", release.ProdHealth, prod.URL)
	}
	if release.ProdCommitKnown == nil || *release.ProdCommitKnown {
		t.Fatalf(
			"prod_commit_known = %#v, want false: prod reports a commit this checkout never fetched",
			release.ProdCommitKnown,
		)
	}
	if release.ProdInMain != nil {
		t.Fatalf("prod_in_main = %#v, want nil when the commit is unknown locally", release.ProdInMain)
	}
}

func TestHTTPDashboardMarksUnreachableEnvironmentsUnhealthy(t *testing.T) {
	repo := newReleaseTestRepo(t)
	t.Setenv("FACTORY_RELEASE_SOURCE_ROOT", repo.root)

	failing := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadGateway)
	}))
	t.Cleanup(failing.Close)
	t.Setenv("FACTORY_RELEASE_PROD_URL", failing.URL)

	fixture := newHTTPFixture(t)
	response := fixture.request(http.MethodGet, "/api/v1/dashboard", "", "", nil)
	requireStatus(t, response, http.StatusOK)
	release := decodeResponse[protocol.DashboardSummary](t, response).Release

	if release.ProdHealth == nil || *release.ProdHealth {
		t.Fatalf("prod_health = %#v, want false: the probed server returned 502", release.ProdHealth)
	}
	if release.ProdRelease != nil {
		t.Fatalf("prod_release = %#v, want nil: an unhealthy target reports no commit", release.ProdRelease)
	}
}

func TestHTTPDashboardDoesNotErrorWithoutAGitCheckout(t *testing.T) {
	t.Setenv("FACTORY_RELEASE_SOURCE_ROOT", t.TempDir())

	fixture := newHTTPFixture(t)
	response := fixture.request(http.MethodGet, "/api/v1/dashboard", "", "", nil)
	requireStatus(t, response, http.StatusOK)
	release := decodeResponse[protocol.DashboardSummary](t, response).Release

	if release.MainHead != nil {
		t.Fatalf("main_head = %#v, want nil outside a git checkout", release.MainHead)
	}
}

func TestHTTPVersionReportsBuildinfo(t *testing.T) {
	fixture := newHTTPFixture(t)
	response := fixture.request(http.MethodGet, "/api/v1/version", "", "", nil)
	requireStatus(t, response, http.StatusOK)
	version := decodeResponse[protocol.VersionInfo](t, response)
	if version.Commit == "" || version.Version == "" {
		t.Fatalf("version response = %#v, want non-empty commit and version", version)
	}
}
