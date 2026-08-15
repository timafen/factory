export type TaskState = "queued" | "running" | "succeeded" | "failed" | "cancelled";
export type Runtime = "codex" | "claude-code";

export interface EbayConsent {
  operation_id: string;
  consent_url?: string;
  status: "pending" | "authorized" | "failed" | "expired";
  message?: string;
}

export type EbayConsentStatus = Omit<EbayConsent, "consent_url">;

export interface Repository {
  id: string;
  key: string;
  remote_identity: string;
  retained_count: number;
}

export interface RetainedWorktree {
  attempt_id: string;
  repository_id: string;
  path: string;
  reason: string;
  cleanup_command: string;
}

export interface Worker {
  id: string;
  name: string;
  worker_version: string;
  runtime: Runtime;
  runtime_version: string;
  capacity: number;
  active_count: number;
  health: "healthy" | "unhealthy";
  online: boolean;
  repositories: Repository[];
  source_access?: Array<{ provider: string; hostname: string }>;
  accepts_managed_repositories?: boolean;
  repository_cache_count?: number;
  retained_worktrees: RetainedWorktree[];
  registered_at: string;
  last_heartbeat: string;
  current_task_title?: string;
}

export type PilotStage = "Triage" | "Specification" | "Implement + Test" | "Review" | "Verify";
export type PilotTier = "low" | "medium" | "high";
export type PilotNotificationGroup = "questions" | "stuck" | "money" | "done" | "escalate" | "routine";

// Этапы приходят с сервера списком, а не словарём: порядок этапов —
// это и есть конвейер, и его нельзя терять при сериализации.
export interface PilotStageRoute {
  workflow: string;
  workers: Record<PilotTier, string>;
}

export interface PilotSettings {
  _note?: string;
  enabled: boolean;
  poll_seconds: number;
  timeout_seconds: number;
  read_only?: boolean;
  auto_merge: boolean;
  auto_answer: boolean;
  max_stage_attempts: number;
  allow_any_worker: boolean;
  allowed_workers: string[];
  max_parallel_subtasks: number;
  max_parallel_works: number;
  max_terminal_tasks_per_cycle: number;
  day_cap_usd: number;
  deploy_staging_cmd: string;
  deploy_factory_cmd: string;
  owner_chat_url: string;
  owner_ui_url: string;
  stages: PilotStageRoute[];
  skip_stages_for_low: string[];
  stopped_pipelines: string[];
  stage_base_usd: Record<string, number>;
  complexity_factor: Record<PilotTier, number>;
  work_cap_usd: Record<PilotTier, number>;
  ntfy_topic: string;
  ntfy_server: string;
  ntfy_owner_topic: string;
  notify_groups?: Partial<Record<PilotNotificationGroup, boolean>>;
  project_providers?: Array<{ remote_identity: string; type: "trade" | "factory" }>;
  brain_chain: Array<{ cli: string; model: string; provider: string; note?: string }>;
}

export interface PilotSettingsResponse {
  settings: PilotSettings;
  version: string;
  warnings: string[];
}

export interface DialogMessage {
  role: "user" | "assistant";
  content: string;
}

export interface DialogScreenshot {
  name: string;
  content_type: "image/png" | "image/jpeg" | "image/webp";
  data: string;
}

export interface DialogResponse {
  message: DialogMessage;
  model_label: string;
}

