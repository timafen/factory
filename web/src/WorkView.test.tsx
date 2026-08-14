import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import { WorkView } from "./Work";
import type { Task } from "./types";

const now = new Date().toISOString();

function task(id: string, title: string, state: Task["state"], workID?: string): Task {
  return {
    id, work_id: workID, request_key: id, title, state, created_at: now,
    worker_id: "", repository_id: "", timeout_seconds: 60,
  };
}

function mockAPI(data: Record<string, unknown>) {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input);
    if (path.startsWith("/api/v1/work-history?")) return Response.json({ history: data.history ?? [] });
    if (path === "/api/v1/verdicts") return Response.json(data.verdicts ?? { verdicts: {} });
    if (path === "/api/v1/questions") return Response.json(data.questions ?? { questions: [] });
    if (path === "/api/v1/works") return Response.json(data.works ?? {});
    if (path === "/api/v1/work-status") return Response.json(data.statuses ?? {});
    if (path === "/api/v1/promises") return Response.json({});
    return Response.json({});
  }));
}

function view(tasks: Task[], handlers: { onAnswer?: () => void; onResume?: (base: string) => void | Promise<void> } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><WorkView tasks={tasks} workers={[]} pending={false} error={null}
    fetching={false} updatedAt={Date.now()} onTask={() => undefined}
    onDelegate={() => undefined} onRefresh={() => undefined}
    hasMore={false} loadingMore={false} onLoadMore={() => undefined} {...handlers} /></QueryClientProvider>);
}

afterEach(() => vi.unstubAllGlobals());

it("separates queued work from work running right now", async () => {
  mockAPI({ works: { "Уже выполняется": { origin: "assistant" } } });
  view([
    task("running", "[auto] [3/5 Implement + Test] Уже выполняется", "running"),
    task("queued", "[auto] [4/5 Review] Ждёт исполнителя", "queued"),
  ]);

  const runningSection = (await screen.findByRole("heading", { name: "В работе прямо сейчас" }))
    .parentElement?.parentElement as HTMLElement;
  const queuedSection = screen.getByRole("heading", { name: "Ожидают исполнителя" })
    .parentElement?.parentElement as HTMLElement;

  expect(within(runningSection).getByText("Уже выполняется")).toBeVisible();
  expect(within(runningSection).queryByText("Ждёт исполнителя")).not.toBeInTheDocument();
  expect(within(queuedSection).getAllByText("Ждёт исполнителя")).toHaveLength(2);
  expect(within(queuedSection).queryByText("Уже выполняется")).not.toBeInTheDocument();
  expect(screen.getByText("Текущий этап поставлен в очередь и ещё не выполняется.")).toBeVisible();
  expect(screen.getByText("поставил помощник")).toBeVisible();
  expect(screen.getAllByText("Ждёт исполнителя")).toHaveLength(2);
  expect(screen.getByText("Текущий этап ещё не начат")).toBeVisible();
});

it("shows equal work names as independently expandable cards", async () => {
  mockAPI({ history: [
    { task_id: "first", text: "История первой работы" },
    { task_id: "second", text: "История второй работы" },
  ] });
  view([
    task("first", "[auto] [1/5 Triage] Одинаковое название", "running", "work-first"),
    task("second", "[auto] [1/5 Triage] Одинаковое название", "running", "work-second"),
  ]);

  const cards = await screen.findAllByText("Одинаковое название");
  expect(cards).toHaveLength(2);
  expect(screen.queryByText("work-first")).not.toBeInTheDocument();
  fireEvent.click(cards[0]);
  expect(await screen.findByText("История первой работы")).toBeVisible();
  expect(screen.queryByText("История второй работы")).not.toBeInTheDocument();
});

it("names the work screen and task queue by their meaning", async () => {
  mockAPI({});
  view([task("running", "[auto] [1/5 Triage] Запущенный этап", "running")]);

  expect(await screen.findByRole("heading", { name: "Работа" })).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Показать по этапам" }));
  expect(screen.getByRole("heading", { name: "Задачи: ожидают запуска" })).toBeVisible();
  expect(screen.getAllByText("Таких задач нет").length).toBeGreaterThan(0);
});

