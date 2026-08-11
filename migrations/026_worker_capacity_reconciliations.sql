-- An append-only audit trail for server-derived worker capacity.  The old
-- workers.active_count column remains a compatibility snapshot for old clients.
CREATE TABLE worker_capacity_reconciliations (
    id INTEGER PRIMARY KEY,
    worker_id TEXT NOT NULL REFERENCES workers(id),
    reconciled_at INTEGER NOT NULL,
    trigger TEXT NOT NULL,
    previous_active_count INTEGER NOT NULL,
    derived_active_count INTEGER NOT NULL,
    ghost_slots_released INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX worker_capacity_reconciliations_time
ON worker_capacity_reconciliations(reconciled_at);

CREATE INDEX worker_capacity_reconciliations_worker_time
ON worker_capacity_reconciliations(worker_id, reconciled_at);
