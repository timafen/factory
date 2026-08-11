package worker

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestWorkerCredentialPersistsWithRestrictedPermissions(t *testing.T) {
	directory := t.TempDir()
	credential := strings.Repeat("c", 43)
	if err := saveWorkerCredential(directory, credential); err != nil {
		t.Fatal(err)
	}
	loaded, err := loadWorkerCredential(directory)
	if err != nil || loaded != credential {
		t.Fatalf("loaded credential = %q, err=%v", loaded, err)
	}
	info, err := os.Lstat(filepath.Join(directory, workerCredentialFilename))
	if err != nil {
		t.Fatal(err)
	}
	if info.Mode().Perm() != 0o600 {
		t.Fatalf("credential mode = %o", info.Mode().Perm())
	}
}

func TestWorkerCredentialRejectsSymlinkAndOpenPermissions(t *testing.T) {
	for name, prepare := range map[string]func(string) error{
		"symlink": func(path string) error {
			target := path + "-target"
			if err := os.WriteFile(target, []byte(strings.Repeat("c", 43)+"\n"), 0o600); err != nil {
				return err
			}
			return os.Symlink(target, path)
		},
		"open permissions": func(path string) error {
			return os.WriteFile(path, []byte(strings.Repeat("c", 43)+"\n"), 0o644)
		},
	} {
		t.Run(name, func(t *testing.T) {
			directory := t.TempDir()
			if err := prepare(filepath.Join(directory, workerCredentialFilename)); err != nil {
				t.Fatal(err)
			}
			if _, err := loadWorkerCredential(directory); err == nil {
				t.Fatal("unsafe credential file was accepted")
			}
		})
	}
}
