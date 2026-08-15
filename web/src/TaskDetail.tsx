import {
  AlertCircle,
  ArrowLeft,
  ChevronRight,
  Clock3,
  LoaderCircle,
  RefreshCw,
  Square,
  Trash2,
} from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { SpeakButton } from "./Speak";
import { TaskSummary } from "./Summary";
import { LiveActivity } from "./Live";
import { invalidateControlPlane } from "./controlPlaneQueries";
import { duration, eventSummary, runtimeLabel, type EventSummary } from "./format";
import { useVisibleInterval } from "./polling";
import type {
  Attempt,
  AttemptEvent,
  TaskDetail as TaskDetailType,
  Worker,
} from "./types";
import {
  ErrorState,
  InlineError,
  LoadingState,
  PanelHeading,
  StaleBanner,
  StatusBadge,
} from "./ui";

export function TaskDetail({
  id,
  workers,
  onBack,
  onDeleted,
}: {
  id: string;
  workers: Worker[];
  onBack: () => void;
  onDeleted: () => void;
}) {
  const interval = useVisibleInterval(2_000);
  const queryClient = useQueryClient();
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [terminalCatchupAttemptID, setTerminalCatchupAttemptID] = useState<string | null>(null);
  const detail = useQuery({
    queryKey: ["task", id],
    queryFn: () => api.task(id),
    refetchInterval: (query) => {
      const state = query.state.data?.task.state;
      return state === "queued" || state === "running" ? interval : false;
    },
  });
  const latestAttempt = detail.data?.attempts?.at(-1);
  const taskIsActive =
    detail.data?.task.state === "queued" || detail.data?.task.state === "running";
  const eventKey = ["events", latestAttempt?.id] as const;
  const events = useQuery({
    queryKey: eventKey,
    queryFn: async () => {
      const cached = queryClient.getQueryData<AttemptEvent[]>(eventKey) ?? [];
      const appended = await loadLaterEvents(
        latestAttempt!.id,
        cached.at(-1)?.sequence ?? -1,
      );
      const unique = new Map(cached.map((event) => [event.sequence, event]));
      for (const event of appended) unique.set(event.sequence, event);
      return [...unique.values()].sort((left, right) => left.sequence - right.sequence);
    },
    enabled: Boolean(latestAttempt),
    refetchInterval: detail.data?.task.state === "running" ? interval : false,
  });
  const previousTask = useRef<{ id: string; active: boolean } | undefined>(undefined);
  useEffect(() => {
    if (detail.data === undefined) return;
    let stateTimer: number | undefined;
    if (
      previousTask.current?.id === id &&
      previousTask.current.active &&
      !taskIsActive &&
      latestAttempt
    ) {
      stateTimer = window.setTimeout(
        () => setTerminalCatchupAttemptID(latestAttempt.id),
        0,
      );
    } else if (taskIsActive) {
      stateTimer = window.setTimeout(() => setTerminalCatchupAttemptID(null), 0);
    }
    previousTask.current = { id, active: taskIsActive };
    return () => {
      if (stateTimer !== undefined) window.clearTimeout(stateTimer);
    };
  }, [detail.data, id, latestAttempt, taskIsActive]);
  const refetchEvents = events.refetch;
  useEffect(() => {
    if (!terminalCatchupAttemptID || terminalCatchupAttemptID !== latestAttempt?.id) return;
    let cancelled = false;
    let retryTimer: number | undefined;
    const catchUp = async () => {
      const result = await refetchEvents();
      if (cancelled) return;
      if (result.isSuccess) {
        setTerminalCatchupAttemptID((current) =>
          current === terminalCatchupAttemptID ? null : current
        );
        return;
      }
      if (interval !== false) {
        retryTimer = window.setTimeout(() => void catchUp(), interval);
      }
    };
    void catchUp();
    return () => {
      cancelled = true;
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
    };
  }, [interval, latestAttempt?.id, refetchEvents, terminalCatchupAttemptID]);
  const cancel = useMutation({
    mutationFn: () => api.cancelTask(id),
    onSuccess: async (next) => {
      queryClient.setQueryData(["task", id], next);
      setConfirmCancel(false);
      await invalidateControlPlane(queryClient);
    },
  });
  const retry = useMutation({
    mutationFn: () => api.retryExecution(detail.data!.execution.id),
    onSuccess: async (next) => {
      queryClient.setQueryData(["task", id], next);
      await invalidateControlPlane(queryClient);
    },
  });
  const deleteTask = useMutation({
    mutationFn: () => api.deleteTask(id),
    onSuccess: async () => {
      const attemptIDs = detail.data?.attempts?.map((attempt) => attempt.id) ?? [];
      await Promise.all([
        queryClient.cancelQueries({ queryKey: ["task", id], exact: true }),
        ...attemptIDs.map((attemptID) =>
          queryClient.cancelQueries({ queryKey: ["events", attemptID], exact: true })
        ),
      ]);
      queryClient.removeQueries({ queryKey: ["task", id], exact: true });
      for (const attemptID of attemptIDs) {
        queryClient.removeQueries({ queryKey: ["events", attemptID], exact: true });
      }
      onDeleted();
      void invalidateControlPlane(queryClient);
    },
  });

  if (detail.isPending) return <LoadingState label="Загружаем задачу" />;
  if (!detail.data) return <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />;

  const data = detail.data;
  const worker = workers.find((item) => item.id === data.execution.assigned_worker_id);
  const active = data.task.state === "queued" || data.task.state === "running";
  const retryable = data.task.state === "failed" || data.task.state === "cancelled";
  const progress = (events.data ?? []).flatMap((event) => {
    const summary = eventSummary(event);
    return summary ? [{ event, summary }] : [];
  });

  return (
    <div className="page detail-page">
      <button className="back-button" onClick={onBack}><ArrowLeft size={16} /> Все задачи</button>
      <div className="detail-heading">
        <div>
          <StatusBadge state={data.task.state} />
          <h1>{data.task.title}</h1>
          <p>Создана {new Date(data.task.created_at).toLocaleString()}</p>
        </div>
        <div className="detail-actions">
          {active && !confirmCancel && (
            <button className="button button-danger-secondary" onClick={() => setConfirmCancel(true)}>
              <Square size={14} /> Отменить
            </button>
          )}
          {confirmCancel && (
            <div className="confirm-action" role="alert">
              <span>Отменить эту задачу?</span>
              <button className="button button-danger" onClick={() => cancel.mutate()} disabled={cancel.isPending}>
                {cancel.isPending ? "Отменяем…" : "Подтвердить отмену"}
              </button>
              <button className="button button-secondary" onClick={() => setConfirmCancel(false)}>Продолжить выполнение</button>
            </div>
          )}
          {retryable && (
            <button className="button button-primary" onClick={() => retry.mutate()} disabled={retry.isPending}>
              <RefreshCw size={15} className={retry.isPending ? "spin" : ""} />
              {retry.isPending ? "Перезапускаем…" : "Перезапустить задачу"}
            </button>
          )}
          {!active && !confirmDelete && (
            <button className="button button-danger-secondary" onClick={() => setConfirmDelete(true)}>
              <Trash2 size={14} /> Удалить историю
            </button>
          )}
          {confirmDelete && (
            <div className="confirm-action" role="alert">
              <span>Навсегда удалить задачу, инструкцию, попытки и события?</span>
              <button
                className="button button-danger"
                onClick={() => deleteTask.mutate()}
                disabled={deleteTask.isPending}
              >
                {deleteTask.isPending ? "Удаляем…" : "Подтвердить удаление"}
              </button>
              <button className="button button-secondary" onClick={() => setConfirmDelete(false)}>
                Сохранить историю
              </button>
            </div>
          )}
        </div>
      </div>
      {detail.error && <StaleBanner error={detail.error} />}
      {(cancel.error || retry.error || deleteTask.error) && (
        <InlineError error={cancel.error ?? retry.error ?? deleteTask.error} />
      )}
      {!data.repository_available && (
        <div className="warning-banner"><AlertCircle size={17} /> Репозиторий недоступен назначенному исполнителю. Задача останется в очереди.</div>
      )}
      {data.execution.cancellation_requested && data.task.state === "running" && (
        <div className="warning-banner"><Clock3 size={17} /> Запрошена отмена. Исполнитель остановит задачу при следующем сигнале.</div>
      )}

      <TaskSummary
        taskId={id}
        title={data.task.title}
        result={(data.attempts ?? []).slice().reverse().find((a) => a.result)?.result}
        error={(data.attempts ?? []).slice().reverse().find((a) => a.error)?.error}
      />

      <LiveActivity attemptId={latestAttempt?.id} running={data.task.state === "running"} />

      <div className="detail-grid">
        <section className="panel detail-main">
          <details>
            <summary style={{ cursor: "pointer", fontWeight: 600, padding: "4px 0" }}>
              Задание агенту (техническое) — развернуть
            </summary>
            <div className="long-copy" style={{ marginTop: 8 }}>{data.context}</div>
          </details>
        </section>
        <section className="panel">
          <PanelHeading title="Назначение" />
          <dl className="metadata">
            <div><dt>Исполнитель</dt><dd>{worker?.name ?? data.execution.assigned_worker_id}</dd></div>
            <div><dt>Среда</dt><dd>{runtimeLabel(data.execution.required_runtime)}</dd></div>
            <div><dt>Репозиторий</dt><dd>{data.repository.key}</dd></div>
            <div><dt>Удалённый адрес</dt><dd className="break-anywhere">{data.repository.remote_identity}</dd></div>
            <div><dt>Лимит времени</dt><dd>{formatTimeout(data.task.timeout_seconds)}</dd></div>
            <div><dt>Прошло</dt><dd>{taskElapsed(data)}</dd></div>
            <div><dt>Сценарий</dt><dd>{data.workflow ? `${data.workflow.title} · редакция ${data.workflow.revision_number}` : "Без сценария"}</dd></div>
          </dl>
        </section>
      </div>

      <section className="panel">
        <details>
          <summary style={{ cursor: "pointer", fontWeight: 600, padding: "4px 0" }}>
            Полный промпт (инструкция + контекст) — развернуть
          </summary>
          <div className="long-copy" style={{ marginTop: 8 }}>{data.resolved_prompt}</div>
        </details>
      </section>

      <section className="panel progress-panel">
        <PanelHeading title="Ход работы" aside={`${progress.length} обновлений`} />
        {events.error && <InlineError error={events.error} />}
        {!latestAttempt ? (
          <div className="quiet-empty">Ход работы появится, когда исполнитель начнёт задачу.</div>
        ) : events.isPending && events.data === undefined ? (
          <LoadingLine label="Загружаем ход работы" />
        ) : events.data === undefined ? null : progress.length === 0 ? (
          <div className="quiet-empty">Ход работы появится, когда исполнитель начнёт задачу.</div>
        ) : (
          <ol className="event-list">
            {progress.map(({ event, summary }) => (
              <ProgressEvent key={event.sequence} event={event} summary={summary} />
            ))}
          </ol>
        )}
      </section>

      {(data.attempts ?? []).length > 0 && (
        <section className="panel attempts-panel">
          <PanelHeading title="Попытки" aside={`${data.attempts?.length ?? 0} всего`} />
          {[...(data.attempts ?? [])].reverse().map((attempt, index) => (
        <AttemptRow key={attempt.id} attempt={attempt} current={index === 0} />
          ))}
        </section>
      )}
    </div>
  );
}

