CREATE INDEX tasks_efficiency_created_title
ON tasks(created_at, title);

CREATE INDEX attempts_efficiency_execution_order
ON attempts(execution_id, attempt_number, started_at, completed_at);
