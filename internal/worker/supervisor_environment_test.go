package worker

import (
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
	for _, entry := range runtimeEnvironment(worktree) {
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
