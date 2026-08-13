package main

import (
	"bytes"
	"context"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	"github.com/owainlewis/factory/internal/controlplane"
)

func TestBackupCLICreatesSnapshotWithoutHome(t *testing.T) {
	root := t.TempDir()
	source := filepath.Join(root, "source", "factory.sqlite3")
	store, err := controlplane.Open(context.Background(), source)
	if err != nil {
		t.Fatal(err)
	}
	if err := store.Close(); err != nil {
		t.Fatal(err)
	}
	sourceBefore, err := os.ReadFile(source)
	if err != nil {
		t.Fatal(err)
	}
	markerBefore, err := os.ReadFile(source + ".v2-control-plane")
	if err != nil {
		t.Fatal(err)
	}

	binary := filepath.Join(root, "factory-server")
	build := exec.Command("go", "build", "-o", binary, ".")
	if output, err := build.CombinedOutput(); err != nil {
		t.Fatalf("build factory-server: %v\n%s", err, output)
	}

	tests := []struct {
		name string
		args func(string) []string
	}{
		{"single-dash-separated", func(destination string) []string {
			return []string{"-database", source, "-backup", destination}
		}},
		{"double-dash-separated", func(destination string) []string {
			return []string{"--database", source, "--backup", destination}
		}},
		{"single-dash-equals", func(destination string) []string {
			return []string{"-database=" + source, "-backup=" + destination}
		}},
		{"double-dash-equals", func(destination string) []string {
			return []string{"--database=" + source, "--backup=" + destination}
		}},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			destination := filepath.Join(root, test.name+".sqlite3")
			command := exec.Command(binary, test.args(destination)...)
			command.Env = serverEnvironmentWithoutHome(filepath.Join(root, "missing-config.toml"))
			output, err := command.CombinedOutput()
			if err != nil {
				t.Fatalf("backup CLI: %v\n%s", err, output)
			}
			if want := "created Factory database backup at " + destination; !strings.Contains(string(output), want) {
				t.Fatalf("backup output = %q, want it to contain %q", output, want)
			}
			for _, path := range []string{destination, destination + ".v2-control-plane"} {
				if info, err := os.Lstat(path); err != nil || !info.Mode().IsRegular() {
					t.Fatalf("backup file %s = %#v, %v", path, info, err)
				}
			}
			for _, suffix := range []string{"-wal", "-shm"} {
				if _, err := os.Lstat(destination + suffix); !os.IsNotExist(err) {
					t.Fatalf("standalone backup has unexpected %s sidecar: %v", suffix, err)
				}
			}
			for path, before := range map[string][]byte{
				source:                       sourceBefore,
				source + ".v2-control-plane": markerBefore,
			} {
				after, err := os.ReadFile(path)
				if err != nil {
					t.Fatal(err)
				}
				if !bytes.Equal(after, before) {
					t.Fatalf("backup changed source file %s", path)
				}
			}
		})
	}
}

func serverEnvironmentWithoutHome(configPath string) []string {
	excluded := map[string]bool{
		"HOME": true, "FACTORY_DATA_HOME": true, "FACTORY_V2_DATA_HOME": true,
		"FACTORY_SERVER_CONFIG": true,
	}
	environment := make([]string, 0, len(os.Environ())+1)
	for _, entry := range os.Environ() {
		name, _, _ := strings.Cut(entry, "=")
		if !excluded[name] {
			environment = append(environment, entry)
		}
	}
	return append(environment, "FACTORY_SERVER_CONFIG="+configPath)
}

func TestBackupWithExplicitDatabaseHonorsFlagGrammar(t *testing.T) {
	tests := []struct {
		name string
		args []string
		want bool
	}{
		{"separated values", []string{"-database", "source", "-backup", "destination"}, true},
		{"equals values", []string{"--database=source", "--backup=destination"}, true},
		{"database text is another flag value", []string{"-listen", "-database", "-backup", "destination"}, false},
		{"flags after positional argument", []string{"-backup", "destination", "positional", "-database", "source"}, false},
		{"unknown flag", []string{"-unknown", "-database", "source", "-backup", "destination"}, false},
		{"repeated flags", []string{"-database", "first", "-database", "second", "-backup", "first", "-backup", "second"}, true},
		{"empty final backup", []string{"-database", "source", "-backup", "destination", "-backup="}, false},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			if got := backupWithExplicitDatabase(test.args); got != test.want {
				t.Fatalf("backupWithExplicitDatabase(%q) = %v, want %v", test.args, got, test.want)
			}
		})
	}
}

