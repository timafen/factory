ALTER TABLE executions ADD COLUMN reassignment_count INTEGER NOT NULL DEFAULT 0
    CHECK (reassignment_count >= 0);

ALTER TABLE workflow_revisions ADD COLUMN read_only INTEGER NOT NULL DEFAULT 0
    CHECK (read_only IN (0, 1));
ALTER TABLE tasks ADD COLUMN read_only INTEGER NOT NULL DEFAULT 0
    CHECK (read_only IN (0, 1));

UPDATE workflow_revisions SET read_only = 1 WHERE lower(trim(title)) = 'review';
UPDATE tasks SET read_only = 1
WHERE workflow_revision_id IN (SELECT id FROM workflow_revisions WHERE read_only = 1);

CREATE INDEX executions_compatible_claim_order
ON executions(state, required_runtime, created_at, id);
