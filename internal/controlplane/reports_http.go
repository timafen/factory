package controlplane

import (
	"database/sql"
	"encoding/json"
	"errors"
	"net/http"
	"os"
	"path/filepath"
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
	var status, path, hash string
	var size int64
	err := api.store.db.QueryRowContext(r.Context(), `SELECT status,pdf_path,pdf_sha256,pdf_size FROM daily_reports WHERE report_date=? ORDER BY timezone LIMIT 1`, date).Scan(&status, &path, &hash, &size)
	if errors.Is(err, sql.ErrNoRows) || status != "ready" {
		http.NotFound(w, r)
		return
	}
	if err != nil || filepath.Base(path) != path || path == "" {
		http.Error(w, "report unavailable", http.StatusConflict)
		return
	}
	root := os.Getenv("FACTORY_REPORT_ROOT")
	if root == "" {
		root = "/opt/factory-data/reports"
	}
	file, err := os.Open(filepath.Join(root, path))
	if err != nil {
		http.NotFound(w, r)
		return
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil || info.Size() != size || hash == "" {
		http.Error(w, "report incomplete", http.StatusConflict)
		return
	}
	w.Header().Set("Content-Type", "application/pdf")
	w.Header().Set("Content-Disposition", `attachment; filename="daily-report-`+date+`.pdf"`)
	http.ServeContent(w, r, path, info.ModTime(), file)
}
