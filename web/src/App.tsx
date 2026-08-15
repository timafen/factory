import { Bell, BookOpenText, Bot, Boxes, FileText, Gauge, GitBranch, KeyRound, Lightbulb, ListChecks, Menu, MessageCircleQuestion, Mic, Plus, Settings as SettingsIcon, Waypoints, Workflow as AutomationIcon, X } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { invalidateControlPlane } from "./controlPlaneQueries";
import { DelegateModal } from "./DelegateModal";
import { Overview } from "./Overview";
import { RepositoriesView, RepositoryDetail } from "./Repositories";
import { TaskDetail } from "./TaskDetail";
import { useVisibleInterval } from "./polling";
import type { Task, TaskPage } from "./types";
import { WorkersView, WorkerDetail } from "./Workers";
import { WorkView } from "./Work";
import { WorkflowDetail, WorkflowsView } from "./Workflows";
import { PipelineView } from "./Pipeline";
import { CardsView } from "./Cards";
import { SayView } from "./Say";
import { EpicsView } from "./Epics";
import { AnswerView } from "./Answer";
import { AccessView } from "./Access";
import { AutomationDetail, AutomationsView } from "./Automations";
import { Settings } from "./Settings";
import { Dialog } from "./Dialog";
import { SandboxKeys } from "./SandboxKeys";
import { ProjectsView } from "./Projects";
import { Reports } from "./Reports";

type Route =
  | { page: "overview" }
	| { page: "reports" }
  | { page: "say" }
  | { page: "epics" }
  | { page: "answer" }
  | { page: "access" }
  | { page: "sandboxKeys" }
  | { page: "work" }
  | { page: "workers" }
  | { page: "repositories" }
  | { page: "projects" }
  | { page: "task"; id: string }
  | { page: "worker"; id: string }
  | { page: "repository"; id: string }
  | { page: "workflows" }
  | { page: "workflow"; id: string }
  | { page: "pipeline" }
  | { page: "cards" }
  | { page: "automations" }
  | { page: "settings" }
  | { page: "dialog" }
  | { page: "automation"; id: string };

function readRoute(): Route {
  const parts = window.location.pathname.split("/").filter(Boolean);
  if (parts[0] === "tasks" && parts[1]) return { page: "task", id: parts[1] };
  if (parts[0] === "workers" && parts[1]) return { page: "worker", id: parts[1] };
  if (parts[0] === "workflows" && parts[1]) return { page: "workflow", id: parts[1] };
  if (parts[0] === "workflows") return { page: "workflows" };
  if (parts[0] === "pipeline") return { page: "pipeline" };
  if (parts[0] === "cards") return { page: "cards" };
  if (parts[0] === "automations" && parts[1]) return { page: "automation", id: parts[1] };
  if (parts[0] === "automations") return { page: "automations" };
  if (parts[0] === "settings") return { page: "settings" };
  if (parts[0] === "dialog") return { page: "dialog" };
  if (parts[0] === "workers") return { page: "workers" };
  if (parts[0] === "repositories" && parts[1]) return { page: "repository", id: parts[1] };
  if (parts[0] === "repositories") return { page: "repositories" };
  if (parts[0] === "projects") return { page: "projects" };
	if (parts[0] === "reports") return { page: "reports" };
  if (parts[0] === "work") return { page: "work" };
  if (parts[0] === "say") return { page: "say" };
  if (parts[0] === "epics") return { page: "epics" };
  if (parts[0] === "answer") return { page: "answer" };
  if (parts[0] === "access") return { page: "access" };
  if (parts[0] === "sandbox-keys") return { page: "sandboxKeys" };
  return { page: "overview" };
}

function routePath(route: Route): string {
  if (route.page === "task") return `/tasks/${route.id}`;
  if (route.page === "worker") return `/workers/${route.id}`;
  if (route.page === "workflow") return `/workflows/${route.id}`;
  if (route.page === "workflows") return "/workflows";
  if (route.page === "pipeline") return "/pipeline";
  if (route.page === "cards") return "/cards";
  if (route.page === "automation") return `/automations/${route.id}`;
  if (route.page === "automations") return "/automations";
  if (route.page === "settings") return "/settings";
  if (route.page === "dialog") return "/dialog";
  if (route.page === "workers") return "/workers";
  if (route.page === "repository") return `/repositories/${route.id}`;
  if (route.page === "repositories") return "/repositories";
  if (route.page === "projects") return "/projects";
	if (route.page === "reports") return "/reports";
  if (route.page === "say") return "/say";
  if (route.page === "epics") return "/epics";
  if (route.page === "answer") return "/answer";
  if (route.page === "access") return "/access";
  if (route.page === "sandboxKeys") return "/sandbox-keys";
  return route.page === "work" ? "/work" : "/";
}

