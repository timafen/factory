CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    repository_id TEXT NOT NULL UNIQUE REFERENCES repositories(id),
    name TEXT NOT NULL,
    main_branch TEXT NOT NULL,
    project_type TEXT NOT NULL CHECK (project_type IN ('factory-single-instance', 'tarser-operations-staging')),
    contract_json TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE project_environments (
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL CHECK (name IN ('staging', 'production')),
    url TEXT NOT NULL,
    health_url TEXT NOT NULL,
    blocked INTEGER NOT NULL CHECK (blocked IN (0, 1)),
    release_adapter TEXT NOT NULL,
    rollback_adapter TEXT NOT NULL,
    PRIMARY KEY (project_id, name)
);

CREATE TABLE project_hosts (
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    environment TEXT NOT NULL,
    host TEXT NOT NULL,
    PRIMARY KEY (project_id, environment, host),
    FOREIGN KEY (project_id, environment) REFERENCES project_environments(project_id, name) ON DELETE CASCADE
);

CREATE TABLE project_required_secrets (
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    environment TEXT NOT NULL,
    name TEXT NOT NULL,
    PRIMARY KEY (project_id, environment, name),
    FOREIGN KEY (project_id, environment) REFERENCES project_environments(project_id, name) ON DELETE CASCADE
);

CREATE TABLE project_gate_results (
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    gate TEXT NOT NULL CHECK (gate IN ('secret-scan', 'static-typecheck', 'tests', 'build')),
    commit_sha TEXT NOT NULL,
    passed INTEGER NOT NULL CHECK (passed IN (0, 1)),
    checked_at INTEGER NOT NULL,
    PRIMARY KEY (project_id, gate)
);

CREATE TABLE project_runtime_readiness (
    project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    commit_sha TEXT NOT NULL DEFAULT '',
    branch_access INTEGER NOT NULL DEFAULT 0 CHECK (branch_access IN (0, 1)),
    executor_ready INTEGER NOT NULL DEFAULT 0 CHECK (executor_ready IN (0, 1)),
    updated_at INTEGER NOT NULL
);

CREATE TABLE project_operations (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    environment TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('release', 'rollback')),
    commit_sha TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'release_failed_rolled_back', 'health_failed_rolled_back', 'rollback_failed')),
    message TEXT NOT NULL,
    owner_confirmed INTEGER NOT NULL DEFAULT 0 CHECK (owner_confirmed IN (0, 1)),
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
