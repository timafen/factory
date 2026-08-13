package controlplane

import (
	"bytes"
	"crypto/sha256"
	"crypto/subtle"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"time"
)

func (api *API) listDailyReports(w http.ResponseWriter, r *http.Request) {
	reports, err := api.store.ListDailyReports(r.Context())
	if err != nil {
		writeError(w, err)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(reports)
}

func (api *API) downloadDailyReport(w http.ResponseWriter, r *http.Request) {
	date := r.PathValue("date")
	timezone := r.URL.Query().Get("timezone")
	if timezone == "" {
		http.Error(w, "timezone is required", http.StatusBadRequest)
		return
	}
	var status, path, hash string
	var size int64
	err := api.store.db.QueryRowContext(r.Context(), `SELECT status,pdf_path,pdf_sha256,pdf_size FROM daily_reports WHERE report_date=? AND timezone=?`, date, timezone).Scan(&status, &path, &hash, &size)
	if errors.Is(err, sql.ErrNoRows) || status != "ready" {
		http.NotFound(w, r)
		return
	}
	if err != nil || filepath.Base(path) != path || path == "" {
		http.Error(w, "report unavailable", http.StatusConflict)
		return
	}
	content, err := os.ReadFile(filepath.Join(api.store.reportRoot, path))
	if err != nil {
		http.NotFound(w, r)
		return
	}
	actualHash := fmt.Sprintf("%x", sha256.Sum256(content))
	if int64(len(content)) != size || hash == "" || subtle.ConstantTimeCompare([]byte(actualHash), []byte(hash)) != 1 {
		http.Error(w, "report incomplete", http.StatusConflict)
		return
	}
	w.Header().Set("Content-Type", "application/pdf")
	w.Header().Set("Content-Disposition", `attachment; filename="daily-report-`+date+`.pdf"`)
	http.ServeContent(w, r, path, time.Time{}, bytes.NewReader(content))
}
