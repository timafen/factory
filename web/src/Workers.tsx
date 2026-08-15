import {
  ArrowLeft,
  Bot,
  Check,
  ChevronRight,
  Copy,
  GitBranch,
  HardDrive,
  LoaderCircle,
  Play,
  Plus,
  Server,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useId, useState, type KeyboardEvent, type ReactNode } from "react";
import { api } from "./api";
import { runtimeLabel, stateLabel, timeAgo } from "./format";
import { useVisibleInterval } from "./polling";
import type { Worker } from "./types";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PanelHeading,
  StaleBanner,
  ViewHeader,
  type ViewStateProps,
} from "./ui";

const workerTabs = ["overview", "work", "capabilities", "settings"] as const;
type WorkerTab = (typeof workerTabs)[number];

const workerTabLabel: Record<WorkerTab, string> = {
  overview: "Обзор",
  work: "Работа",
  capabilities: "Возможности",
  settings: "Настройки",
};

export function WorkersView({
  workers,
  pending,
  error,
  fetching,
  updatedAt,
  onWorker,
  onRefresh,
}: ViewStateProps & {
  workers?: Worker[];
  pending: boolean;
  error: Error | null;
  onWorker: (id: string) => void;
}) {
  if (pending) return <LoadingState label="Загружаем исполнителей" />;
  if (error && !workers) return <ErrorState error={error} onRetry={onRefresh} />;
  const registered = workers ?? [];
  const online = registered.filter((worker) => worker.online).length;
  const availableSlots = registered.reduce(
    (total, worker) =>
      worker.online && worker.health === "healthy"
        ? total + Math.max(worker.capacity - worker.active_count, 0)
        : total,
    0,
  );

  return (
    <div className="page">
      <ViewHeader
        title="Исполнители"
        fetching={fetching}
        updatedAt={updatedAt}
        onRefresh={onRefresh}
      />
      {error && <StaleBanner error={error} />}
      {registered.length === 0 ? (
        <EmptyState
          icon={<Server size={22} />}
          title="Нет зарегистрированных исполнителей"
          description="Запустите исполнитель Factory — после регистрации он появится здесь автоматически."
        />
      ) : (
        <>
          <div className="fleet-summary" aria-label="Сводка исполнителей">
            <div><span>Зарегистрировано</span><strong>{registered.length}</strong></div>
            <div><span>В сети</span><strong>{online}</strong></div>
            <div><span>Свободно мест</span><strong>{availableSlots}</strong></div>
          </div>
          <div className="workers-list">
            <div className="worker-table-head" aria-hidden="true">
              <span>Исполнитель</span><span>Загрузка</span><span>Репозитории</span><span>Версии</span><span>Последний контакт</span><span />
            </div>
            {registered.map((worker) => (
              <button className="worker-row" key={worker.id} onClick={() => onWorker(worker.id)}>
                <span className="worker-identity">
                  <span className="worker-avatar"><Bot size={17} /></span>
                  <span>
                    <span className="worker-name-line">
                      <strong>{worker.name}</strong>
                      <span className={`presence ${worker.online ? "online" : "offline"}`} aria-hidden="true" />
                    </span>
                    <span className={`runtime-badge runtime-${worker.runtime}`}>
                      <Play size={10} /> {runtimeLabel(worker.runtime)}
                    </span>
                    <small>
                      {worker.online ? "В сети" : "Не в сети"} ·{" "}
                      <span className={worker.health === "healthy" ? "healthy-text" : "danger-text"}>
                        {stateLabel(worker.health)}
                      </span>
                    </small>
                    {worker.current_task_title && <em>{worker.current_task_title}</em>}
                  </span>
                </span>
                <span className="capacity-cell">
                  <strong>{worker.active_count}/{worker.capacity}</strong>
                  <span className="capacity-bar" aria-label={`${worker.active_count} из ${worker.capacity} мест занято`}>
                    <span style={{ width: `${(worker.active_count / worker.capacity) * 100}%` }} />
                  </span>
                </span>
                <span className="repo-list">
                  {worker.repositories.map((repo) => <span className="tag" key={repo.id}>{repo.key}</span>)}
                </span>
                <span className="versions">
                  <small>{runtimeLabel(worker.runtime)} {worker.runtime_version || "неизвестно"}</small>
                  <small>Исполнитель {worker.worker_version || "неизвестно"}</small>
                </span>
                <span className="last-seen">{timeAgo(worker.last_heartbeat)}</span>
                <ChevronRight size={16} className="row-chevron" aria-hidden="true" />
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export function WorkerDetail({
  id,
  onBack,
  onDelegate,
}: {
  id: string;
  onBack: () => void;
  onDelegate: () => void;
}) {
  const interval = useVisibleInterval(10_000);
  const worker = useQuery({
    queryKey: ["worker", id],
    queryFn: () => api.worker(id),
    refetchInterval: interval,
  });
  const [copied, setCopied] = useState<string>();
  const [activeTab, setActiveTab] = useState<WorkerTab>("overview");
  const tabIDPrefix = useId();

  if (worker.isPending) return <LoadingState label="Загружаем исполнителя" />;
  if (!worker.data) return <ErrorState error={worker.error} onRetry={() => void worker.refetch()} />;

  const data = worker.data;
  const tabID = (tab: WorkerTab) => `${tabIDPrefix}-tab-${tab}`;
  const tabPanelID = (tab: WorkerTab) => `${tabIDPrefix}-panel-${tab}`;
  const grouped = (data.retained_worktrees ?? []).reduce((groups, worktree) => {
    const current = groups.get(worktree.repository_id) ?? [];
    current.push(worktree);
    groups.set(worktree.repository_id, current);
    return groups;
  }, new Map<string, Worker["retained_worktrees"]>());
  const copy = async (attemptID: string, command: string) => {
    await navigator.clipboard.writeText(command);
    setCopied(attemptID);
    window.setTimeout(() => setCopied(undefined), 1_500);
  };
  const selectTabFromKeyboard = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let nextIndex: number | undefined;
    if (event.key === "ArrowRight") nextIndex = (index + 1) % workerTabs.length;
    if (event.key === "ArrowLeft") nextIndex = (index - 1 + workerTabs.length) % workerTabs.length;
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = workerTabs.length - 1;
    if (nextIndex === undefined) return;
    event.preventDefault();
    const nextTab = workerTabs[nextIndex];
    setActiveTab(nextTab);
    document.getElementById(tabID(nextTab))?.focus();
  };
  const tabPanel = (tab: WorkerTab, content: ReactNode) => (
    <div
      className="worker-tab-panel"
      role="tabpanel"
      id={tabPanelID(tab)}
      aria-labelledby={tabID(tab)}
      hidden={activeTab !== tab}
      tabIndex={0}
    >
      {content}
    </div>
  );
  const activeSessions = `${data.active_count} занято`;
  const latestActiveTask = data.active_count > 1 ? `Последняя из сеансов: ${activeSessions}` : activeSessions;

  return (
    <div className="page detail-page">
      <button className="back-button" onClick={onBack}><ArrowLeft size={16} /> Все исполнители</button>
      <div className="detail-heading worker-detail-heading">
        <div className="worker-detail-identity">
          <span className="worker-avatar worker-avatar-large"><Bot size={25} /></span>
          <div>
            <div className="worker-state-line">
              <span className={`presence ${data.online ? "online" : "offline"}`} aria-hidden="true" />
              <span>{data.online ? "В сети" : "Не в сети"}</span>
              <span>·</span>
              <span className={data.health === "healthy" ? "healthy-text" : "danger-text"}>{stateLabel(data.health)}</span>
            </div>
            <h1>{data.name}</h1>
            <div className="worker-profile-meta">
              <span className={`runtime-badge runtime-${data.runtime}`}>
                <Play size={10} /> {runtimeLabel(data.runtime)}
              </span>
              <span>{data.active_count} / {data.capacity} сеансов занято</span>
              <span>Последний контакт {timeAgo(data.last_heartbeat)}</span>
            </div>
          </div>
        </div>
        <div className="detail-actions">
          <button className="button button-primary" onClick={onDelegate}>
            <Plus size={15} /> Назначить работу
          </button>
        </div>
      </div>
      {worker.error && <StaleBanner error={worker.error} />}

      <div className="worker-tabs" role="tablist" aria-label="Профиль исполнителя">
        {workerTabs.map((tab, index) => (
          <button
            type="button"
            role="tab"
            id={tabID(tab)}
            aria-controls={tabPanelID(tab)}
            aria-selected={activeTab === tab}
            tabIndex={activeTab === tab ? 0 : -1}
            key={tab}
            onClick={() => setActiveTab(tab)}
            onKeyDown={(event) => selectTabFromKeyboard(event, index)}
          >
            {workerTabLabel[tab]}
          </button>
        ))}
      </div>

      {tabPanel("overview",
        <>
          <section className="worker-summary-grid" aria-label="Сводка исполнителя">
            <div><span>Статус</span><strong>{data.online ? "В сети" : "Не в сети"}</strong><small>{stateLabel(data.health)}</small></div>
            <div><span>Сеансы</span><strong>{data.active_count} / {data.capacity}</strong><small>занято</small></div>
            <div><span>Репозитории</span><strong>{data.repositories.length}</strong><small>объявлено</small></div>
            <div><span>Рабочие копии</span><strong>{data.retained_worktrees?.length ?? 0}</strong><small>сохранено</small></div>
          </section>
          <div className="worker-overview-layout">
            <section className="panel">
              <PanelHeading title="Профиль" />
              <dl className="metadata">
                <div><dt>runtime</dt><dd>{runtimeLabel(data.runtime)}</dd></div>
                <div><dt>Последний контакт</dt><dd>{timeAgo(data.last_heartbeat)}</dd></div>
                <div><dt>Зарегистрирован</dt><dd>{new Date(data.registered_at).toLocaleString()}</dd></div>
                <div><dt>ID исполнителя</dt><dd><span className="worker-id" title={data.id}>{data.id}</span></dd></div>
              </dl>
            </section>
            <section className="panel">
              <PanelHeading title="Последняя активная задача" aside={latestActiveTask} />
              {data.current_task_title ? (
                <div className="current-work"><LoaderCircle size={17} className="spin" /> {data.current_task_title}</div>
              ) : data.active_count > 0 ? (
                <div className="quiet-empty">Название активной задачи пока не передано.</div>
              ) : (
                <div className="quiet-empty">Исполнитель готов к следующей задаче.</div>
              )}
            </section>
          </div>
        </>,
      )}

      {tabPanel("work",
        <>
          <section className="panel">
            <PanelHeading title="Последняя активная задача" aside={latestActiveTask} />
            {data.current_task_title ? (
              <div className="current-work"><LoaderCircle size={17} className="spin" /> {data.current_task_title}</div>
            ) : data.active_count > 0 ? (
              <div className="quiet-empty">Название активной задачи пока не передано.</div>
            ) : (
              <div className="quiet-empty">Исполнитель готов к следующей задаче.</div>
            )}
          </section>
          <section className="panel">
            <PanelHeading title="Сохранённые рабочие копии" aside={`${data.retained_worktrees?.length ?? 0} сохранено`} />
            {(data.retained_worktrees ?? []).length === 0 ? (
              <div className="quiet-empty">Нет рабочих копий для локальной проверки или очистки.</div>
            ) : (
              [...grouped.entries()].map(([repositoryID, worktrees]) => {
                const repo = data.repositories.find((candidate) => candidate.id === repositoryID);
                return (
                  <div className="worktree-group" key={repositoryID}>
                    <h3>{repo?.key ?? `Репозиторий ${repositoryID}`}</h3>
                    {worktrees.map((worktree) => (
                      <div className="worktree-card" key={worktree.attempt_id}>
                        <div className="worktree-title">
                          <HardDrive size={16} />
                          <span><strong>Попытка {worktree.attempt_id}</strong><small>{worktree.reason}</small></span>
                        </div>
                        <div className="worktree-path">{worktree.path}</div>
                        <div className="command-row">
                          <code>{worktree.cleanup_command}</code>
                          <button className="icon-button" aria-label={`Скопировать команду очистки для ${worktree.attempt_id}`} onClick={() => void copy(worktree.attempt_id, worktree.cleanup_command)}>
                            {copied === worktree.attempt_id ? <Check size={16} /> : <Copy size={16} />}
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                );
              })
            )}
          </section>
        </>,
      )}

      {tabPanel("capabilities",
        <>
          <div className="worker-capabilities-layout">
            <section className="panel">
              <PanelHeading title="Возможности runtime" />
              <dl className="metadata">
                <div><dt>runtime</dt><dd>{runtimeLabel(data.runtime)}</dd></div>
                <div><dt>Версия runtime</dt><dd>{data.runtime_version || "Неизвестно"}</dd></div>
                <div><dt>Версия исполнителя</dt><dd>{data.worker_version || "Неизвестно"}</dd></div>
                <div><dt>Управляемые репозитории</dt><dd>{data.accepts_managed_repositories ? "Принимаются" : "Не объявлено"}</dd></div>
                <div><dt>Кэш репозиториев</dt><dd>{data.repository_cache_count ?? 0} в кэше</dd></div>
              </dl>
            </section>
            <section className="panel">
              <PanelHeading title="Доступ к источникам" aside={`${data.source_access?.length ?? 0} объявлено`} />
              {(data.source_access ?? []).length === 0 ? (
                <div className="quiet-empty">Исполнитель не объявил поставщиков исходного кода.</div>
              ) : (
                <div className="capability-list">
                  {(data.source_access ?? []).map((source) => (
                    <div key={`${source.provider}-${source.hostname}`}>
                      <strong>{source.provider}</strong>
                      <span>{source.hostname}</span>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>
          <section className="panel">
            <PanelHeading title="Репозитории" aside={`${data.repositories.length} объявлено`} />
            {data.repositories.length === 0 ? (
              <div className="quiet-empty">Устаревшие рабочие копии репозиториев не объявлены.</div>
            ) : (
              <div className="repository-rows">
                {data.repositories.map((repo) => (
                  <div className="repository-row" key={repo.id}>
                    <GitBranch size={17} />
                    <span><strong>{repo.key}</strong><small>{repo.remote_identity}</small></span>
                    <span className="retained-count">{repo.retained_count} сохранено</span>
                  </div>
                ))}
              </div>
            )}
          </section>
        </>,
      )}

      {tabPanel("settings",
        <>
          <section className="panel execution-settings-card">
            <PanelHeading title="Выполнение" aside="Только чтение" />
            <div className="execution-settings-grid">
              <div className="execution-setting">
                <span>runtime</span>
                <strong>{runtimeLabel(data.runtime)}</strong>
                <small>Один тип runtime на идентификатор исполнителя.</small>
              </div>
              <div className="execution-setting execution-concurrency">
                <span>Параллельность</span>
                <strong>{data.active_count} / {data.capacity}</strong>
                <small>сеансов занято</small>
                <meter
                  min={0}
                  max={data.capacity}
                  value={Math.min(data.active_count, data.capacity)}
                  aria-label="Параллельность исполнителя"
                />
              </div>
            </div>
            <div className="execution-owner-note">
              <strong>Управляется конфигурацией исполнителя</strong>
              <p>
                При запуске Factory читает <code>runtime</code> и <code>max_concurrent</code> из TOML исполнителя.
                Чтобы изменить параллельность, обновите файл и перезапустите исполнитель. runtime неизменяем для
                существующего идентификатора; для другого runtime используйте отдельные конфигурацию и каталог данных.
              </p>
            </div>
          </section>
          <section className="panel">
            <PanelHeading title="Настройки runtime" />
            <p className="settings-copy">
              Модель, глубина рассуждений, скорость и аргументы runtime остаются в установленной конфигурации Codex
              или Claude Code. Factory показывает возможности выполнения, но не меняет настройки поставщика.
            </p>
          </section>
        </>,
      )}
    </div>
  );
}
