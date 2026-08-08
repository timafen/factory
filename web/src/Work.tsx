import { ChevronRight, ListChecks, Plus } from "lucide-react";
import { runtimeLabel, stateLabel, taskStates, timeAgo } from "./format";
import type { Task, TaskState, Worker } from "./types";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  StaleBanner,
  StatusBadge,
  ViewHeader,
  type ViewStateProps,
} from "./ui";

const LIVE_STATES: TaskState[] = ["queued", "running"];

export type WorkGroup = {
  base: string;
  items: Array<{ task: Task; stage: string | null }>;
  currentStage: string | null;
  reached: Record<string, "done" | "live" | "bad" | "again">;
};

function parseAutomatedTitle(title: string): { base: string; stage: string | null } {
  const match = /^\[auto\]\s*\[\d+\/\d+\s+([^\]]+)\]\s*(.*)$/.exec(title);
  return match ? { stage: match[1].trim(), base: match[2].trim() } : { stage: null, base: title };
}

/** Build the small piece of pipeline history needed by the work screen. */
// eslint-disable-next-line react-refresh/only-export-components
export function buildWorkGroups(
  tasks: Task[],
  _verdicts: Record<string, unknown> = {},
  _questions: unknown[] = [],
): WorkGroup[] {
  void _verdicts;
  void _questions;
  const groups = new Map<string, WorkGroup>();
  for (const task of [...tasks].sort((a, b) => a.created_at.localeCompare(b.created_at))) {
    const parsed = parseAutomatedTitle(task.title);
    const group = groups.get(parsed.base) ?? {
      base: parsed.base,
      items: [],
      currentStage: null,
      reached: {},
    };
    group.items.push({ task, stage: parsed.stage });
    if (parsed.stage) {
      if (LIVE_STATES.includes(task.state)) group.reached[parsed.stage] = "live";
      else if (task.state === "succeeded") group.reached[parsed.stage] = "done";
      else if (task.state === "failed" && !group.reached[parsed.stage]) group.reached[parsed.stage] = "bad";
    }
    groups.set(parsed.base, group);
  }

  for (const group of groups.values()) {
    const runs = new Map<string, number>();
    for (const item of group.items) {
      if (item.stage) runs.set(item.stage, (runs.get(item.stage) ?? 0) + 1);
    }
    const current = group.items.find((item) => LIVE_STATES.includes(item.task.state));
    group.currentStage = current?.stage ?? null;
    if (current?.stage && (runs.get(current.stage) ?? 0) > 1) {
      group.reached[current.stage] = "again";
    }
  }
  return [...groups.values()];
}

export function WorkView({
  tasks,
  workers,
  pending,
  error,
  fetching,
  updatedAt,
  onTask,
  onDelegate,
  onRefresh,
  hasMore,
  loadingMore,
  onLoadMore,
}: ViewStateProps & {
  tasks?: Task[];
  workers?: Worker[];
  pending: boolean;
  error: Error | null;
  onTask: (id: string) => void;
  onDelegate: () => void;
  hasMore: boolean;
  loadingMore: boolean;
  onLoadMore: () => void;
}) {
  if (pending) return <LoadingState label="Loading work" />;
  if (error && !tasks) return <ErrorState error={error} onRetry={onRefresh} />;

  const grouped = Object.fromEntries(
    taskStates.map((state) => [state, (tasks ?? []).filter((task) => task.state === state)]),
  ) as Record<TaskState, Task[]>;
  const workerMap = new Map((workers ?? []).map((worker) => [worker.id, worker]));
  const repeatedTaskIds = new Set(
    buildWorkGroups(tasks ?? []).flatMap((group) =>
      group.items
        .filter((item) => {
          const stage = item.stage;
          return stage !== null && stage === group.currentStage && group.reached[stage] === "again" && LIVE_STATES.includes(item.task.state);
        })
        .map((item) => item.task.id),
    ),
  );

  return (
    <div className="page page-work">
      <ViewHeader
        title="Agent work"
        fetching={fetching}
        updatedAt={updatedAt}
        onRefresh={onRefresh}
      />
      {error && <StaleBanner error={error} />}
      {(tasks ?? []).length === 0 ? (
        <EmptyState
          icon={<ListChecks size={22} />}
          title="No work yet"
          description="Delegate the first task to a registered worker. It will stay here through restarts."
          action={<button className="button button-primary" onClick={onDelegate}><Plus size={16} /> Delegate task</button>}
        />
      ) : (
        <div className="work-board" data-testid="work-board">
          {taskStates.map((state) => (
            <section className="work-column" key={state} aria-labelledby={`heading-${state}`}>
              <div className="column-heading">
                <span className={`status-dot status-${state}`} aria-hidden="true" />
                <h2 id={`heading-${state}`}>{stateLabel(state)}</h2>
                <span className="count">{grouped[state].length}</span>
              </div>
              <div className="task-stack">
                {grouped[state].length === 0 ? (
                  <div className="column-empty">No {state} work</div>
                ) : (
                  grouped[state].map((task) => (
                    <TaskCard
                      key={task.id}
                      task={task}
                      worker={workerMap.get(task.worker_id)}
                      repeated={repeatedTaskIds.has(task.id)}
                      onClick={() => onTask(task.id)}
                    />
                  ))
                )}
              </div>
            </section>
          ))}
        </div>
      )}
      {hasMore && (
        <div className="load-more">
          <button
            className="button button-secondary"
            onClick={onLoadMore}
            disabled={loadingMore}
          >
            {loadingMore ? "Loading more…" : "Load more work"}
          </button>
        </div>
      )}
    </div>
  );
}

function TaskCard({ task, worker, repeated, onClick }: { task: Task; worker?: Worker; repeated: boolean; onClick: () => void }) {
  return (
    <button className="task-card" onClick={onClick}>
      <div className="task-card-top">
        <StatusBadge state={task.state} />
        <ChevronRight size={14} aria-hidden="true" />
      </div>
      <span className="task-title">{task.title}{repeated && " — заново"}</span>
      {task.description && <span className="task-description">{task.description}</span>}
      <div className="task-meta">
        <span className="task-worker">{worker?.name ?? "Unknown worker"}</span>
        <span aria-hidden="true">·</span>
        {worker && (
          <>
            <span>{runtimeLabel(worker.runtime)}</span>
            <span aria-hidden="true">·</span>
          </>
        )}
        <span>{timeAgo(task.created_at)}</span>
      </div>
    </button>
  );
}
