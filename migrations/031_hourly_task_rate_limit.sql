-- Automatic pipeline tasks share one durable sliding-hour budget.
ALTER TABLE tasks ADD COLUMN automatic INTEGER NOT NULL DEFAULT 0;

CREATE INDEX tasks_automatic_created_at ON tasks(automatic, created_at);
