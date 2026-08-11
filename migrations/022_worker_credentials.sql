CREATE TABLE worker_credentials (
    worker_id TEXT PRIMARY KEY REFERENCES workers(id) ON DELETE CASCADE,
    credential_digest BLOB NOT NULL CHECK (length(credential_digest) = 32),
    created_at INTEGER NOT NULL
);