it("separates owner decision, pause, dead end, automatic repair, and archive", async () => {
  const answer = vi.fn();
  const resume = vi.fn();
  const tasks = [
    task("question", "[auto] [3/5 Implement + Test] Нужен выбор", "running"),
    task("paused", "[auto] [4/5 Review] Пауза владельца", "failed"),
    task("stuck", "[auto] [4/5 Review] Настоящий тупик", "failed"),
    task("verify", "[auto] [5/5 Verify] Автодоработка", "succeeded"),
    task("retry", "[auto] [3/5 Implement + Test] Автодоработка", "running"),
    task("cancelled", "[auto] [3/5 Implement + Test] Отменённая", "cancelled"),
  ];
  mockAPI({
    verdicts: { verdicts: { verify: { final_pass: false, stage: "Verify" } } },
    questions: { questions: [{ task_id: "question", status: "open", question: "Какой вариант выбрать?" }] },
    statuses: {
      "Пауза владельца": { state: "stopped_owner", text: "остановлена: конвейер по этой работе на паузе" },
      "Настоящий тупик": { state: "stuck", text: "следующий этап не запускается" },
    },
  });
  view(tasks, { onAnswer: answer, onResume: resume });

  expect(await screen.findByRole("heading", { name: "Нужно твоё решение" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "Поставлено на паузу" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "Factory не может продолжить" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "Исправляется автоматически" })).toBeVisible();
  expect(screen.getAllByText("Что случилось").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Дальше Factory").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Твоё участие").length).toBeGreaterThan(0);
  expect(screen.queryByText("Не вышло / остановлено")).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Ответить Factory →" }));
  fireEvent.click(screen.getByRole("button", { name: "Продолжить" }));
  expect(answer).toHaveBeenCalledOnce();
  expect(resume).toHaveBeenCalledOnce();
  expect(resume).toHaveBeenCalledWith("Пауза владельца");

  expect(screen.getByRole("button", { name: "Архив · 1" })).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Архив · 1" }));
  expect(screen.getByText("Отменённая")).toBeVisible();
});

it("uses one mobile-column explanation card", async () => {
  mockAPI({});
  view([task("running", "[auto] [3/5 Implement + Test] Узкая карточка", "running")]);
  expect(await screen.findByLabelText("Что будет дальше")).toHaveClass("work-explanation");
});

it("keeps the paused card and shows the resume error", async () => {
  const tasks = [task("paused", "[auto] [1/5 Triage] Ошибка продолжения", "failed")];
  mockAPI({ statuses: { "Ошибка продолжения": { state: "stopped_owner", text: "пауза" } } });
  view(tasks, { onResume: () => Promise.reject(new Error("Нет доступного исполнителя")) });

  fireEvent.click(await screen.findByRole("button", { name: "Продолжить" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Продолжение не выполнено. Проверь состояние Factory и повтори попытку.");
  expect(screen.queryByText("Нет доступного исполнителя")).not.toBeInTheDocument();
  expect(screen.queryByText(/same-origin|cross_origin_request/i)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Продолжить" })).toBeVisible();
});

it("shows an answered heavy work reservation as waiting for a slot, not for an owner", async () => {
  const title = "Весь HTTPS-набор проходит с реальным service worker";
  mockAPI({
    questions: { questions: [{
      task_id: "https", status: "answered",
      reservation: { stage: "Implement + Test" },
      escalation_reason: "ответ принят, ожидает зарезервированный слот из-за загрузки сервера",
    }] },
  });
  view([task("https", `[auto] [3/5 Implement + Test] ${title}`, "failed")]);

  const queued = await screen.findByRole("heading", { name: "В очереди" });
  expect(queued.parentElement?.parentElement).toHaveTextContent("Ответ принят — слот зарезервирован");
  expect(screen.getByText("Ответ владельца принят; эта работа ждёт зарезервированный слот.")).toBeVisible();
  expect(screen.getByText("ответ принят, ожидает зарезервированный слот из-за загрузки сервера")).toBeVisible();
  expect(screen.queryByRole("heading", { name: "Нужно твоё решение" })).not.toBeInTheDocument();
});

it("shows the reason for every repeated Review return", async () => {
  const tasks = [
    { ...task("review-1", "[auto] [4/5 Review] Повторные возвраты", "succeeded"), created_at: "2026-08-10T10:01:00Z" },
    { ...task("implement-1", "[auto] [3/5 Implement + Test] Повторные возвраты", "succeeded"), created_at: "2026-08-10T10:02:00Z" },
    { ...task("review-2", "[auto] [4/5 Review] Повторные возвраты", "succeeded"), created_at: "2026-08-10T10:03:00Z" },
    { ...task("implement-2", "[auto] [3/5 Implement + Test] Повторные возвраты", "running"), created_at: "2026-08-10T10:04:00Z" },
  ];
  mockAPI({
    verdicts: { verdicts: {
      "review-1": { stage: "Review", action: "stop", return_reason: "Нет проверки двойной оплаты" },
      "review-2": { stage: "Review", action: "stop", return_reason: "Нет проверки двойной оплаты" },
    } },
  });
  view(tasks);

  expect(await screen.findByRole("heading", { name: "Исправляется автоматически" })).toBeVisible();
  fireEvent.click(screen.getByText("Повторные возвраты"));
  expect(screen.getAllByText("Причина возврата: Нет проверки двойной оплаты")).toHaveLength(2);
});
