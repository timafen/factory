ALTER TABLE tasks ADD COLUMN work_id TEXT;
ALTER TABLE tasks ADD COLUMN parent_task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL;
ALTER TABLE tasks ADD COLUMN correction_kind TEXT CHECK (
    correction_kind IS NULL OR correction_kind IN (
        'review_return',
        'verify_return',
        'machine_gate_return',
        'execution_retry',
        'merge_conflict_return',
        'answer_resume',
        'diagnostic_repair'
    )
);

CREATE INDEX tasks_work_created ON tasks(work_id, created_at, id);
CREATE INDEX tasks_parent_task ON tasks(parent_task_id);
