-- Capacity history starts at this migration.  It deliberately records samples
-- rather than deriving a fictional past from the current execution snapshot.
CREATE TABLE product_capacity_samples (
    sampled_at INTEGER PRIMARY KEY,
    active_works INTEGER NOT NULL CHECK (active_works BETWEEN 0 AND 4),
    queued_works INTEGER NOT NULL CHECK (queued_works >= 0),
    underload_reason TEXT NOT NULL CHECK (underload_reason IN (
        'none', 'no_ready_work', 'owner_question', 'provider_limit',
        'repository_conflict', 'release_lock', 'unknown'
    ))
);

CREATE INDEX product_capacity_samples_retention
ON product_capacity_samples(sampled_at);
