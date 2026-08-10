import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import { WorkView } from "./Work";
import type { Task } from "./types";

const now = new Date().toISOString();

function task(id: string, title: string, state: Task["state"]): Task {
  return {
    id, request_key: id, title, state, created_at: now,
    worker_id: "", repository_id: "", timeout_seconds: 60,
  };
}

function mockAPI(data: Record<string, unknown>) {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input);
    if (path.startsWith("/api/v1/work-history?")) return Response.json({ history: [] });
    if (path === "/api/v1/verdicts") return Response.json(data.verdicts ?? { verdicts: {} });
    if (path === "/api/v1/questions") return Response.json(data.questions ?? { questions: [] });
    if (path === "/api/v1/works") return Response.json(data.works ?? {});
    if (path === "/api/v1/work-status") return Response.json(data.statuses ?? {});
    if (path === "/api/v1/promises") return Response.json({});
    return Response.json({});
  }));
}

function view(tasks: Task[], handlers: { onAnswer?: () => void; onResume?: () => void } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><WorkView tasks={tasks} workers={[]} pending={false} error={null}
    fetching={false} updatedAt={Date.now()} onTask={() => undefined}
    onDelegate={() => undefined} onRefresh={() => undefined}
    hasMore={false} loadingMore={false} onLoadMore={() => undefined} {...handlers} /></QueryClientProvider>);
}

afterEach(() => vi.unstubAllGlobals());

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
  fireEvent.click(screen.getByRole("button", { name: "Продолжить в настройках →" }));
  expect(answer).toHaveBeenCalledOnce();
  expect(resume).toHaveBeenCalledOnce();

  expect(screen.getByRole("button", { name: "Архив · 1" })).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Архив · 1" }));
  expect(screen.getByText("Отменённая")).toBeVisible();
});

it("uses one mobile-column explanation card", async () => {
  mockAPI({});
  view([task("running", "[auto] [3/5 Implement + Test] Узкая карточка", "running")]);
  expect(await screen.findByLabelText("Что будет дальше")).toHaveClass("work-explanation");
});