export function App() {
  const [route, setRoute] = useState<Route>(readRoute);
  const [delegateRequest, setDelegateRequest] = useState<{ workerID?: string } | null>(null);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const pendingAnswers = usePendingAnswers();
  const [taskHistory, setTaskHistory] = useState<Task[]>([]);
  const [taskHistoryCursor, setTaskHistoryCursor] = useState<string | null>();
  const previousTaskHeadCursor = useRef<string | null | undefined>(undefined);
  const deletedTaskIDs = useRef(new Set<string>());
  const workInterval = useVisibleInterval(5_000);
  const workerInterval = useVisibleInterval(10_000);
  const delegateTrigger = useRef<HTMLElement | null>(null);
  const queryClient = useQueryClient();

  useEffect(() => {
    const onPopState = () => setRoute(readRoute());
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const navigate = (next: Route) => {
    window.history.pushState({}, "", routePath(next));
    setRoute(next);
    setMobileNavOpen(false);
    window.scrollTo({ top: 0, behavior: "instant" });
  };
  const openDelegate = (workerID?: string) => {
    delegateTrigger.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setDelegateRequest({ workerID });
  };
  const closeDelegate = () => {
    const trigger = delegateTrigger.current;
    setDelegateRequest(null);
    window.setTimeout(() => trigger?.focus(), 0);
  };

  const tasks = useQuery({
    queryKey: ["tasks", "head"],
    queryFn: async () => withoutDeletedTasks(await api.tasks(), deletedTaskIDs.current),
    refetchInterval: workInterval,
  });
  const loadTaskHistory = useMutation({
    mutationFn: async ({ cursor }: { cursor: string; headCursor: string | null }) =>
      withoutDeletedTasks(await api.tasks(cursor), deletedTaskIDs.current),
    onSuccess: (page, request) => {
      setTaskHistory((current) => mergeTasks(page.tasks, current));
      if (previousTaskHeadCursor.current === request.headCursor) {
        setTaskHistoryCursor(page.next_cursor);
      }
    },
  });
  const workers = useQuery({
    queryKey: ["workers"],
    queryFn: api.workers,
    refetchInterval: workerInterval,
  });
  const resumeWork = useMutation({
    mutationFn: api.resumeWork,
    onSuccess: async () => {
      await Promise.all([tasks.refetch(), workers.refetch()]);
    },
  });

  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState === "visible") {
        void invalidateControlPlane(queryClient);
      }
    };
    document.addEventListener("visibilitychange", refresh);
    return () => document.removeEventListener("visibilitychange", refresh);
  }, [queryClient]);

  useEffect(() => {
    if (!tasks.data) return;
    const boundaryChanged = previousTaskHeadCursor.current !== tasks.data.next_cursor;
    setTaskHistoryCursor((current) => boundaryChanged ? tasks.data.next_cursor : current);
    previousTaskHeadCursor.current = tasks.data.next_cursor;
  }, [tasks.data]);

  const taskItems = tasks.data
    ? mergeTasks(tasks.data.tasks, taskHistory)
    : taskHistory.length > 0
      ? taskHistory
      : undefined;

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileNavOpen ? "sidebar-open" : ""}`}>
        <div
          className="brand"
          role="button"
          tabIndex={0}
          title="На главную"
          style={{ cursor: "pointer" }}
          onClick={() => navigate({ page: "overview" })}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") navigate({ page: "overview" }); }}
        >
          <div className="brand-mark" aria-hidden="true">
            <Boxes size={18} strokeWidth={2.2} />
          </div>
          <div>
            <span className="brand-name">Factory</span>
            <span className="brand-subtitle">панель управления</span>
          </div>
        </div>
        <nav aria-label="Основная навигация">
          <button
            className={`nav-item ${route.page === "overview" ? "active" : ""}`}
            aria-current={route.page === "overview" ? "page" : undefined}
            onClick={() => navigate({ page: "overview" })}
          >
            <Gauge size={17} /> Обзор
          </button>
		  <button className={`nav-item ${route.page === "reports" ? "active" : ""}`} aria-current={route.page === "reports" ? "page" : undefined} onClick={() => navigate({ page: "reports" })}>
			<FileText size={17} /> Отчёты
		  </button>
          <button
            className={`nav-item ${route.page === "say" ? "active" : ""}`}
            aria-current={route.page === "say" ? "page" : undefined}
            onClick={() => navigate({ page: "say" })}
          >
            <Mic size={17} /> Say
          </button>
          <button
            className={`nav-item ${route.page === "epics" ? "active" : ""}`}
            aria-current={route.page === "epics" ? "page" : undefined}
            onClick={() => navigate({ page: "epics" })}
          >
            <ListChecks size={17} /> Epics
          </button>
          <button
            className={`nav-item ${route.page === "answer" ? "active" : ""}`}
            aria-current={route.page === "answer" ? "page" : undefined}
            onClick={() => navigate({ page: "answer" })}
          >
            <MessageCircleQuestion size={17} /> Нужен ответ
            {pendingAnswers > 0 && (
              <span
                title={`${pendingAnswers} вопрос(ов) ждут твоего ответа`}
                style={{
                  marginLeft: "auto", minWidth: 20, height: 20, padding: "0 6px",
                  borderRadius: 999, background: "#c0392b", color: "#fff",
                  fontSize: 12, fontWeight: 700, lineHeight: "20px",
                  textAlign: "center", fontVariantNumeric: "tabular-nums",
                }}
              >
                {pendingAnswers}
              </span>
            )}
          </button>
          <a className="nav-item" href="/intake/plan">
            <Lightbulb size={17} /> План
          </a>
          <a className="nav-item" href="/intake/alerts">
            <Bell size={17} /> Уведомления
          </a>
          <button
            className={`nav-item ${route.page === "access" ? "active" : ""}`}
            aria-current={route.page === "access" ? "page" : undefined}
            onClick={() => navigate({ page: "access" })}
          >
            <KeyRound size={17} /> Доступы
          </button>
          <button className={`nav-item ${route.page === "sandboxKeys" ? "active" : ""}`} aria-current={route.page === "sandboxKeys" ? "page" : undefined} onClick={() => navigate({ page: "sandboxKeys" })}>
            <KeyRound size={17} /> Ключи песочницы
          </button>
          
          <button
            className={`nav-item ${route.page === "work" || route.page === "task" ? "active" : ""}`}
            aria-current={route.page === "work" ? "page" : undefined}
            onClick={() => navigate({ page: "work" })}
          >
            <ListChecks size={17} /> Работа
          </button>
          <button
            className={`nav-item ${route.page === "workflows" || route.page === "workflow" ? "active" : ""}`}
            aria-current={route.page === "workflows" ? "page" : undefined}
            onClick={() => navigate({ page: "workflows" })}
          >
            <BookOpenText size={17} /> Сценарии
          </button>
          <button
            className={`nav-item ${route.page === "pipeline" ? "active" : ""}`}
            aria-current={route.page === "pipeline" ? "page" : undefined}
            onClick={() => navigate({ page: "pipeline" })}
          >
            <Waypoints size={17} /> Pipeline
          </button>
          <button
            className={`nav-item ${route.page === "cards" ? "active" : ""}`}
            aria-current={route.page === "cards" ? "page" : undefined}
            onClick={() => navigate({ page: "cards" })}
          >
            <FileText size={17} /> Карточки
          </button>
          <button
            className={`nav-item ${route.page === "automations" || route.page === "automation" ? "active" : ""}`}
            aria-current={route.page === "automations" ? "page" : undefined}
            onClick={() => navigate({ page: "automations" })}
          >
            <AutomationIcon size={17} /> Автоматизации
          </button>
          <button
            className={`nav-item ${route.page === "workers" || route.page === "worker" ? "active" : ""}`}
            aria-current={route.page === "workers" ? "page" : undefined}
            onClick={() => navigate({ page: "workers" })}
          >
            <Bot size={17} /> Исполнители
          </button>
          <button
            className={`nav-item ${route.page === "repositories" || route.page === "repository" ? "active" : ""}`}
            aria-current={route.page === "repositories" ? "page" : undefined}
            onClick={() => navigate({ page: "repositories" })}
          >
            <GitBranch size={17} /> Репозитории
          </button>
          <button
            className={`nav-item ${route.page === "projects" ? "active" : ""}`}
            aria-current={route.page === "projects" ? "page" : undefined}
            onClick={() => navigate({ page: "projects" })}
          >
            <Boxes size={17} /> Проекты
          </button>
          <button
            className={`nav-item ${route.page === "dialog" ? "active" : ""}`}
            aria-current={route.page === "dialog" ? "page" : undefined}
            onClick={() => navigate({ page: "dialog" })}
          >
            <MessageCircleQuestion size={17} /> Диалог
          </button>
          <button
            className={`nav-item ${route.page === "settings" ? "active" : ""}`}
            aria-current={route.page === "settings" ? "page" : undefined}
            onClick={() => navigate({ page: "settings" })}
          >
            <SettingsIcon size={17} /> Настройки
          </button>
        </nav>
        <div className="sidebar-foot">
          <span className="local-dot" aria-hidden="true" />
          Локальная панель управления
        </div>
      </aside>

      <div className="main-shell">
        <header className="topbar">
          <button
            className="icon-button mobile-menu"
            aria-label="Открыть навигацию"
            aria-expanded={mobileNavOpen}
            onClick={() => setMobileNavOpen((open) => !open)}
          >
            {mobileNavOpen ? <X size={19} /> : <Menu size={19} />}
          </button>
          <div className="topbar-title">
            {route.page === "overview" && "Обзор"}
            {route.page === "say" && "Say"}
            {route.page === "epics" && "Epics"}
            {route.page === "answer" && "Нужен ответ"}
            {route.page === "work" && "Работа"}
            {route.page === "workers" && "Исполнители"}
            {route.page === "task" && "Задача"}
            {route.page === "worker" && "Исполнитель"}
            {route.page === "repositories" && "Репозитории"}
            {route.page === "projects" && "Безопасные проекты"}
            {route.page === "repository" && "Репозиторий"}
            {route.page === "workflows" && "Сценарии"}
            {route.page === "workflow" && "Сценарий"}
            {route.page === "pipeline" && "Pipeline"}
            {route.page === "cards" && "Карточки"}
            {route.page === "automations" && "Автоматизации"}
            {route.page === "automation" && "Автоматизация"}
            {route.page === "settings" && "Настройки"}
            {route.page === "dialog" && "Диалог"}
            {route.page === "sandboxKeys" && "Ключи песочницы"}
          </div>
          <button className="button button-primary" onClick={() => openDelegate()}>
            <Plus size={16} /> Поставить задачу
          </button>
        </header>

        <main>
          {route.page === "say" && <SayView />}
          {route.page === "epics" && <EpicsView onTask={(id) => navigate({ page: "task", id })} onAnswer={() => navigate({ page: "answer" })} />}
          {route.page === "answer" && <AnswerView onTask={(id) => navigate({ page: "task", id })} />}
          {route.page === "access" && <AccessView />}
          {route.page === "sandboxKeys" && <SandboxKeys />}
          {route.page === "overview" && <Overview onNav={(p) => navigate({ page: p } as Route)} />}
		  {route.page === "reports" && <Reports />}
          {route.page === "work" && (
            <WorkView
              tasks={taskItems}
              workers={workers.data}
              pending={tasks.isPending}
              error={tasks.error ?? loadTaskHistory.error}
              fetching={tasks.isFetching}
              updatedAt={tasks.dataUpdatedAt}
              onTask={(id) => navigate({ page: "task", id })}
              onAnswer={() => navigate({ page: "answer" })}
              onResume={(base) => resumeWork.mutateAsync(base).then(() => undefined)}
              onDelegate={() => openDelegate()}
              onRefresh={() => void tasks.refetch()}
              hasMore={Boolean(taskHistoryCursor)}
              loadingMore={loadTaskHistory.isPending}
              onLoadMore={() => {
                if (taskHistoryCursor) {
                  loadTaskHistory.mutate({
                    cursor: taskHistoryCursor,
                    headCursor: previousTaskHeadCursor.current ?? null,
                  });
                }
              }}
            />
          )}
          {route.page === "workers" && (
            <WorkersView
              workers={workers.data}
              pending={workers.isPending}
              error={workers.error}
              fetching={workers.isFetching}
              updatedAt={workers.dataUpdatedAt}
              onWorker={(id) => navigate({ page: "worker", id })}
              onRefresh={() => void workers.refetch()}
            />
          )}
          {route.page === "repositories" && (
            <RepositoriesView onRepository={(id) => navigate({ page: "repository", id })} />
          )}
          {route.page === "projects" && <ProjectsView />}
          {route.page === "task" && (
            <TaskDetail
              id={route.id}
              workers={workers.data ?? []}
              onBack={() => navigate({ page: "work" })}
              onDeleted={() => {
                deletedTaskIDs.current.add(route.id);
                queryClient.setQueryData<TaskPage>(["tasks", "head"], (current) =>
                  current
                    ? { ...current, tasks: current.tasks.filter((task) => task.id !== route.id) }
                    : current
                );
                setTaskHistory((current) => current.filter((task) => task.id !== route.id));
                navigate({ page: "work" });
              }}
            />
          )}
          {route.page === "worker" && (
            <WorkerDetail
              id={route.id}
              onBack={() => navigate({ page: "workers" })}
              onDelegate={() => openDelegate(route.id)}
            />
          )}
          {route.page === "repository" && (
            <RepositoryDetail
              id={route.id}
              onBack={() => navigate({ page: "repositories" })}
            />
          )}
          {route.page === "workflows" && (
            <WorkflowsView onWorkflow={(id) => navigate({ page: "workflow", id })} />
          )}
          {route.page === "workflow" && (
            <WorkflowDetail id={route.id} onBack={() => navigate({ page: "workflows" })} />
          )}
          {route.page === "pipeline" && (
            <PipelineView onWorkflow={(id) => navigate({ page: "workflow", id })} />
          )}
          {route.page === "cards" && <CardsView />}
          {route.page === "settings" && <Settings />}
          {route.page === "dialog" && <Dialog />}
          {route.page === "automations" && (
            <AutomationsView onAutomation={(id) => navigate({ page: "automation", id })} />
          )}
          {route.page === "automation" && (
            <AutomationDetail
              id={route.id}
              onBack={() => navigate({ page: "automations" })}
              onTask={(taskID) => navigate({ page: "task", id: taskID })}
            />
          )}
        </main>
      </div>

      {mobileNavOpen && (
        <button
          className="nav-scrim"
          aria-label="Закрыть навигацию"
          onClick={() => setMobileNavOpen(false)}
        />
      )}
      {delegateRequest && (
        <DelegateModal
          workers={workers.data ?? []}
          workersPending={workers.isPending}
          initialWorkerID={delegateRequest.workerID}
          onClose={closeDelegate}
          onCreated={(id) => {
            setDelegateRequest(null);
            navigate({ page: "task", id });
          }}
        />
      )}
    </div>
  );
}

function mergeTasks(...groups: Task[][]): Task[] {
  const unique = new Map<string, Task>();
  for (const group of groups) {
    for (const task of group) {
      if (!unique.has(task.id)) unique.set(task.id, task);
    }
  }
  return [...unique.values()].sort((left, right) => {
    const created = Date.parse(right.created_at) - Date.parse(left.created_at);
    if (created !== 0) return created;
    if (left.id === right.id) return 0;
    return left.id < right.id ? 1 : -1;
  });
}

function withoutDeletedTasks(page: TaskPage, deletedTaskIDs: Set<string>): TaskPage {
  return {
    ...page,
    tasks: page.tasks.filter((task) => !deletedTaskIDs.has(task.id)),
  };
}

/** Сколько вопросов ждёт владельца. Опрашивается редко и только когда вкладка
 *  видима — цифра нужна живая, но не ценой лишней нагрузки. */
function usePendingAnswers(): number {
  const [n, setN] = useState(0);
  useEffect(() => {
    let alive = true;
    const pull = async () => {
      if (document.hidden) return;
      try {
        const r = await fetch("/api/v1/questions");
        if (!r.ok) return;
        const d = (await r.json()) as { questions?: { status?: string }[] };
        const open = (d.questions ?? []).filter(
          (q) => q.status === "open",
        ).length;
        if (alive) setN(open);
      } catch { /* тихо: цифра не критична */ }
    };
    void pull();
    const h = window.setInterval(() => void pull(), 15000);
    const onVis = () => void pull();
    document.addEventListener("visibilitychange", onVis);
    return () => {
      alive = false;
      window.clearInterval(h);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);
  return n;
}
