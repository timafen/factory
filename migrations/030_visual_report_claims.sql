ALTER TABLE visual_captures ADD COLUMN claim_token TEXT NOT NULL DEFAULT '';
ALTER TABLE visual_captures ADD COLUMN updated_at TEXT NOT NULL DEFAULT '';
ALTER TABLE daily_reports ADD COLUMN claim_token TEXT NOT NULL DEFAULT '';
