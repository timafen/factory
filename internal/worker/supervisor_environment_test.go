package worker

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestRuntimeEnvironmentIsolatesAgentBuildsFromLiveFactory(t *testing.T) {
	worktree := t.TempDir()
	t.Setenv("FACTORY_DATA_HOME", "/opt/factory-data")
	t.Setenv("FACTORY_V2_DATA_HOME", "/opt/factory-v2")
	t.Setenv("FACTORY_BUILD_DIR", "/opt/factory-data/bin")
	t.Setenv("FACTORY_V2_BUILD_DIR", "/opt/factory-v2/bin")
	t.Setenv("FACTORY_WORKER_CONFIG", "/opt/factory-data/worker.toml")
	t.Setenv("FACTORY_V2_WORKER_CONFIG", "/opt/factory-v2/worker.toml")
	t.Setenv("FACTORY_TEST_RUNTIME_SENTINEL", "preserved")

	values := map[string]string{}
	for _, entry := range runtimeEnvironment(worktree, "") {
		name, value, _ := strings.Cut(entry, "=")
		values[name] = value
	}

	if got := values["FACTORY_BUILD_DIR"]; got != filepath.Join(worktree, ".factory-build") {
		t.Fatalf("FACTORY_BUILD_DIR = %q", got)
	}
	for _, name := range []string{
		"FACTORY_DATA_HOME", "FACTORY_V2_DATA_HOME", "FACTORY_V2_BUILD_DIR",
		"FACTORY_WORKER_CONFIG", "FACTORY_V2_WORKER_CONFIG",
	} {
		if _, present := values[name]; present {
			t.Fatalf("service-only %s leaked into the agent environment", name)
		}
	}
	if values["FACTORY_TEST_RUNTIME_SENTINEL"] != "preserved" {
		t.Fatal("ordinary runtime environment was not preserved")
	}
	if values["LANG"] != runtimeUTF8Locale || values["LC_ALL"] != runtimeUTF8Locale {
		t.Fatal("UTF-8 locale was not preserved")
	}
}

func TestRuntimeEnvironmentGitHubRepositoryPolicy(t *testing.T) {
	t.Setenv("GH_REPO", "owainlewis/factory")
	tests := []struct {
		name     string
		identity string
		want     string
	}{
		{name: "github", identity: "GitHub.com/Example/Cattle", want: "example/cattle"},
		{name: "assigned factory repository", identity: "github.com/timafen/factory", want: "timafen/factory"},
		{name: "empty"},
		{name: "too few segments", identity: "github.com/example"},
		{name: "too many segments", identity: "github.com/example/cattle/extra"},
		{name: "invalid owner", identity: "github.com/-example/cattle"},
		{name: "invalid repository", identity: "github.com/example/cattle!"},
		{name: "file", identity: "file:///tmp/cattle"},
		{name: "gitlab", identity: "gitlab.com/example/cattle"},
		{name: "self hosted", identity: "github.example.com/example/cattle"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			var values []string
			for _, entry := range runtimeEnvironment(t.TempDir(), test.identity) {
				if strings.HasPrefix(entry, "GH_REPO=") {
					values = append(values, strings.TrimPrefix(entry, "GH_REPO="))
				}
			}
			if test.want == "" && len(values) != 0 {
				t.Fatalf("GH_REPO leaked into runtime: %q", values)
			}
			if test.want != "" && (len(values) != 1 || values[0] != test.want) {
				t.Fatalf("GH_REPO values = %q; want [%q]", values, test.want)
			}
		})
	}
	if os.Getenv("GH_REPO") != "owainlewis/factory" {
		t.Fatal("test unexpectedly changed the service environment")
	}
}
