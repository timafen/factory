package worker

import (
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/owainlewis/factory/internal/protocol"
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

func TestWorkerCredentialSaveFailureCanBeRetriedWithRotatedCredential(t *testing.T) {
	root := t.TempDir()
	directory := filepath.Join(root, "temporarily-missing")
	firstRotation := strings.Repeat("a", 43)
	if err := saveWorkerCredential(directory, firstRotation); err == nil {
		t.Fatal("credential save unexpectedly succeeded without its data directory")
	}
	if err := os.Mkdir(directory, 0o700); err != nil {
		t.Fatal(err)
	}
	secondRotation := strings.Repeat("b", 43)
	if err := saveWorkerCredential(directory, secondRotation); err != nil {
		t.Fatalf("retry after credential write failure: %v", err)
	}
	loaded, err := loadWorkerCredential(directory)
	if err != nil || loaded != secondRotation {
		t.Fatalf("loaded credential=%q err=%v", loaded, err)
	}
}

func TestClaimSendsWorkerCredential(t *testing.T) {
	credential := strings.Repeat("c", 43)
	server := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		if got := request.Header.Get(protocol.WorkerCredentialHeader); got != credential {
			t.Errorf("claim credential = %q", got)
		}
		response.WriteHeader(http.StatusNoContent)
	}))
	defer server.Close()

	apiClient := newClient(server.URL, server.Client())
	apiClient.setWorkerCredential(credential)
	claim, err := apiClient.claim(context.Background(), "worker-a", protocol.ClaimRequest{
		RequestID: "claim-with-credential", LeaseToken: "lease-token",
	}, time.Millisecond, time.Millisecond)
	if err != nil || claim != nil {
		t.Fatalf("claim = %#v, err = %v", claim, err)
	}
}