async function loadLaterEvents(attemptID: string, initialAfter: number): Promise<AttemptEvent[]> {
  const events: AttemptEvent[] = [];
  let after = initialAfter;
  for (;;) {
    const requestAfter = after;
    const page = await api.events(attemptID, after);
    for (const event of page.events) {
      if (event.sequence > after) {
        events.push(event);
        after = event.sequence;
      }
    }
    if (!page.has_more) return events;
    if (page.next_after <= requestAfter) {
      throw new Error("Пагинация событий не продвинулась.");
    }
    after = page.next_after;
  }
}

function ProgressEvent({ event, summary }: { event: AttemptEvent; summary: EventSummary }) {
  return (
    <li>
      <span className="event-marker" aria-hidden="true" />
      <div>
        <span className="event-kind">{summary.label}</span>
        <p>{summary.text}</p>
        <time dateTime={event.server_time}>{new Date(event.server_time).toLocaleTimeString()}</time>
      </div>
    </li>
  );
}

function AttemptRow({ attempt, current }: { attempt: Attempt; current: boolean }) {
  const [open, setOpen] = useState(current);
  return (
    <div className="attempt-row">
      <button onClick={() => setOpen((value) => !value)} aria-expanded={open}>
        <span><strong>Попытка {attempt.attempt_number}</strong><small>{attempt.id}</small></span>
        <span className="attempt-state"><StatusBadge state={attempt.state} /><ChevronRight size={16} className={open ? "rotate" : ""} /></span>
      </button>
      {open && (
        <div className="attempt-content">
          <dl className="metadata compact-metadata">
            <div><dt>Начата</dt><dd>{attempt.started_at ? new Date(attempt.started_at).toLocaleString() : "Не начата"}</dd></div>
            <div><dt>Длительность</dt><dd>{duration(attempt.started_at ?? attempt.created_at, attempt.completed_at)}</dd></div>
          </dl>
                    {attempt.result && <div className="attempt-output success-output"><strong>Технический отчёт</strong><SpeakButton text={attempt.result} /><pre>{attempt.result}</pre></div>}
                    {attempt.error && <div className="attempt-output error-output"><strong>Техническая ошибка</strong><SpeakButton text={attempt.error} /><pre>{attempt.error}</pre></div>}
          {!attempt.result && !attempt.error && <div className="quiet-empty">Результат или ошибка пока не записаны.</div>}
        </div>
      )}
    </div>
  );
}

function LoadingLine({ label }: { label: string }) {
  return <div className="loading-line" role="status"><LoaderCircle size={16} className="spin" />{label}</div>;
}

function formatTimeout(seconds: number): string {
  if (seconds % 3600 === 0) return `${seconds / 3600}h`;
  if (seconds % 60 === 0) return `${seconds / 60}m`;
  return `${seconds}s`;
}

function taskElapsed(detail: TaskDetailType): string {
  const latest = detail.attempts?.at(-1);
  if (!latest) return duration(detail.task.created_at);
  return duration(latest.started_at ?? latest.created_at, latest.completed_at);
}
