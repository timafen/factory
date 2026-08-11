-- Migration 027 depends on the audit schema installed by migration 026.
-- Keep this projection before every ALTER: sqlite executes this file in one
-- transaction, so a 025 database cannot acquire provenance columns (or a
-- misleading migration-ledger entry) when 026 is not present.
SELECT id, worker_id, reconciled_at, trigger, previous_active_count,
       derived_active_count, ghost_slots_released
FROM worker_capacity_reconciliations
LIMIT 0;

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