func TestBackupModeRejectsMissingSourceWithoutCreatingState(t *testing.T) {
	root := t.TempDir()
	source := filepath.Join(root, "missing", "factory.sqlite3")
	destination := filepath.Join(root, "backup", "factory.sqlite3")
	handled, err := runRecoveryMode(context.Background(), source, destination, "", io.Discard)
	if !handled || err == nil {
		t.Fatalf("missing-source backup = handled %v, error %v", handled, err)
	}
	for _, path := range []string{source, source + ".v2-control-plane", destination} {
		if _, statErr := os.Lstat(path); !os.IsNotExist(statErr) {
			t.Fatalf("missing-source CLI backup created %s: %v", path, statErr)
		}
	}
}

func TestDefaultDatabasePathUsesFactoryHome(t *testing.T) {
	home := t.TempDir()
	t.Setenv("HOME", home)
	t.Setenv("FACTORY_DATA_HOME", "")
	t.Setenv("FACTORY_V2_DATA_HOME", "")

	database, root, err := defaultDatabasePath()
	if err != nil {
		t.Fatal(err)
	}
	wantRoot := filepath.Join(home, ".factory")
	if root != wantRoot {
		t.Fatalf("root = %q, want %q", root, wantRoot)
	}
	if want := filepath.Join(wantRoot, "server", "factory.sqlite3"); database != want {
		t.Fatalf("database = %q, want %q", database, want)
	}
}

func TestDefaultDatabasePathHonorsOverride(t *testing.T) {
	root := t.TempDir()
	t.Setenv("FACTORY_DATA_HOME", root)

	database, gotRoot, err := defaultDatabasePath()
	if err != nil {
		t.Fatal(err)
	}
	if gotRoot != root {
		t.Fatalf("root = %q, want %q", gotRoot, root)
	}
	if want := filepath.Join(root, "server", "factory.sqlite3"); database != want {
		t.Fatalf("database = %q, want %q", database, want)
	}
}

func TestDefaultDatabasePathHonorsPreviewAlias(t *testing.T) {
	root := t.TempDir()
	t.Setenv("FACTORY_DATA_HOME", "")
	t.Setenv("FACTORY_V2_DATA_HOME", root)

	database, gotRoot, err := defaultDatabasePath()
	if err != nil {
		t.Fatal(err)
	}
	if gotRoot != root {
		t.Fatalf("root = %q, want %q", gotRoot, root)
	}
	if want := filepath.Join(root, "server", "factory.sqlite3"); database != want {
		t.Fatalf("database = %q, want %q", database, want)
	}
}

func TestDefaultReportRuntimeLivesUnderFactoryDataRoot(t *testing.T) {
	root := t.TempDir()
	capture, renderer, err := controlplane.MaterializeReportScripts(filepath.Join(root, "reports"))
	if err != nil {
		t.Fatal(err)
	}
	for _, script := range []string{capture, renderer} {
		if !filepath.IsAbs(script) || !strings.HasPrefix(script, filepath.Join(root, "reports")+string(filepath.Separator)) {
			t.Fatalf("embedded report script=%q", script)
		}
		if info, err := os.Stat(script); err != nil || !info.Mode().IsRegular() {
			t.Fatalf("script info=%v err=%v", info, err)
		}
	}
}

