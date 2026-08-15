import {
  Activity,
  ArrowLeft,
  BookOpenText,
  Bot,
  ChevronRight,
  CirclePlay,
  DatabaseBackup,
  ExternalLink,
  FlaskConical,
  LoaderCircle,
  Pencil,
  Plus,
  Power,
  PowerOff,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { api } from "./api";
import { invalidateControlPlane } from "./controlPlaneQueries";
import { useVisibleInterval } from "./polling";
import type {
  Automation,
	AutomationStatus,
  AutomationDetail as AutomationDetailType,
  AutomationOccurrence,
  AutomationTaskSummary,
  AutomationTrigger,
  CreateAutomationInput,
  LegacyPollerMigration,
  LegacyPollerSelection,
  TestAutomationResult,
} from "./types";
import {
  EmptyState,
  ErrorState,
  InlineError,
  LoadingState,
  PanelHeading,
  StaleBanner,
  ViewHeader,
} from "./ui";

export function AutomationsView({ onAutomation }: { onAutomation: (id: string) => void }) {
  const [createOpen, setCreateOpen] = useState(false);
  const [migrationOpen, setMigrationOpen] = useState(false);
  const [repositoryFilter, setRepositoryFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState<"all" | "enabled" | "disabled">("all");
  const [history, setHistory] = useState<Automation[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>();
  const previousHeadCursor = useRef<string | null | undefined>(undefined);
  const interval = useVisibleInterval(5_000);
  const query = useQuery({
    queryKey: ["automations", "head"],
    queryFn: () => api.automations(),
    refetchInterval: interval,
  });
	const statuses = useQuery({
		queryKey: ["automations", "status"],
		queryFn: () => api.automationStatuses(),
		refetchInterval: interval,
	});
  const loadMore = useMutation({
    mutationFn: ({ cursor }: { cursor: string; headCursor: string | null }) => api.automations(cursor),
    onSuccess: (page, request) => {
      setHistory((current) => mergeAutomations(current, page.automations));
      if (previousHeadCursor.current === request.headCursor) setNextCursor(page.next_cursor);
    },
  });
  useEffect(() => {
    if (!query.data) return;
    const boundaryChanged = previousHeadCursor.current !== query.data.next_cursor;
    setNextCursor((current) => boundaryChanged ? query.data.next_cursor : current);
    previousHeadCursor.current = query.data.next_cursor;
  }, [query.data]);
  const activeCursor = nextCursor === undefined ? query.data?.next_cursor : nextCursor;
  const items = mergeAutomations(query.data?.automations ?? [], history);
  const repositoryOptions = useMemo(() => Array.from(new Set(
    items.map((automation) => automation.repository_identity),
  )).sort(), [items]);
  const visibleItems = items.filter((automation) => {
    if (repositoryFilter !== "all" && automation.repository_identity !== repositoryFilter) return false;
    if (statusFilter === "enabled" && !automation.enabled) return false;
    if (statusFilter === "disabled" && automation.enabled) return false;
    return true;
  });

  if (query.isPending) return <LoadingState label="Загружаем автоматизации" />;
  if (!query.data) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;

  return (
    <div className="page">
      <ViewHeader
        title="Автоматизации"
        fetching={query.isFetching}
        updatedAt={query.dataUpdatedAt}
        onRefresh={() => void query.refetch()}
      />
      {query.error && <StaleBanner error={query.error} />}
	  {statuses.error && <StaleBanner error={statuses.error} />}
      <div className="view-toolbar">
        <p>Запускайте агентов по сохранённому Markdown-сценарию, состоянию GitHub или расписанию.</p>
        <div className="detail-actions">
          <button className="button button-secondary" onClick={() => setMigrationOpen(true)}>
            <DatabaseBackup size={15} /> Перенести старый опросчик
          </button>
          <button className="button button-primary" onClick={() => setCreateOpen(true)}>
            <Plus size={15} /> Создать автоматизацию
          </button>
        </div>
      </div>
	  {statuses.data && (
		<div className="workflow-list automation-list" aria-label="Живой статус автоматик">
		  <div className="automation-table-head">
			<span>Автоматика</span><span>Категория</span><span>Состояние</span><span>Назначение</span><span>Последняя активность</span><span />
		  </div>
		  {statuses.data.map((status: AutomationStatus) => {
			const content = <>
			  <span className="workflow-identity"><strong>{status.title}</strong><small>{status.source === "host" ? "Служба хоста" : "Панель управления"}</small></span>
			  <span>{status.category}</span>
			  <span className="automation-list-copy"><strong>{status.data_status === "no_data" ? "Нет данных" : status.status}</strong><small>{status.diagnostic ?? "Живой статус"}</small></span>
			  <span>{status.purpose}</span>
			  <span>{status.last_activity_at ? formatTimestamp(status.last_activity_at) : "нет данных"}</span>
			  {status.source === "control_plane" ? <ChevronRight size={15} className="row-chevron" /> : <span />}
			</>;
			return status.source === "control_plane"
			  ? <button className="automation-row automation-live-row" key={`${status.source}:${status.id}`} onClick={() => onAutomation(status.id)}>{content}</button>
			  : <div className="automation-row automation-live-row" key={`${status.source}:${status.id}`}>{content}</div>;
		  })}
		</div>
	  )}
      {items.length > 0 && (
        <div className="automation-filterbar" aria-label="Фильтры автоматизаций">
          <SlidersHorizontal size={14} aria-hidden="true" />
          <label>
            <span>Репозиторий</span>
            <select value={repositoryFilter} onChange={(event) => setRepositoryFilter(event.target.value)}>
              <option value="all">Все репозитории</option>
              {repositoryOptions.map((identity) => <option key={identity} value={identity}>{identity}</option>)}
            </select>
          </label>
          <label>
            <span>Статус</span>
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)}>
              <option value="all">Любой статус</option>
              <option value="enabled">Включена</option>
              <option value="disabled">Выключена</option>
            </select>
          </label>
          <span className="automation-filter-count">{visibleItems.length} из {items.length}</span>
        </div>
      )}
      {items.length === 0 ? (
        <EmptyState
          icon={<Bot size={22} />}
          title="Автоматизаций пока нет"
          description="Создайте выключенный типизированный триггер, проверьте его и затем включите."
          action={<button className="button button-primary" onClick={() => setCreateOpen(true)}>Создать автоматизацию</button>}
        />
      ) : visibleItems.length === 0 ? (
        <EmptyState
          icon={<SlidersHorizontal size={22} />}
          title="Подходящих автоматизаций нет"
          description="Измените фильтр репозитория или статуса, чтобы увидеть больше автоматизаций."
          action={<button className="button button-secondary" onClick={() => { setRepositoryFilter("all"); setStatusFilter("all"); }}>Сбросить фильтры</button>}
        />
      ) : (
        <div className="workflow-list automation-list">
          <div className="automation-table-head">
            <span>Автоматизация</span><span>Статус</span><span>Последний запуск</span><span>Активность</span><span>Следующее действие</span><span />
          </div>
          {visibleItems.map((automation) => {
            const latestRun = automation.latest_run;
            const latestRunState = latestRun ? automationRunState(latestRun) : undefined;
            return (
              <button className="automation-row" key={automation.id} onClick={() => onAutomation(automation.id)}>
                <span className="workflow-identity">
                  <strong>{automation.title}</strong>
                  <small>{automation.repository_identity} · {triggerSummary(automation)}</small>
                </span>
                <span className="automation-list-health"><HealthBadge automation={automation} /><small>{automationHealthMessage(automation.health.code, automation.health.message)}</small></span>
                <span className="automation-list-copy">
                  <strong>{latestRun ? occurrenceIdentity(latestRun) : automation.latest_task?.title || "Запусков ещё нет"}</strong>
                  <small>{latestRun && latestRunState
                    ? `${latestRunState.label} · ${formatTimestamp(latestRun.created_at)}`
                    : automation.latest_task ? formatRunState(automation.latest_task.state) : "Ожидается первый запуск"}</small>
                </span>
                <span className="automation-list-copy"><strong>{automation.dispatched_count} запущено</strong><small>{automation.matched_count} найдено · {automation.skipped_count} повторно использовано</small></span>
                <span className="automation-list-copy"><strong>{formatTimestamp(automation.next_due_at ?? automation.next_check_at)}</strong><small>{automation.trigger.type === "schedule" ? "Следующий запуск" : "Следующая проверка"} · проверено {formatTimestamp(automation.last_checked_at)}</small></span>
                <ChevronRight size={15} className="row-chevron" />
              </button>
            );
          })}
        </div>
      )}
      {activeCursor && (
        <div className="load-more">
          <button
            className="button button-secondary"
            disabled={loadMore.isPending}
            onClick={() => loadMore.mutate({ cursor: activeCursor, headCursor: previousHeadCursor.current ?? null })}
          >
            {loadMore.isPending ? "Загружаем…" : "Показать ещё автоматизации"}
          </button>
        </div>
      )}
      {loadMore.error && <InlineError error={loadMore.error} />}
      {createOpen && (
        <AutomationForm
          mode="create"
          onClose={() => setCreateOpen(false)}
          onSaved={(detail) => {
            setCreateOpen(false);
            onAutomation(detail.automation.id);
          }}
        />
      )}
      {migrationOpen && (
        <LegacyPollerMigrationDialog
          onClose={() => setMigrationOpen(false)}
          onAutomation={onAutomation}
        />
      )}
    </div>
  );
}

export function AutomationDetail({
  id,
  onBack,
  onTask,
}: {
  id: string;
  onBack: () => void;
  onTask: (id: string) => void;
}) {
  const queryClient = useQueryClient();
  const interval = useVisibleInterval(3_000);
  const [editing, setEditing] = useState(false);
  const [confirmEnabled, setConfirmEnabled] = useState<boolean>();
  const [confirmPatrol, setConfirmPatrol] = useState(false);
  const [preview, setPreview] = useState<TestAutomationResult>();
  const [occurrenceHistory, setOccurrenceHistory] = useState<AutomationOccurrence[]>([]);
  const [nextOccurrenceCursor, setNextOccurrenceCursor] = useState<string | null>();
  const previousOccurrenceHeadCursor = useRef<string | null | undefined>(undefined);
  const runRequest = useRef<{ automationID: string; key: string } | undefined>(undefined);
  const detail = useQuery({
    queryKey: ["automation", id],
    queryFn: () => api.automation(id),
    refetchInterval: interval,
  });
  const workflowID = detail.data?.automation.workflow_id ?? "";
  const runbook = useQuery({
    queryKey: ["workflow", workflowID, "automation-detail"],
    queryFn: () => api.workflow(workflowID),
    enabled: Boolean(workflowID),
  });
  const occurrences = useQuery({
    queryKey: ["automations", id, "occurrences", "head"],
    queryFn: () => api.automationOccurrences(id),
    refetchInterval: interval,
  });
  const loadMoreOccurrences = useMutation({
    mutationFn: ({ cursor }: { cursor: string; headCursor: string | null }) => api.automationOccurrences(id, cursor),
    onSuccess: (page, request) => {
      setOccurrenceHistory((current) => mergeOccurrences(current, page.occurrences));
      if (previousOccurrenceHeadCursor.current === request.headCursor) setNextOccurrenceCursor(page.next_cursor);
    },
  });
  useEffect(() => {
    if (!occurrences.data) return;
    const boundaryChanged = previousOccurrenceHeadCursor.current !== occurrences.data.next_cursor;
    setNextOccurrenceCursor((current) => boundaryChanged ? occurrences.data.next_cursor : current);
    previousOccurrenceHeadCursor.current = occurrences.data.next_cursor;
  }, [occurrences.data]);
  const setEnabled = useMutation({
    mutationFn: (enabled: boolean) => api.setAutomationEnabled({ id, enabled }),
    onSuccess: async (next) => {
      queryClient.setQueryData(["automation", id], next);
      setConfirmEnabled(undefined);
      await invalidateControlPlane(queryClient);
    },
  });
  const provisionPatrol = useMutation({
    mutationFn: () => api.provisionPipelinePatrol(id),
    onSuccess: async (next) => {
      queryClient.setQueryData(["automation", id], next);
      setConfirmPatrol(false);
      await invalidateControlPlane(queryClient);
    },
  });
  const test = useMutation({
    mutationFn: () => api.testAutomation(id),
    onSuccess: setPreview,
  });
  const check = useMutation({
    mutationFn: () => api.checkAutomation(id),
    onSuccess: async (next) => {
      queryClient.setQueryData(["automation", id], next);
      await invalidateControlPlane(queryClient);
    },
  });
  const run = useMutation({
    mutationFn: () => {
      if (!runRequest.current || runRequest.current.automationID !== id) {
        runRequest.current = { automationID: id, key: crypto.randomUUID() };
      }
      return api.runAutomation(id, runRequest.current.key);
    },
    onSuccess: async (next) => {
      runRequest.current = undefined;
      queryClient.setQueryData(["automation", id], next);
      await invalidateControlPlane(queryClient);
    },
  });

  if (detail.isPending) return <LoadingState label="Загружаем автоматизацию" />;
  if (!detail.data) return <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />;
  const data = detail.data;
  const automation = data.automation;
  const occurrenceItems = mergeOccurrences(occurrences.data?.occurrences ?? data.occurrences, occurrenceHistory);
  const latestRun = automation.latest_run ?? occurrenceItems[0];
  const latestRunState = latestRun ? automationRunState(latestRun) : undefined;
  const activeOccurrenceCursor = nextOccurrenceCursor === undefined
    ? occurrences.data?.next_cursor
    : nextOccurrenceCursor;

  return (
    <div className="page detail-page">
      <button className="back-button" onClick={onBack}><ArrowLeft size={16} /> Все автоматизации</button>
      <div className="detail-heading">
        <div>
          <HealthBadge automation={automation} />
          <h1>{automation.title}</h1>
          <p>{triggerSummary(automation)} · {automation.repository_identity}</p>
        </div>
        <div className="detail-actions">
          <button className="button button-secondary" onClick={() => test.mutate()} disabled={test.isPending}>
            {test.isPending ? <LoaderCircle size={14} className="spin" /> : <FlaskConical size={14} />} Проверить триггер
          </button>
          {automation.trigger.type === "schedule" ? (
            <>
              <button className="button button-secondary" onClick={() => setConfirmPatrol(true)} disabled={provisionPatrol.isPending}>
                <Bot size={14} /> Включить патруль конвейера
              </button>
              <button className="button button-secondary" onClick={() => run.mutate()} disabled={!automation.enabled || run.isPending}>
                <CirclePlay size={14} /> Запустить сейчас
              </button>
            </>
          ) : (
            <button className="button button-secondary" onClick={() => check.mutate()} disabled={!automation.enabled || check.isPending}>
              <CirclePlay size={14} /> Проверить сейчас
            </button>
          )}
          <button className="button button-secondary" onClick={() => setEditing(true)} disabled={automation.enabled}>
            <Pencil size={14} /> Изменить
          </button>
          <button
            className={automation.enabled ? "button button-danger-secondary" : "button button-primary"}
            onClick={() => setConfirmEnabled(!automation.enabled)}
          >
            {automation.enabled ? <PowerOff size={14} /> : <Power size={14} />}
            {automation.enabled ? "Выключить" : "Включить"}
          </button>
        </div>
      </div>
      {detail.error && <StaleBanner error={detail.error} />}
      {setEnabled.error && <InlineError error={setEnabled.error} />}
      {provisionPatrol.error && <InlineError error={provisionPatrol.error} />}
      {test.error && <InlineError error={test.error} />}
      {check.error && <InlineError error={check.error} />}
      {run.error && <InlineError error={run.error} />}
      {confirmEnabled !== undefined && (
        <div className="confirm-action automation-confirm" role="alert">
          <div>
            <strong>{confirmEnabled ? "Включить эту автоматизацию?" : "Выключить эту автоматизацию?"}</strong>
            <p>{confirmEnabled
              ? `${automation.workflow_title} · ${automation.repository_identity} · ${triggerSummary(automation)}`
              : "Будущие проверки и ожидающие запуски остановятся. Существующие задачи продолжатся."}</p>
          </div>
          <button
            className={confirmEnabled ? "button button-primary" : "button button-danger"}
            disabled={setEnabled.isPending}
            onClick={() => setEnabled.mutate(confirmEnabled)}
          >
            {setEnabled.isPending ? "Сохраняем…" : `Подтвердить ${confirmEnabled ? "включение" : "выключение"}`}
          </button>
          <button className="button button-secondary" onClick={() => setConfirmEnabled(undefined)}>Отмена</button>
        </div>
      )}
      {confirmPatrol && (
        <div className="confirm-action automation-confirm" role="alert">
          <div>
            <strong>Включить патруль конвейера по этому расписанию?</strong>
            <p>Инструкции патруля сохранятся в «{automation.title}». Текущие Cron и часовой пояс не изменятся.</p>
          </div>
          <button
            className="button button-primary"
            disabled={provisionPatrol.isPending}
            onClick={() => provisionPatrol.mutate()}
          >
            {provisionPatrol.isPending ? "Включаем…" : "Подтвердить патруль"}
          </button>
          <button className="button button-secondary" onClick={() => setConfirmPatrol(false)}>Отмена</button>
        </div>
      )}

      <div className="automation-health-card panel">
        <PanelHeading title="Состояние автоматизации" aside={automation.health.status} />
        <p className={automation.health.status === "error" || automation.health.status === "blocked" ? "health-error" : ""}>
          {automationHealthMessage(automation.health.code, automation.health.message)}
          {automation.health.code && <span className="mono"> · {automation.health.code}</span>}
        </p>
        <div className="automation-metrics">
          <Metric label="Найдено" value={automation.matched_count} />
          <Metric label="Повторно использовано" value={automation.skipped_count} />
          <Metric label="Запущено" value={automation.dispatched_count} />
          <Metric label={automation.trigger.type === "schedule" ? "Последнее событие" : "Последняя проверка"} value={formatTimestamp(automation.last_checked_at)} />
          <Metric label={automation.trigger.type === "schedule" ? "Следующий запуск" : "Следующая проверка"} value={formatTimestamp(automation.next_due_at ?? automation.next_check_at)} />
        </div>
        <div className="automation-latest-task">
          <span><strong>Последний запуск</strong><small>{latestRun ? occurrenceIdentity(latestRun) : "Зафиксированных запусков пока нет."}</small></span>
          {latestRun && latestRunState && <>
            <span className={`status-badge status-${latestRunState.style}`}><span className="status-dot" />{latestRunState.label}</span>
            {latestRun.task && <button className="button button-secondary" onClick={() => onTask(latestRun.task!.id)}>Открыть последнюю задачу</button>}
          </>}
        </div>
      </div>

      {preview && (
        <section className="panel preview-panel" aria-live="polite">
          <PanelHeading title="Результаты проверки" aside={preview.next_due_at ? `Следующий запуск ${formatTimestamp(preview.next_due_at)}` : `${preview.matches.length} совпадений`} />
          <p className="muted">Проверка не создаёт задачу или постоянную запись запуска.</p>
          {preview.next_due_at ? <p>Следующий подходящий момент UTC: <strong>{new Date(preview.next_due_at).toISOString()}</strong>.</p> : preview.matches.length === 0 ? <p>Подходящие элементы GitHub не найдены.</p> : preview.matches.map((match) => (
            <a key={match.number} href={match.url} target="_blank" rel="noreferrer" className="preview-match">
              <strong>#{match.number} {match.title}</strong>
              <span>{match.state}{match.base_branch ? ` · база ${match.base_branch}` : ""}{match.is_draft ? " · черновик" : ""} · {match.labels.join(", ") || "без меток"}</span>
            </a>
          ))}
        </section>
      )}

      <div className="detail-grid">
        <section className="panel detail-main">
          <PanelHeading title="Конфигурация" aside={`Версия ${automation.version}`} />
          <dl className="metadata">
            <div><dt>Сценарий</dt><dd>{automation.workflow_title} · версия {automation.workflow_revision}</dd></div>
            <div><dt>Репозиторий</dt><dd className="mono">{automation.repository_identity}</dd></div>
            {automation.trigger.type === "schedule" ? <>
              <div><dt>Cron</dt><dd className="mono">{automation.trigger.cron}</dd></div>
              <div><dt>Часовой пояс</dt><dd>{automation.trigger.timezone}</dd></div>
              <div><dt>Следующий запуск UTC</dt><dd>{automation.next_due_at ? new Date(automation.next_due_at).toISOString() : "Выключена"}</dd></div>
            </> : <>
              <div><dt>{automation.trigger.type === "github_pull_request" ? "Состояние pull request" : "Состояние issue"}</dt><dd>{automation.trigger.state}</dd></div>
            {automation.trigger.type === "github_pull_request" && <>
              <div><dt>Черновики</dt><dd>{automation.trigger.include_drafts ? "Включены" : "Исключены"}</dd></div>
              <div><dt>Базовые ветки</dt><dd>{automation.trigger.base_branches.join(", ") || "Любые"}</dd></div>
            </>}
            <div><dt>Обязательные метки</dt><dd>{automation.trigger.required_labels.join(", ") || "Нет"}</dd></div>
            <div><dt>Опрос</dt><dd>Каждые {automation.trigger.poll_interval_seconds} секунд</dd></div>
            </>}
            <div><dt>Тайм-аут</dt><dd>{automation.timeout_seconds} секунд</dd></div>
          </dl>
        </section>
        <section className="panel">
          <PanelHeading title="Сценарий" aside={runbook.data ? `Версия ${runbook.data.workflow.current_revision.revision_number}` : undefined} />
          {runbook.isPending ? (
            <p className="muted">Загружаем инструкции Markdown…</p>
          ) : runbook.data ? (
            <pre className="runbook-copy">{runbook.data.workflow.current_revision.instructions}</pre>
          ) : (
            <InlineError error={runbook.error as Error} />
          )}
        </section>
      </div>

      <section className="panel automation-context-panel">
        <PanelHeading title="Контекст автоматизации" />
        <div className="long-copy">{automation.context || "Дополнительного контекста нет."}</div>
      </section>

      <section className="panel">
        <PanelHeading title="Запуски" aside={`${occurrenceItems.length} загружено`} />
        {occurrenceItems.length === 0 ? (
          <p className="muted">Запусков пока нет.</p>
        ) : (
          <div className="occurrence-list">
            {occurrenceItems.map((occurrence) => {
              const state = automationRunState(occurrence);
              const sourceURL = occurrence.pull_request_url ?? occurrence.issue_url;
              return (
                <div className="occurrence-row" key={occurrence.id}>
                  <span className={`status-badge status-${state.style}`}><span className="status-dot" />{state.label}</span>
                  <span className="occurrence-identity">
                    <strong>{occurrenceIdentity(occurrence)}</strong>
                    <small>{formatTimestamp(occurrence.created_at)}{occurrence.task ? ` · ${occurrence.task.title}` : ""}{occurrence.diagnostic ? ` · ${occurrence.diagnostic}` : ""}</small>
                  </span>
                  <span className="occurrence-actions">
                    {sourceURL && (
                      <a className="button button-secondary" href={sourceURL} target="_blank" rel="noreferrer">
                        <ExternalLink size={13} /> Источник GitHub
                      </a>
                    )}
                    {occurrence.task ? (
                      <button className="button button-secondary" onClick={() => onTask(occurrence.task!.id)}>
                        Открыть задачу
                      </button>
                    ) : occurrence.state === "task_deleted" ? (
                      <span className="muted">Задача удалена</span>
                    ) : null}
                  </span>
                </div>
              );
            })}
          </div>
        )}
        {activeOccurrenceCursor && (
          <div className="load-more">
            <button
              className="button button-secondary"
              disabled={loadMoreOccurrences.isPending}
              onClick={() => loadMoreOccurrences.mutate({
                cursor: activeOccurrenceCursor,
                headCursor: previousOccurrenceHeadCursor.current ?? null,
              })}
            >
              {loadMoreOccurrences.isPending ? "Загружаем…" : "Показать ещё запуски"}
            </button>
          </div>
        )}
        {(occurrences.error || loadMoreOccurrences.error) && <InlineError error={(occurrences.error || loadMoreOccurrences.error) as Error} />}
      </section>
      {editing && (
        <AutomationForm
          mode="edit"
          detail={data}
          onClose={() => setEditing(false)}
          onSaved={(next) => {
            queryClient.setQueryData(["automation", id], next);
            setEditing(false);
            void invalidateControlPlane(queryClient);
          }}
        />
      )}
    </div>
  );
}

function LegacyPollerMigrationDialog({
  onClose,
  onAutomation,
}: {
  onClose: () => void;
  onAutomation: (id: string) => void;
}) {
  const queryClient = useQueryClient();
  const [selection, setSelection] = useState<LegacyPollerSelection>({ confirm_stopped: false });
  const [migrationState, setMigration] = useState<LegacyPollerMigration>();
  const [reviewQueues, setReviewQueues] = useState<LegacyPollerMigration["queues"]>([]);
  const activeMigration = useQuery({
    queryKey: ["legacy-poller-migration", "active"],
    queryFn: api.activeLegacyPollerMigration,
  });
  const migration = migrationState ?? activeMigration.data?.migration ?? undefined;
  const actionSelection = migration?.status === "imported" ? {
    config_path: migration.config_path,
    data_home: migration.data_home,
    working_directory: migration.working_directory,
    confirm_stopped: selection.confirm_stopped,
  } : selection;
  const preview = useMutation({
    mutationFn: () => api.previewLegacyPoller(selection),
    onSuccess: (result) => {
      setMigration(result);
      setReviewQueues(result.queues);
    },
  });
  const importMigration = useMutation({
    mutationFn: (mappings: Array<{ queue_id: string; workflow_title: string; automation_title: string }>) =>
      api.importLegacyPoller({ migration: migration!, selection, mappings }),
    onSuccess: async (result) => {
      setMigration(result);
      await invalidateControlPlane(queryClient);
    },
  });
  const resolveOccurrence = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "resume" | "skip" }) =>
      action === "resume" ? api.resumeLegacyOccurrence(id) : api.skipLegacyOccurrence(id),
    onSuccess: async () => {
      setMigration(await api.legacyPollerMigration(migration!.id));
      await invalidateControlPlane(queryClient);
    },
  });
  const finalize = useMutation({
    mutationFn: () => api.finalizeLegacyPoller({ migration: migration!, selection: actionSelection }),
    onSuccess: async (result) => {
      setMigration(result);
      await invalidateControlPlane(queryClient);
    },
  });
  const unresolved = migration?.occurrences.filter((occurrence) =>
    occurrence.state === "pending" || occurrence.state === "dispatching" || occurrence.state === "failed") ?? [];
  const hasMissingLedgerQueue = reviewQueues.some((queue) => queue.blocking);
  const operationError = activeMigration.error || preview.error || importMigration.error || resolveOccurrence.error || finalize.error;
  const setPath = (field: "config_path" | "data_home" | "working_directory", value: string) =>
    setSelection((current) => ({ ...current, [field]: value || undefined }));
  const submitImport = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const mappings = reviewQueues.filter((queue) => queue.supported).map((queue) => ({
      queue_id: queue.queue_id,
      workflow_title: String(form.get(`workflow-${queue.queue_id}`) ?? "").trim(),
      automation_title: String(form.get(`automation-${queue.queue_id}`) ?? "").trim(),
    }));
    importMigration.mutate(mappings);
  };

  return (
    <div className="modal-layer">
      <button className="modal-scrim" aria-label="Закрыть перенос старого опросчика" onClick={onClose} />
      <div className="modal migration-modal" role="dialog" aria-modal="true" aria-labelledby="legacy-migration-heading">
        <div className="modal-header">
          <div>
            <h2 id="legacy-migration-heading">Перенос старого опросчика</h2>
            <p className="muted">Остановить → Предпросмотр → Импортировать выключенными → Решить ожидающие → Завершить → Включить</p>
          </div>
          <button className="icon-button" aria-label="Закрыть" onClick={onClose}><X size={19} /></button>
        </div>
        <div className="modal-body migration-body">
          {!migration && activeMigration.isPending && <LoadingState label="Проверяем активный перенос" />}
          {!migration && !activeMigration.isPending && (
            <div className="migration-grid">
              <Field label="Старый poller.toml" htmlFor="migration-config" hint="Необязательный абсолютный путь. По умолчанию: ~/.factory/poller.toml">
                <input id="migration-config" value={selection.config_path ?? ""} onChange={(event) => setPath("config_path", event.target.value)} placeholder="/absolute/path/poller.toml" />
              </Field>
              <Field label="Старый каталог данных" htmlFor="migration-home" hint="Необязательный абсолютный путь. По умолчанию: FACTORY_DATA_HOME или ~/.factory">
                <input id="migration-home" value={selection.data_home ?? ""} onChange={(event) => setPath("data_home", event.target.value)} placeholder="/absolute/path/.factory" />
              </Field>
              <Field label="Исходный рабочий каталог" htmlFor="migration-cwd" hint="Нужен, только если старое окружение использовало относительный путь.">
                <input id="migration-cwd" value={selection.working_directory ?? ""} onChange={(event) => setPath("working_directory", event.target.value)} placeholder="/absolute/path" />
              </Field>
              <label className="confirmation-check migration-confirm">
                <input
                  type="checkbox"
                  checked={selection.confirm_stopped}
                  onChange={(event) => setSelection((current) => ({ ...current, confirm_stopped: event.target.checked }))}
                />
                Все процессы factory-poller остановлены. Factory может брать исключительную блокировку на время переноса.
              </label>
              <button className="button button-primary" disabled={!selection.confirm_stopped || preview.isPending} onClick={() => preview.mutate()}>
                {preview.isPending ? <LoaderCircle size={15} className="spin" /> : <DatabaseBackup size={15} />} Проверить заблокированный снимок
              </button>
            </div>
          )}

          {migration && (
            <>
              <section className="migration-summary">
                <div><span>Статус</span><strong>{migration.status}</strong></div>
                <div><span>Очереди</span><strong>{migration.counts.supported_queues} поддерживается · {migration.counts.unsupported_queues} не поддерживается</strong></div>
                <div><span>Наблюдения</span><strong>{migration.counts.submitted_observations} отправлено · {migration.counts.pending_observations} ожидает</strong></div>
                <div><span>Снимок</span><strong className="mono">SHA {migration.snapshot_digest.slice(0, 16)}…</strong></div>
              </section>
              <dl className="migration-paths">
                <div><dt>Конфигурация</dt><dd className="mono">{migration.config_path}</dd></div>
                <div><dt>Каталог данных</dt><dd className="mono">{migration.data_home}</dd></div>
                <div><dt>Исходный рабочий каталог</dt><dd className="mono">{migration.working_directory}</dd></div>
                <div><dt>Старый каталог данных</dt><dd className="mono">{migration.data_directory}</dd></div>
                <div><dt>Журнал</dt><dd className="mono">{migration.ledger_path}</dd></div>
                <div><dt>Корень архива</dt><dd className="mono">{migration.archive_root}</dd></div>
              </dl>
            </>
          )}

          {migration?.status === "previewed" && (
            <form onSubmit={submitImport}>
              <div className="migration-queue-list">
                {reviewQueues.map((queue) => (
                  <section className="panel migration-queue" key={queue.queue_id}>
                    <PanelHeading title={queue.name} aside={queue.supported ? "issue GitHub" : "Не импортируется"} />
                    <p>{queue.project} · {queue.state} · метки {queue.required_labels.join(", ") || "нет"}</p>
                    {queue.supported && <p className="muted">Репозиторий: <span className="mono">{queue.repository_identity}</span> · ID <span className="mono">{queue.repository_id}</span></p>}
                    <p className="muted">{queue.submitted_observations} отправлено · {queue.pending_observations} ожидает · каждые {queue.poll_interval_seconds} с</p>
                    {queue.errors.map((message) => <p className="field-error" key={message}>{message}</p>)}
                    {queue.supported && (
                      <div className="migration-title-grid">
                        <Field label="Название сценария" htmlFor={`workflow-${queue.queue_id}`}>
                          <input id={`workflow-${queue.queue_id}`} name={`workflow-${queue.queue_id}`} autoComplete="off" defaultValue={queue.workflow_title} required />
                        </Field>
                        <Field label="Название автоматизации" htmlFor={`automation-${queue.queue_id}`}>
                          <input id={`automation-${queue.queue_id}`} name={`automation-${queue.queue_id}`} autoComplete="off" defaultValue={queue.automation_title} required />
                        </Field>
                      </div>
                    )}
                  </section>
                ))}
              </div>
              <div className="migration-actions">
                <button type="button" className="button button-secondary" onClick={() => { setMigration(undefined); setReviewQueues([]); }}>Новый предпросмотр</button>
                <button type="submit" className="button button-primary" disabled={hasMissingLedgerQueue || importMigration.isPending}>
                  {importMigration.isPending ? "Импортируем…" : hasMissingLedgerQueue ? "Восстановите отсутствующую очередь" : migration.counts.supported_queues === 0 ? "Перейти к архиву" : "Импортировать выключенными"}
                </button>
              </div>
            </form>
          )}

          {migration && migration.status !== "previewed" && (
            <>
              {migration.status === "imported" && (
                <label className="confirmation-check migration-confirm">
                  <input
                    type="checkbox"
                    checked={selection.confirm_stopped}
                    onChange={(event) => setSelection((current) => ({ ...current, confirm_stopped: event.target.checked }))}
                  />
                  Все процессы factory-poller по-прежнему остановлены.
                </label>
              )}
              {migration.occurrences.length > 0 && (
                <section className="panel">
                  <PanelHeading title="Импортированные наблюдения" aside={`${unresolved.length} не решено`} />
                  <div className="occurrence-list">
                    {migration.occurrences.map((occurrence) => (
                      <div className="occurrence-row" key={occurrence.id}>
                        <span className={`status-badge status-${occurrence.state}`}><span className="status-dot" />{occurrence.state}</span>
                        <span className="occurrence-identity">
                          <strong>{occurrenceIdentity(occurrence)}</strong>
                          <small>{occurrence.diagnostic || occurrence.task_request_key}</small>
                        </span>
                        {(occurrence.state === "pending" || occurrence.state === "failed") && (
                          <div className="detail-actions">
                            {occurrence.state === "pending" && <button className="button button-secondary" disabled={!selection.confirm_stopped || resolveOccurrence.isPending} onClick={() => resolveOccurrence.mutate({ id: occurrence.id, action: "resume" })}>Продолжить</button>}
                            <button className="button button-danger-secondary" disabled={!selection.confirm_stopped || resolveOccurrence.isPending} onClick={() => resolveOccurrence.mutate({ id: occurrence.id, action: "skip" })}>Пропустить</button>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </section>
              )}
              {migration.status === "imported" && (
                <div className="migration-actions">
                  <p className="muted">Завершение проверяет тот же снимок и архивирует копии, не удаляя исходные файлы.</p>
                  <button className="button button-primary" disabled={!selection.confirm_stopped || unresolved.length > 0 || finalize.isPending} onClick={() => finalize.mutate()}>
                    {finalize.isPending ? "Завершаем…" : "Завершить и архивировать"}
                  </button>
                </div>
              )}
              {migration.status === "finalized" && (
                <section className="panel migration-complete">
                  <PanelHeading title="Перенос завершён" aside="Готово к проверке" />
                  <p>Архив: <span className="mono">{migration.archive_path}</span></p>
                  <p className="muted">Проверьте каждую автоматизацию и её триггер, затем включите. Старый опросчик должен оставаться остановленным.</p>
                  <div className="detail-actions">
                    {migration.automations.map((automation) => (
                      <button className="button button-secondary" key={automation.id} onClick={() => onAutomation(automation.id)}>
                        Проверить {automation.title}
                      </button>
                    ))}
                  </div>
                </section>
              )}
            </>
          )}
          {operationError && <InlineError error={operationError as Error} />}
        </div>
        <div className="modal-footer">
          <span className="disabled-first-note"><Activity size={14} /> Импортированные автоматизации выключены до завершения.</span>
          <button className="button button-secondary" onClick={onClose}>Закрыть</button>
        </div>
      </div>
    </div>
  );
}

function AutomationForm({
  mode,
  detail,
  onClose,
  onSaved,
}: {
  mode: "create" | "edit";
  detail?: AutomationDetailType;
  onClose: () => void;
  onSaved: (detail: AutomationDetailType) => void;
}) {
  const queryClient = useQueryClient();
  const titleID = useId();
  const workflowID = useId();
  const repositoryID = useId();
  const triggerTypeID = useId();
  const stateID = useId();
  const labelsID = useId();
  const draftsID = useId();
  const branchesID = useId();
  const intervalID = useId();
  const schedulePresetID = useId();
  const scheduleTimeID = useId();
  const cronID = useId();
  const timezoneID = useId();
  const timeoutID = useId();
  const contextID = useId();
  const titleRef = useRef<HTMLInputElement>(null);
  const advancedRef = useRef<HTMLDetailsElement>(null);
  const closeRef = useRef(onClose);
  const requestRef = useRef<{ fingerprint: string; key: string } | undefined>(undefined);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const workflows = useQuery({ queryKey: ["workflows", "automation-form"], queryFn: api.allWorkflows });
  const repositories = useQuery({ queryKey: ["repositories"], queryFn: api.repositories });
  const current = detail?.automation;
  const [triggerType, setTriggerType] = useState<AutomationTrigger["type"]>(current?.trigger.type ?? "github_issue");
  const [workflowSelection, setWorkflowSelection] = useState(current?.workflow_id ?? "");
  const initialSchedule = scheduleEditorState(current?.trigger);
  const [schedulePreset, setSchedulePreset] = useState<SchedulePreset>(initialSchedule.preset);
  const [scheduleTime, setScheduleTime] = useState(initialSchedule.time);
  const [customCron, setCustomCron] = useState(initialSchedule.cron);
  const isPullRequest = triggerType === "github_pull_request";
  const isSchedule = triggerType === "schedule";
  const selectedRunbook = useQuery({
    queryKey: ["workflow", workflowSelection, "automation-form"],
    queryFn: () => api.workflow(workflowSelection),
    enabled: Boolean(workflowSelection),
  });
  useEffect(() => {
    closeRef.current = onClose;
  }, [onClose]);
  useEffect(() => {
    titleRef.current?.focus();
    const close = (event: KeyboardEvent) => event.key === "Escape" && closeRef.current();
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, []);
  const save = useMutation({
    mutationFn: async (input: CreateAutomationInput) => mode === "create"
      ? api.createAutomation(input)
      : api.updateAutomation({
          id: current!.id,
          input: {
            expected_version: current!.version,
            title: input.title,
            workflow_id: input.workflow_id,
            context: input.context,
            timeout_seconds: input.timeout_seconds,
            trigger: input.trigger,
          },
        }),
    onSuccess: async (next) => {
      await invalidateControlPlane(queryClient);
      onSaved(next);
    },
  });
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const title = String(form.get("title") ?? "").trim();
    const workflow = workflowSelection;
    const repository = current?.repository_id ?? String(form.get("repository_id") ?? "");
    const context = String(form.get("context") ?? "");
    const timeout = Number(form.get("timeout_seconds"));
    const pollInterval = Number(form.get("poll_interval_seconds"));
    const cron = (schedulePreset === "custom" ? customCron : cronForSchedule(schedulePreset, scheduleTime))
      .trim().replace(/\s+/g, " ");
    const timezone = String(form.get("timezone") ?? "").trim();
    const labels = String(form.get("required_labels") ?? "").split(",").map((label) => label.trim()).filter(Boolean);
    const baseBranches = String(form.get("base_branches") ?? "").split(",").map((branch) => branch.trim()).filter(Boolean);
    const nextErrors: Record<string, string> = {};
    if (!title) nextErrors.title = "Введите название автоматизации.";
    else if (Array.from(title).length > 100) nextErrors.title = "Название должно быть не длиннее 100 символов.";
    if (!workflow) nextErrors.workflow = "Выберите сценарий.";
    if (!repository) nextErrors.repository = "Выберите репозиторий.";
    if (!isSchedule && (labels.length > 20 || labels.some((label) => new TextEncoder().encode(label).length > 200))) nextErrors.labels = "Укажите не больше 20 меток по 200 байт.";
    if (isPullRequest && (baseBranches.length > 20 || baseBranches.some((branch) => new TextEncoder().encode(branch).length > 255))) nextErrors.branches = "Укажите не больше 20 базовых веток по 255 байт.";
    if (!isSchedule && (!Number.isInteger(pollInterval) || pollInterval < 10 || pollInterval > 86_400)) nextErrors.interval = "Укажите от 10 до 86 400 секунд.";
    if (isSchedule && schedulePreset !== "custom" && !/^\d{2}:\d{2}$/.test(scheduleTime)) nextErrors.schedule = "Выберите время запуска.";
    if (isSchedule && cron.split(" ").length !== 5) nextErrors.cron = "Введите ровно пять полей Cron без поля секунд.";
    if (isSchedule && !timezone) nextErrors.timezone = "Введите часовой пояс IANA, например Europe/London.";
    if (!Number.isInteger(timeout) || timeout < 1 || timeout > 28_800) nextErrors.timeout = "Укажите от 1 до 28 800 секунд.";
    if (new TextEncoder().encode(context).length > 8 * 1024) nextErrors.context = "Контекст должен занимать не больше 8 KiB.";
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) {
      if (nextErrors.interval || nextErrors.cron || nextErrors.timeout) advancedRef.current?.setAttribute("open", "");
      return;
    }
    const trigger: AutomationTrigger = isSchedule ? {
      type: "schedule",
      cron,
      timezone,
    } : isPullRequest ? {
      type: "github_pull_request",
      state: String(form.get("state")) as "open" | "closed" | "merged",
      include_drafts: form.get("include_drafts") === "on",
      required_labels: labels,
      base_branches: baseBranches,
      poll_interval_seconds: pollInterval,
    } : {
      type: "github_issue",
      state: String(form.get("state")) as "open" | "closed",
      required_labels: labels,
      poll_interval_seconds: pollInterval,
    };
    const payload = {
      title,
      workflow_id: workflow,
      repository_id: repository,
      context,
      timeout_seconds: timeout,
      trigger,
    };
    const fingerprint = JSON.stringify(payload);
    if (requestRef.current?.fingerprint !== fingerprint) {
      requestRef.current = { fingerprint, key: crypto.randomUUID() };
    }
    save.mutate({ request_key: requestRef.current.key, ...payload });
  };
  const workflowItems = workflows.data ?? [];
  const repositoryItems = repositories.data ?? [];
  const selectedWorkflow = workflowItems.find((workflow) => workflow.id === workflowSelection);
  const selectedRepository = current
    ? repositoryItems.find((repository) => repository.id === current.repository_id)
    : undefined;
  return (
    <div className="modal-layer">
      <button className="modal-scrim" aria-label="Закрыть форму автоматизации" onClick={onClose} />
      <div className="modal automation-modal" role="dialog" aria-modal="true" aria-labelledby="automation-form-heading">
        <div className="modal-header">
          <h2 id="automation-form-heading">{mode === "create" ? "Создать автоматизацию" : "Изменить автоматизацию"}</h2>
          <button className="icon-button" aria-label="Закрыть" onClick={onClose}><X size={19} /></button>
        </div>
        <form onSubmit={submit} noValidate>
          <div className="modal-body automation-composer">
            <section className="automation-form-section">
              <div className="automation-section-heading">
                <span>1</span>
                <div><strong>Что запускать?</strong><small>Выберите версию Markdown-инструкций для агента.</small></div>
              </div>
              <div className="automation-form-grid">
                <Field label="Название" htmlFor={titleID} error={errors.title}>
                  <input ref={titleRef} id={titleID} name="title" autoComplete="off" defaultValue={current?.title ?? ""} aria-invalid={Boolean(errors.title)} />
                </Field>
                <Field label="Сценарий" htmlFor={workflowID} error={errors.workflow} hint="Сохранённый Markdown с неизменяемыми версиями.">
                  <select
                    id={workflowID}
                    name="workflow_id"
                    value={workflowSelection}
                    onChange={(event) => setWorkflowSelection(event.target.value)}
                    aria-invalid={Boolean(errors.workflow)}
                  >
                    <option value="">Выберите сценарий</option>
                    {current && !workflowItems.some((workflow) => workflow.id === current.workflow_id) && (
                      <option value={current.workflow_id}>{current.workflow_title}</option>
                    )}
                    {workflowItems.map((workflow) => <option key={workflow.id} value={workflow.id}>{workflow.current_revision.title}{workflow.enabled ? "" : " (выключен)"}</option>)}
                  </select>
                </Field>
              </div>
              {workflowSelection && (
                <div className="runbook-preview" aria-live="polite">
                  <div><BookOpenText size={14} /><strong>{selectedRunbook.data?.workflow.current_revision.title ?? selectedWorkflow?.current_revision.title ?? current?.workflow_title ?? "Сценарий"}</strong><span>{selectedRunbook.data ? `Версия ${selectedRunbook.data.workflow.current_revision.revision_number}` : "Загружаем…"}</span></div>
                  {selectedRunbook.data ? <pre>{selectedRunbook.data.workflow.current_revision.instructions}</pre> : selectedRunbook.error ? <InlineError error={selectedRunbook.error as Error} /> : null}
                </div>
              )}
            </section>

            <section className="automation-form-section">
              <div className="automation-section-heading">
                <span>2</span>
                <div><strong>Где запускать?</strong><small>Каждый запуск изолирован в одном управляемом Git-репозитории.</small></div>
              </div>
              <Field label="Репозиторий" htmlFor={repositoryID} error={errors.repository} hint={mode === "edit" ? "Адрес репозитория неизменяем." : "Выберите один целевой репозиторий."}>
                <select id={repositoryID} name="repository_id" defaultValue={current?.repository_id ?? ""} disabled={mode === "edit"} aria-invalid={Boolean(errors.repository)}>
                  <option value="">Выберите репозиторий</option>
                  {current && <option key={current.repository_id} value={current.repository_id}>
                    {selectedRepository?.remote_identity ?? current.repository_identity}{selectedRepository?.enabled === false ? " (выключен)" : ""}
                  </option>}
                  {repositoryItems.filter((repository) => repository.id !== current?.repository_id).map((repository) => <option key={repository.id} value={repository.id}>{repository.remote_identity}{repository.enabled ? "" : " (выключен)"}</option>)}
                </select>
              </Field>
              <Field label="Контекст автоматизации" htmlFor={contextID} error={errors.context} hint="Необязательный контекст репозитория · 8 KiB">
                <textarea id={contextID} name="context" rows={4} defaultValue={current?.context ?? ""} aria-invalid={Boolean(errors.context)} />
              </Field>
            </section>

            <section className="automation-form-section">
              <div className="automation-section-heading">
                <span>3</span>
                <div><strong>Когда запускать?</strong><small>Реагировать на состояние GitHub или локальное расписание панели управления.</small></div>
              </div>
              <div className="automation-form-grid">
                <Field label="Триггер" htmlFor={triggerTypeID} hint={mode === "edit" ? "Тип триггера неизменяем." : undefined}>
                  <select
                    id={triggerTypeID}
                    name="trigger_type"
                    value={triggerType}
                    disabled={mode === "edit"}
                    onChange={(event) => setTriggerType(event.target.value as AutomationTrigger["type"])}
                  >
                    <option value="github_issue">GitHub issue</option>
                    <option value="github_pull_request">GitHub pull request</option>
                    <option value="schedule">Расписание</option>
                  </select>
                </Field>
                {!isSchedule && <Field key="provider-state" label={isPullRequest ? "Состояние pull request" : "Состояние issue"} htmlFor={stateID}>
                  <select id={stateID} name="state" defaultValue={current?.trigger.type === "github_issue" || current?.trigger.type === "github_pull_request" ? current.trigger.state : "open"}>
                    <option value="open">Открыт</option><option value="closed">Закрыт</option>
                    {isPullRequest && <option value="merged">Слит</option>}
                  </select>
                </Field>}
                {isPullRequest && <>
                  <Field label="Черновики pull request" htmlFor={draftsID} hint="Включать черновики, подходящие под остальные условия.">
                    <label className="confirmation-check" htmlFor={draftsID}>
                      <input id={draftsID} name="include_drafts" type="checkbox" defaultChecked={current?.trigger.type === "github_pull_request" && current.trigger.include_drafts} />
                      Включать черновики
                    </label>
                  </Field>
                  <Field label="Базовые ветки" htmlFor={branchesID} error={errors.branches} hint="Через запятую · необязательно · до 20">
                    <input id={branchesID} name="base_branches" defaultValue={current?.trigger.type === "github_pull_request" ? current.trigger.base_branches.join(", ") : ""} aria-invalid={Boolean(errors.branches)} />
                  </Field>
                </>}
                {isSchedule ? <>
                  <Field key="schedule-frequency" label="Частота" htmlFor={schedulePresetID}>
                    <select id={schedulePresetID} value={schedulePreset} onChange={(event) => setSchedulePreset(event.target.value as SchedulePreset)}>
                      <option value="weekdays">По будням</option>
                      <option value="daily">Каждый день</option>
                      <option value="weekly">Каждый понедельник</option>
                      <option value="custom">Свой Cron</option>
                    </select>
                  </Field>
                  {schedulePreset !== "custom" && <Field key="schedule-time" label="Время" htmlFor={scheduleTimeID} error={errors.schedule}>
                    <input id={scheduleTimeID} type="time" value={scheduleTime} onChange={(event) => setScheduleTime(event.target.value)} aria-invalid={Boolean(errors.schedule)} />
                  </Field>}
                  <Field key="schedule-timezone" label="Часовой пояс" htmlFor={timezoneID} error={errors.timezone} hint="Имя IANA, например Europe/London">
                    <input id={timezoneID} name="timezone" defaultValue={current?.trigger.type === "schedule" ? current.trigger.timezone : Intl.DateTimeFormat().resolvedOptions().timeZone} aria-invalid={Boolean(errors.timezone)} />
                  </Field>
                </> : <Field key="provider-labels" label="Обязательные метки" htmlFor={labelsID} error={errors.labels} hint="Через запятую · до 20">
                  <input id={labelsID} name="required_labels" defaultValue={current?.trigger.type === "github_issue" || current?.trigger.type === "github_pull_request" ? current.trigger.required_labels.join(", ") : "factory:ready"} aria-invalid={Boolean(errors.labels)} />
                </Field>}
              </div>
            </section>

            <details ref={advancedRef} className="automation-advanced">
              <summary><span><SlidersHorizontal size={14} /> Расширенные настройки</span><small>{isSchedule ? `Cron ${schedulePreset === "custom" ? customCron : cronForSchedule(schedulePreset, scheduleTime)}` : `Опрос каждые ${current?.trigger.type === "github_issue" || current?.trigger.type === "github_pull_request" ? current.trigger.poll_interval_seconds : 30} с`} · тайм-аут {current?.timeout_seconds ?? 7200} с</small></summary>
              <div className="automation-form-grid">
                {isSchedule ? <Field key="schedule-cron" label="Cron (пять полей)" htmlFor={cronID} error={errors.cron} hint="Чтобы изменить выражение, выберите выше «Свой Cron».">
                  <input
                    id={cronID}
                    name="cron"
                    className="mono"
                    value={schedulePreset === "custom" ? customCron : cronForSchedule(schedulePreset, scheduleTime)}
                    readOnly={schedulePreset !== "custom"}
                    onChange={(event) => setCustomCron(event.target.value)}
                    aria-invalid={Boolean(errors.cron)}
                  />
                </Field> : <Field key="provider-poll" label="Интервал опроса, секунд" htmlFor={intervalID} error={errors.interval}>
                  <input id={intervalID} name="poll_interval_seconds" type="number" min={10} max={86_400} defaultValue={current?.trigger.type === "github_issue" || current?.trigger.type === "github_pull_request" ? current.trigger.poll_interval_seconds : 30} aria-invalid={Boolean(errors.interval)} />
                </Field>}
                <Field label="Тайм-аут задачи, секунд" htmlFor={timeoutID} error={errors.timeout}>
                  <input id={timeoutID} name="timeout_seconds" type="number" min={1} max={28_800} defaultValue={current?.timeout_seconds ?? 7200} aria-invalid={Boolean(errors.timeout)} />
                </Field>
              </div>
            </details>
            {(workflows.error || repositories.error || save.error) && <InlineError error={(workflows.error || repositories.error || save.error) as Error} />}
          </div>
          <div className="modal-footer">
            <span className="disabled-first-note"><Activity size={14} /> Новые автоматизации создаются выключенными.</span>
            <button type="button" className="button button-secondary" onClick={onClose}>Отмена</button>
            <button type="submit" className="button button-primary" disabled={save.isPending || workflows.isPending || repositories.isPending}>
              {save.isPending ? <><LoaderCircle size={16} className="spin" /> Сохраняем…</> : <><Plus size={16} /> {mode === "create" ? "Создать автоматизацию" : "Сохранить изменения"}</>}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function Field({ label, htmlFor, error, hint, children }: { label: string; htmlFor: string; error?: string; hint?: string; children: ReactNode }) {
  return <div className="field"><label htmlFor={htmlFor}>{label}</label>{children}{error
    ? <span className="field-error">{error}</span>
    : hint ? <span className="field-hint">{hint}</span> : null}</div>;
}

function HealthBadge({ automation }: { automation: Automation }) {
  const status = automation.enabled ? automation.health.status : "disabled";
  const labels: Record<string, string> = { disabled: "выключена", healthy: "работает", checking: "проверяется", idle: "ожидает", warning: "предупреждение", error: "ошибка", blocked: "заблокирована", unknown: "неизвестно" };
  return <span className={`status-badge automation-health status-${status}`}><span className="status-dot" />{labels[status] ?? status}</span>;
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return <div><span>{label}</span><strong>{value}</strong></div>;
}

export function automationHealthMessage(code?: string, message?: string): string {
  const translatedByCode: Record<string, string> = {
    workflow_disabled: "Сценарий выключен.",
    repository_disabled: "Репозиторий выключен.",
    pipeline_patrol_dependencies_disabled: "Патруль конвейера ждёт включения зависимых сценариев.",
    stored_schedule_invalid: "Сохранённое расписание содержит ошибку.",
    occurrence_limit_reached: "Достигнут лимит запусков по расписанию.",
    check_recovered: "Проверка GitHub снова работает.",
    gh_output_too_large: "GitHub вернул слишком большой ответ; сузьте условия отбора.",
    gh_error_output_too_large: "GitHub вернул слишком большое сообщение об ошибке; проверьте доступ.",
    gh_timed_out: "Проверка GitHub не завершилась вовремя.",
    gh_cancelled: "Проверка GitHub была отменена.",
    gh_unauthenticated: "GitHub CLI не авторизован для github.com.",
    gh_permission_denied: "Нет доступа к репозиторию или запросам GitHub.",
    gh_failed: "Проверка GitHub завершилась с ошибкой.",
    gh_malformed_output: "GitHub вернул некорректный ответ.",
    gh_match_limit: "GitHub вернул слишком много подходящих задач; сузьте условия.",
    gh_invalid_output: "GitHub вернул недопустимые данные.",
    gh_conflicting_duplicate: "GitHub вернул противоречивые повторяющиеся данные.",
  };
  if (code) return translatedByCode[code] ?? "Состояние автоматизации требует внимания.";

  const translatedByLegacyMessage: Record<string, string> = {
    "Automation is disabled.": "Автоматизация выключена.",
    "Waiting for the next GitHub check.": "Ожидается следующая проверка GitHub.",
    "Waiting for the next scheduled occurrence.": "Ожидается следующий запуск по расписанию.",
    "Pipeline patrol provisioned from the existing schedule.": "Патруль конвейера настроен по существующему расписанию.",
    "Checking GitHub now.": "GitHub проверяется сейчас.",
    "Run now occurrence admitted.": "Ручной запуск принят.",
  };
  return message ? translatedByLegacyMessage[message] ?? "Состояние автоматизации требует внимания." : "Сведений о состоянии пока нет.";
}

type SchedulePreset = "weekdays" | "daily" | "weekly" | "custom";

function scheduleEditorState(trigger?: AutomationTrigger): { preset: SchedulePreset; time: string; cron: string } {
  const cron = trigger?.type === "schedule" ? trigger.cron : "0 9 * * 1-5";
  const match = /^(\d{1,2}) (\d{1,2}) \* \* (\*|1-5|1)$/.exec(cron);
  if (!match) return { preset: "custom", time: "09:00", cron };
  const [, minute, hour, weekday] = match;
  const preset: SchedulePreset = weekday === "*" ? "daily" : weekday === "1" ? "weekly" : "weekdays";
  return { preset, time: `${hour.padStart(2, "0")}:${minute.padStart(2, "0")}`, cron };
}

function cronForSchedule(preset: SchedulePreset, time: string): string {
  const [hour = "9", minute = "0"] = time.split(":");
  const weekday = preset === "daily" ? "*" : preset === "weekly" ? "1" : "1-5";
  return `${Number(minute)} ${Number(hour)} * * ${weekday}`;
}

function formatRunState(state: string): string {
  const labels: Record<string, string> = {
    task_deleted: "Задача удалена",
    dispatching: "Подготовка",
    dispatched: "Запущено",
    preparing: "Подготовка",
    queued: "В очереди",
    running: "Выполняется",
    succeeded: "Выполнено",
    failed: "Ошибка",
    cancelled: "Отменено",
    lost: "Потеряно",
    pending: "Ожидает",
    skipped: "Пропущено",
  };
  return labels[state] ?? state;
}

function automationRunState(occurrence: AutomationOccurrence): { style: string; label: string } {
	const retryStatus = occurrence.task?.retry_status;
	if (retryStatus) return retryRunState(retryStatus);
  if (occurrence.task) {
    const state = occurrence.task.state;
    const known = new Set(["queued", "preparing", "running", "succeeded", "failed", "cancelled", "lost"]);
    return { style: known.has(state) ? state : "cancelled", label: formatRunState(state) };
  }
  if (occurrence.state === "pending" || occurrence.state === "dispatching") {
    return { style: "preparing", label: "Подготовка" };
  }
  if (occurrence.state === "task_deleted") return { style: "cancelled", label: "Задача удалена" };
  if (occurrence.state === "skipped") return { style: "skipped", label: "Пропущено" };
  return { style: occurrence.state, label: formatRunState(occurrence.state) };
}

function retryRunState(status: NonNullable<AutomationTaskSummary["retry_status"]>): { style: string; label: string } {
	const labels: Record<typeof status, { style: string; label: string }> = {
		queued: { style: "queued", label: "Повтор ожидает запуска" },
		running: { style: "running", label: "Повтор выполняется" },
		succeeded: { style: "succeeded", label: "Повтор выполнен" },
		final_failed: { style: "failed", label: "Сбой после повтора" },
		skipped_disabled: { style: "failed", label: "Сбой — автоматизация отключена" },
		skipped_worker_unavailable: { style: "failed", label: "Сбой — исполнитель недоступен" },
	};
	return labels[status];
}

function triggerSummary(automation: Automation): string {
  if (automation.trigger.type === "schedule") {
    return `Расписание · ${automation.trigger.cron} · ${automation.trigger.timezone}`;
  }
  const labels = automation.trigger.required_labels.length
    ? ` · метки ${automation.trigger.required_labels.join(", ")}`
    : "";
  if (automation.trigger.type === "github_pull_request") {
    const drafts = automation.trigger.include_drafts ? " · с черновиками" : " · без черновиков";
    const bases = automation.trigger.base_branches.length
      ? ` · базовые ветки ${automation.trigger.base_branches.join(", ")}`
      : "";
    return `pull request GitHub · ${automation.trigger.state}${drafts}${labels}${bases}`;
  }
  return `issue GitHub · ${automation.trigger.state}${labels}`;
}

function occurrenceIdentity(occurrence: AutomationOccurrence): string {
  if (occurrence.kind === "scheduled") return `По расписанию: ${occurrence.scheduled_at ? new Date(occurrence.scheduled_at).toISOString() : "сейчас"}`;
  if (occurrence.kind === "run_now") return "Ручной запуск";
  const number = occurrence.pull_request_number ?? occurrence.issue_number ?? 0;
  const title = occurrence.pull_request_title ?? occurrence.issue_title ?? "Неизвестный элемент GitHub";
  return `#${number} ${title}`;
}

function formatTimestamp(value?: string): string {
  return value ? new Date(value).toLocaleString() : "Никогда";
}

function mergeAutomations(...groups: Automation[][]): Automation[] {
  const merged = new Map<string, Automation>();
  for (const automation of groups.flat()) {
    if (!merged.has(automation.id)) merged.set(automation.id, automation);
  }
  return [...merged.values()].sort((left, right) =>
    right.updated_at.localeCompare(left.updated_at) || right.id.localeCompare(left.id));
}

function mergeOccurrences(...groups: AutomationOccurrence[][]): AutomationOccurrence[] {
  const merged = new Map<string, AutomationOccurrence>();
  for (const occurrence of groups.flat()) {
    if (!merged.has(occurrence.id)) merged.set(occurrence.id, occurrence);
  }
  return [...merged.values()].sort((left, right) =>
    right.created_at.localeCompare(left.created_at) || right.id.localeCompare(left.id));
}
