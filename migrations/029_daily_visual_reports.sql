CREATE TABLE task_visual_targets (
  work_id TEXT PRIMARY KEY,
  url TEXT NOT NULL, state_text TEXT NOT NULL,
  viewport_width INTEGER NOT NULL, viewport_height INTEGER NOT NULL,
  after_workflow_title TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
);
CREATE TABLE visual_captures (
  work_id TEXT NOT NULL REFERENCES task_visual_targets(work_id) ON DELETE CASCADE,
  phase TEXT NOT NULL CHECK (phase IN ('before','after')),
  status TEXT NOT NULL CHECK (status IN ('pending','running','ready','missing')),
  path TEXT NOT NULL DEFAULT '', sha256 TEXT NOT NULL DEFAULT '',
  captured_at TEXT, error TEXT NOT NULL DEFAULT '',
  PRIMARY KEY(work_id, phase)
);
CREATE TABLE daily_reports (
  report_date TEXT NOT NULL, timezone TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending','running','ready','error')),
  metrics_json TEXT NOT NULL DEFAULT '{}', pdf_path TEXT NOT NULL DEFAULT '',
  pdf_sha256 TEXT NOT NULL DEFAULT '', pdf_size INTEGER NOT NULL DEFAULT 0,
  error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  PRIMARY KEY(report_date, timezone)
);