func TestServerBootstrapConfigIsOptionalAndResolvesRelativeDatabase(t *testing.T) {
	dataRoot := t.TempDir()
	t.Setenv("FACTORY_SERVER_CONFIG", "")

	config, err := loadServerBootstrapConfig(dataRoot)
	if err != nil {
		t.Fatal(err)
	}
	if config.Listen != "" || config.Database != "" || config.path != filepath.Join(dataRoot, "config.toml") {
		t.Fatalf("missing optional config = %#v", config)
	}

	path := filepath.Join(dataRoot, "config.toml")
	if err := os.WriteFile(path, []byte("listen = \"127.0.0.1:7447\"\ndatabase = \"state/factory.sqlite3\"\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	config, err = loadServerBootstrapConfig(dataRoot)
	if err != nil {
		t.Fatal(err)
	}
	if config.Listen != "127.0.0.1:7447" || config.Database != filepath.Join(dataRoot, "state", "factory.sqlite3") {
		t.Fatalf("loaded config = %#v", config)
	}
}

func TestServerBootstrapConfigRejectsUnknownFieldsAndSymlinks(t *testing.T) {
	dataRoot := t.TempDir()
	path := filepath.Join(dataRoot, "config.toml")
	t.Setenv("FACTORY_SERVER_CONFIG", path)
	if err := os.WriteFile(path, []byte("listen = \"127.0.0.1:7337\"\nprovider = \"github\"\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := loadServerBootstrapConfig(dataRoot); err == nil || !strings.Contains(err.Error(), "unknown Factory server configuration fields: provider") {
		t.Fatalf("unknown field error = %v", err)
	}

	target := filepath.Join(dataRoot, "target.toml")
	if err := os.WriteFile(target, []byte("listen = \"127.0.0.1:7337\"\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.Remove(path); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(target, path); err != nil {
		t.Fatal(err)
	}
	if _, err := loadServerBootstrapConfig(dataRoot); err == nil || !strings.Contains(err.Error(), "regular non-symlink") {
		t.Fatalf("symlink error = %v", err)
	}
}

func TestValidateNoLegacyServerDefaultRefusesLegacyState(t *testing.T) {
	home := t.TempDir()
	t.Setenv("HOME", home)
	t.Setenv("FACTORY_DATA_HOME", "")
	t.Setenv("FACTORY_V2_DATA_HOME", "")
	legacyRoot := filepath.Join(home, ".factory-v2")
	legacyDatabase := filepath.Join(legacyRoot, "server", "factory.sqlite3")
	if err := os.MkdirAll(filepath.Dir(legacyDatabase), 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(legacyDatabase, []byte("legacy"), 0o600); err != nil {
		t.Fatal(err)
	}

	newRoot := filepath.Join(home, ".factory")
	err := validateNoLegacyServerDefault(newRoot)
	if err == nil {
		t.Fatal("preview server state was accepted")
	}
	for _, want := range []string{legacyDatabase, "FACTORY_DATA_HOME=" + legacyRoot} {
		if !strings.Contains(err.Error(), want) {
			t.Fatalf("error %q does not contain %q", err, want)
		}
	}
	if err := validateLegacyServerSelection("", true, newRoot); err != nil {
		t.Fatalf("explicit database selection was blocked: %v", err)
	}
	if err := validateLegacyServerSelection(legacyRoot, false, newRoot); err != nil {
		t.Fatalf("explicit data home was blocked: %v", err)
	}

	t.Setenv("FACTORY_DATA_HOME", legacyRoot)
	database, root, err := defaultDatabasePath()
	if err != nil {
		t.Fatalf("explicit legacy root: %v", err)
	}
	if root != legacyRoot || database != legacyDatabase {
		t.Fatalf("explicit legacy paths = %q, %q", root, database)
	}

	currentDatabase := filepath.Join(newRoot, "server", "factory.sqlite3")
	if err := os.MkdirAll(filepath.Dir(currentDatabase), 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(currentDatabase, []byte("current"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := validateNoLegacyServerDefault(newRoot); err != nil {
		t.Fatalf("preview state overrode current default: %v", err)
	}
}

func TestValidateDataRootRefusesRetiredStateAncestor(t *testing.T) {
	retiredRoot := t.TempDir()
	marker := filepath.Join(retiredRoot, "factory.sqlite3")
	if err := os.WriteFile(marker, []byte("retired"), 0o600); err != nil {
		t.Fatal(err)
	}
	dataRoot := filepath.Join(retiredRoot, "nested", "control-plane")

	err := validateDataRoot(dataRoot)
	if err == nil || !strings.Contains(err.Error(), "below retired local state") {
		t.Fatalf("validate data root error = %v", err)
	}
	if _, err := os.Lstat(filepath.Join(retiredRoot, "nested")); !os.IsNotExist(err) {
		t.Fatalf("validation mutated retired root: %v", err)
	}
}

func TestValidateDataRootRefusesSymlinkedRetiredStateAncestor(t *testing.T) {
	retiredRoot := t.TempDir()
	if err := os.WriteFile(filepath.Join(retiredRoot, "factory.sqlite3"), []byte("retired"), 0o600); err != nil {
		t.Fatal(err)
	}
	link := filepath.Join(t.TempDir(), "linked-retired")
	if err := os.Symlink(retiredRoot, link); err != nil {
		t.Fatal(err)
	}

	err := validateDataRoot(filepath.Join(link, "nested", "control-plane"))
	if err == nil || !strings.Contains(err.Error(), "below retired local state") {
		t.Fatalf("validate symlinked data root error = %v", err)
	}
}

func TestValidateDataRootAllowsSeparatePath(t *testing.T) {
	if err := validateDataRoot(filepath.Join(t.TempDir(), "nested", "control-plane")); err != nil {
		t.Fatalf("validate separate data root: %v", err)
	}
}

func TestValidateDataRootAllowsRetiredRepositorySibling(t *testing.T) {
	root := filepath.Join(t.TempDir(), ".factory")
	retiredRepositoryRoot := filepath.Join(root, "0123456789abcdef0123")
	if err := os.MkdirAll(retiredRepositoryRoot, 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(retiredRepositoryRoot, "factory.sqlite3"), []byte("retired"), 0o600); err != nil {
		t.Fatal(err)
	}

	if err := validateDataRoot(root); err != nil {
		t.Fatalf("validate shared Factory home with isolated retired sibling: %v", err)
	}
}
