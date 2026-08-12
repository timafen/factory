-- Migration 028 verifies the schema installed by migrations 026 and 027.
-- Both projections are side-effect free and keep the migration ledger honest
-- if an externally assembled database is missing either prerequisite.
SELECT id, worker_id, reconciled_at, trigger, previous_active_count,
       derived_active_count, ghost_slots_released
FROM worker_capacity_reconciliations
LIMIT 0;

SELECT work_id, parent_task_id, correction_kind
FROM tasks
LIMIT 0;
