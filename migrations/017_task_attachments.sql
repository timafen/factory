CREATE TABLE task_attachments (
    id TEXT PRIMARY KEY,
    request_key TEXT NOT NULL,
    task_id TEXT REFERENCES tasks(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE INDEX task_attachments_request_key ON task_attachments(request_key);
CREATE INDEX task_attachments_task_id ON task_attachments(task_id);