export interface ManagedRepository {
  id: string;
  remote_identity: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface ManagedRepositoryWorkerReadiness {
  id: string;
  name: string;
  cached: boolean;
  advertised: boolean;
  ready: boolean;
  reason: string;
}

export interface ManagedRepositoryReadiness {
  routing_ready: boolean;
  workers: ManagedRepositoryWorkerReadiness[];
}

export type ProjectType = "factory-single-instance" | "tarser-operations-staging";
export interface ProjectEnvironmentInput { name: "staging" | "production"; url: string; health_url: string; blocked: boolean; release_adapter: string; rollback_adapter: string; required_secrets: string[]; web_hosts: string[]; }
export interface CreateProjectInput { name: string; remote_identity: string; main_branch: string; project_type: ProjectType; required_checks: ["secret-scan", "static-typecheck", "tests", "build"]; environments: ProjectEnvironmentInput[]; }
export interface Project extends Omit<CreateProjectInput, "environments"> { id: string; repository_id: string; executor_group: string; environments: ProjectEnvironmentInput[]; created_at: string; updated_at: string; }
export interface ProjectReadinessGate { name: string; ready: boolean; reason: string; commit_sha?: string; checked_at?: string; }
export interface ProjectReadiness { ready: boolean; commit_sha?: string; gates: ProjectReadinessGate[]; secrets: Array<{ name: string; present: boolean }>; routing_reason?: string; }
export interface ProjectOperation { id: string; project_id: string; environment: string; kind: "release" | "rollback"; commit_sha: string; status: "running" | "succeeded" | "release_failed_rolled_back" | "health_failed_rolled_back" | "rollback_failed"; message: string; owner_confirmed: boolean; created_at: string; updated_at: string; }

export interface WorkerRepositoryOption {
  id: string;
  key?: string;
  remote_identity: string;
  enabled: boolean;
  cached: boolean;
  advertised: boolean;
  ready: boolean;
  reason: string;
}

export interface Task {
  id: string;
  work_id?: string;
  request_key: string;
  title: string;
  description?: string;
  worker_id: string;
  repository_id: string;
  timeout_seconds: number;
  state: TaskState;
  created_at: string;
}

export interface TaskPage {
  tasks: Task[];
  next_cursor: string | null;
}

export interface Execution {
  id: string;
  task_id: string;
  assigned_worker_id: string;
  required_runtime: Runtime;
  state: "queued" | "preparing" | "running" | "succeeded" | "failed" | "cancelled";
  cancellation_requested: boolean;
  created_at: string;
  updated_at: string;
}

export interface Attempt {
  id: string;
  execution_id: string;
  worker_id: string;
  attempt_number: number;
  state: "preparing" | "running" | "succeeded" | "failed" | "cancelled" | "lost";
  lease_expires_at: string;
  result?: string;
  error?: string;
  started_at?: string;
  completed_at?: string;
  created_at: string;
}

export interface TaskDetail {
  task: Task & { description: string };
  context: string;
  execution: Execution;
  repository: Repository;
  repository_available: boolean;
  attempts: Attempt[] | null;
  workflow?: TaskWorkflowSnapshot;
  resolved_prompt: string;
}

export interface TaskWorkflowSnapshot {
  id: string;
  revision_id: string;
  title: string;
  revision_number: number;
  read_only?: boolean;
}

export interface WorkflowRevision {
  id: string;
  workflow_id: string;
  revision_number: number;
  title: string;
  summary: string;
  instructions?: string;
  read_only?: boolean;
  created_at: string;
}

export interface Workflow {
  id: string;
  enabled: boolean;
  current_revision: WorkflowRevision;
  created_at: string;
  updated_at: string;
}

export interface WorkflowDetail {
  workflow: Workflow;
  revisions: WorkflowRevision[];
}

export interface WorkflowPage {
  workflows: Workflow[];
  next_cursor: string | null;
}

export interface GitHubIssueTrigger {
	type: "github_issue";
	state: "open" | "closed";
	required_labels: string[];
	poll_interval_seconds: number;
}

export interface GitHubPullRequestTrigger {
	type: "github_pull_request";
	state: "open" | "closed" | "merged";
	include_drafts: boolean;
	required_labels: string[];
	base_branches: string[];
	poll_interval_seconds: number;
}

export interface ScheduleTrigger {
	type: "schedule";
	cron: string;
	timezone: string;
}

export type AutomationTrigger = GitHubIssueTrigger | GitHubPullRequestTrigger | ScheduleTrigger;

export interface AutomationTaskSummary {
	id: string;
	title: string;
	state: string;
	retry_count?: number;
	retry_status?: "queued" | "running" | "succeeded" | "final_failed" | "skipped_disabled" | "skipped_worker_unavailable";
}

export interface AutomationHealth {
	status: "disabled" | "pending" | "checking" | "healthy" | "blocked" | "error";
	code?: string;
	message?: string;
}

export interface AutomationStatus {
	source: "control_plane" | "host";
	id: string;
	category: "automation" | "pilot" | "release_broker" | "release" | "janitor";
	title: string;
	purpose: string;
	status: string;
	data_status: "ok" | "no_data";
	last_activity_at?: string;
	diagnostic?: string;
}

export interface Automation {
	id: string;
	title: string;
	workflow_id: string;
	workflow_title: string;
	workflow_revision: number;
	repository_id: string;
	repository_identity: string;
	context: string;
	timeout_seconds: number;
	enabled: boolean;
	version: number;
	trigger: AutomationTrigger;
	health: AutomationHealth;
	last_checked_at?: string;
	next_check_at?: string;
	next_due_at?: string;
	matched_count: number;
	skipped_count: number;
	dispatched_count: number;
	latest_task?: AutomationTaskSummary;
	latest_run?: AutomationOccurrence;
	created_at: string;
	updated_at: string;
}

export interface AutomationOccurrence {
	id: string;
	automation_id: string;
	automation_version: number;
	state: "pending" | "dispatching" | "dispatched" | "failed" | "task_deleted" | "skipped";
	issue_number?: number;
	issue_url?: string;
	issue_title?: string;
	observed_state?: string;
	observed_labels?: string[];
	pull_request_number?: number;
	pull_request_url?: string;
	pull_request_title?: string;
	observed_draft?: boolean;
	observed_base_branch?: string;
	observed_head_commit?: string;
	kind?: "scheduled" | "run_now";
	scheduled_at?: string;
	run_request_key?: string;
	cron?: string;
	timezone?: string;
	task_request_key: string;
	task?: AutomationTaskSummary;
	task_id_snapshot?: string;
	diagnostic?: string;
	created_at: string;
	updated_at: string;
}

export interface LegacyPollerSelection {
	config_path?: string;
	data_home?: string;
	working_directory?: string;
	confirm_stopped: boolean;
}

export interface LegacyPollerQueue {
	queue_id: string;
	name: string;
	source: string;
	project: string;
	state: string;
	required_labels: string[];
	poll_interval_seconds: number;
	timeout_seconds: number;
	repository_id?: string;
	repository_identity?: string;
	workflow_title: string;
	automation_title: string;
	pending_observations: number;
	submitted_observations: number;
	supported: boolean;
	blocking: boolean;
	errors: string[];
}

export interface LegacyPollerMigration {
	id: string;
	snapshot_digest: string;
	status: "previewed" | "imported" | "finalized";
	config_path: string;
	data_home: string;
	working_directory: string;
	data_directory: string;
	ledger_path: string;
	archive_root: string;
	archive_path?: string;
	counts: {
		queues: number;
		supported_queues: number;
		unsupported_queues: number;
		pending_observations: number;
		submitted_observations: number;
	};
	queues: LegacyPollerQueue[];
	automations: Automation[];
	occurrences: AutomationOccurrence[];
	errors: string[];
	created_at: string;
	updated_at: string;
}

export interface AutomationDetail {
	automation: Automation;
	occurrences: AutomationOccurrence[];
}

export interface AutomationPage {
	automations: Automation[];
	next_cursor: string | null;
}

export interface AutomationOccurrencePage {
	occurrences: AutomationOccurrence[];
	next_cursor: string | null;
}

export interface CreateAutomationInput {
	request_key: string;
	title: string;
	workflow_id: string;
	repository_id: string;
	context: string;
	timeout_seconds: number;
	trigger: AutomationTrigger;
}

export interface UpdateAutomationInput extends Omit<CreateAutomationInput, "request_key" | "repository_id"> {
	expected_version: number;
}

export interface TestAutomationResult {
	matches: Array<{
		number: number;
		title: string;
		url: string;
		state: string;
		labels: string[];
		is_draft?: boolean;
		base_branch?: string;
		head_commit?: string;
	}>;
	next_due_at?: string;
}

export type MetricsWindow = "24h" | "7d" | "30d" | "all";

export interface MetricsSummary {
  window: MetricsWindow;
  generated_at: string;
  executions_created: number;
  executions_completed: number;
  succeeded: number;
  failed: number;
  cancelled: number;
  queued: number;
  running: number;
  success_rate: number | null;
  retry_rate: number | null;
  median_cycle_time_seconds: number | null;
  workers_online: number;
  workers_total: number;
  queue_reassignments: number;
  weekly_limit?: WeeklyLimit;
}

export interface WeeklyLimit {
  used_percent: number;
  resets_at: string;
}

export interface AttemptEvent {
  sequence: number;
  kind: string;
  payload: unknown;
  server_time: string;
}

export interface AttemptEventPage {
  events: AttemptEvent[];
  next_after: number;
  has_more: boolean;
}

export interface APIErrorBody {
  error: { code: string; message: string };
}

interface CreateTaskBaseInput {
  request_key: string;
  title: string;
  worker_id: string;
  repository_id?: string;
  route?: {
    repository_remote_identity: string;
    source_access: { provider: string; hostname: string };
  };
  timeout_seconds: number;
	attachment_ids?: string[];
	visual_target?: VisualTarget;
}

export interface VisualTarget { url: string; state_text: string; viewport_width: number; viewport_height: number; after_workflow_title?: string }
export interface DailyReport { report_date: string; timezone: string; status: "pending" | "running" | "ready" | "error"; metrics?: Record<string, unknown>; pdf_sha256?: string; pdf_size?: number; error?: string }

export interface TaskAttachment { id: string; name: string; content_type: string; size: number; sha256: string }

export type CreateTaskInput = CreateTaskBaseInput & (
  | { description: string; context?: never; workflow_revision_id?: never }
  | { description?: never; context: string; workflow_revision_id: string }
);

export interface CreateWorkflowInput {
	request_key: string;
	title: string;
  summary: string;
  instructions: string;
  read_only?: boolean;
}

export interface CreateWorkflowRevisionInput extends CreateWorkflowInput {
  expected_revision_id: string;
}

export interface PipelineStage {
  workflow: string;
  worker?: string;
  workers?: Record<string, string>;
}

export interface PipelineConfig {
  enabled: boolean;
  decision_model: string;
  poll_seconds?: number;
  timeout_seconds?: number;
  _note?: string;
  stages: PipelineStage[];
}

export interface CardSummary {
  repository_id: string;
  repository_identity: string;
  path: string;
  name: string;
  size: number;
  status?: string;
  next_action?: string;
  github_url: string;
}
