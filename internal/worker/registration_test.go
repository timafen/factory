package worker

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/owainlewis/factory/internal/protocol"
)

func TestWorkerRegistrationRetriesAfterCredentialWriteFailure(t *testing.T) {
	credentials := []string{strings.Repeat("a", 43), strings.Repeat("b", 43)}
	registrations := 0
	server := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		if request.Method != http.MethodPut {
			t.Fatalf("method=%s", request.Method)
		}
		credential := credentials[registrations]
		registrations++
		response.Header().Set(protocol.WorkerCredentialHeader, credential)
		response.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(response).Encode(protocol.Worker{ID: "retrying-worker", Name: "Retrying worker"})
	}))
	defer server.Close()

	dataDirectory := t.TempDir()
	credentialPath := filepath.Join(dataDirectory, workerCredentialFilename)
	if err := os.Mkdir(credentialPath, 0o700); err != nil {
		t.Fatal(err)
	}
	manager := &Manager{
		config:  Config{Name: "Retrying worker", Runtime: protocol.RuntimeCodex, MaxConcurrent: 1},
		options: Options{WorkerVersion: "test"}, logger: slog.New(slog.NewTextHandler(io.Discard, nil)),
		id: "retrying-worker", dataDirectory: dataDirectory, client: newClient(server.URL, server.Client()),
		manifests: newManifestStore(dataDirectory, "retrying-worker"), slots: make(chan struct{}, 1),
		health: health{State: "healthy", RuntimeVersion: "test"}, pending: make(map[string]context.CancelFunc),
	}

	manager.registerLocked(context.Background())
	if manager.registered || manager.fatalHealth != nil || manager.client.workerCredential() != "" {
		t.Fatalf("write failure registered=%v fatal=%v credential=%q", manager.registered, manager.fatalHealth, manager.client.workerCredential())
	}
	if err := os.Remove(credentialPath); err != nil {
		t.Fatal(err)
	}
	manager.registerLocked(context.Background())
	if !manager.registered || manager.fatalHealth != nil || manager.client.workerCredential() != credentials[1] {
		t.Fatalf("retry registered=%v fatal=%v credential=%q", manager.registered, manager.fatalHealth, manager.client.workerCredential())
	}
	stored, err := loadWorkerCredential(dataDirectory)
	if err != nil || stored != credentials[1] || registrations != 2 {
		t.Fatalf("stored=%q registrations=%d err=%v", stored, registrations, err)
	}
}
