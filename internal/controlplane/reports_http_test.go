package controlplane

import (
	"crypto/sha256"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestDailyReportDownloadSelectsTimezoneAndVerifiesSHA256(t *testing.T) {
	store := newTestStore(t)
	store.reportRoot = t.TempDir()
	now := time.Now().UTC().Format(time.RFC3339Nano)
	for _, item := range []struct{ zone, name, body string }{
		{"America/Chicago", "chicago.pdf", "%PDF-chicago"},
		{"UTC", "utc.pdf", "%PDF-utc"},
	} {
		if err := os.WriteFile(filepath.Join(store.reportRoot, item.name), []byte(item.body), 0o600); err != nil {
			t.Fatal(err)
		}
		hash := fmt.Sprintf("%x", sha256.Sum256([]byte(item.body)))
		if _, err := store.db.Exec(`INSERT INTO daily_reports(report_date,timezone,status,pdf_path,pdf_sha256,pdf_size,created_at,updated_at) VALUES('2026-08-12',?,'ready',?,?,?,?,?)`, item.zone, item.name, hash, len(item.body), now, now); err != nil {
			t.Fatal(err)
		}
	}
	api := &API{store: store}
	request := httptest.NewRequest(http.MethodGet, "/api/v1/reports/daily/2026-08-12/pdf?timezone=America%2FChicago", nil)
	request.SetPathValue("date", "2026-08-12")
	response := httptest.NewRecorder()
	api.downloadDailyReport(response, request)
	if response.Code != http.StatusOK || response.Body.String() != "%PDF-chicago" {
		t.Fatalf("download status=%d body=%q", response.Code, response.Body.String())
	}
	if err := os.WriteFile(filepath.Join(store.reportRoot, "chicago.pdf"), []byte("%PDF-tampered"), 0o600); err != nil {
		t.Fatal(err)
	}
	response = httptest.NewRecorder()
	api.downloadDailyReport(response, request)
	if response.Code != http.StatusConflict {
		t.Fatalf("tampered status=%d", response.Code)
	}
}
