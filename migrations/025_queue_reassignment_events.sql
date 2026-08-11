CREATE TABLE execution_reassignments (
    id INTEGER PRIMARY KEY,
    execution_id TEXT NOT NULL REFERENCES executions(id),
    from_worker_id TEXT NOT NULL REFERENCES workers(id),
    to_worker_id TEXT NOT NULL REFERENCES workers(id),
    reassigned_at INTEGER NOT NULL
);

CREATE INDEX execution_reassignments_time
ON execution_reassignments(reassigned_at);
