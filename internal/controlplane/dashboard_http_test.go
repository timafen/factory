package controlplane

import (
	"net/http"
	"os"
	"path/filepath"
	"testing"
)

func TestDashboardCountsRunningWork(t *testing.T) {
	home := t.TempDir()
	t.Setenv("FACTORY_DATA_HOME", home)
	if err := os.MkdirAll(filepath.Join(home, "pilot"), 0o755); err != nil {
		t.Fatal(err)
	}
	data := []byte(`{"now":{"running":[{"id":"one","title":"First"},{"id":"two","title":"Second"}]}}`)
	if err := os.WriteFile(filepath.Join(home, "pilot", "dashboard.json"), data, 0o600); err != nil {
		t.Fatal(err)
	}

	fixture := newHTTPFixture(t)
	response := fixture.request(http.MethodGet, "/api/v1/dashboard", "", "", nil)
	requireStatus(t, response, http.StatusOK)
	dashboard := decodeResponse[struct {
		Now struct {
			RunningCount int `json:"running_count"`
		} `json:"now"`
	}](t, response)
	if dashboard.Now.RunningCount != 2 {
		t.Fatalf("running_count = %d, want 2", dashboard.Now.RunningCount)
	}
}
