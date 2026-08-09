import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import { WorkView } from "./Work";
import type { Task } from "./types";

const task: Task = {
  id: "task-history",
  request_key: "history",
  title: "[auto] [3/5 Implement + Test] Понятная история",
  worker_id: "",
  repository_id: "",
  timeout_seconds: 60,
  state: "succeeded",
  created_at: new Date().toISOString(),
};

function renderHistory(tasks: Task[] = [task]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}>
    <WorkView tasks={tasks} workers={[]} pending={false} error={null}
      fetching={false} updatedAt={Date.now()} onTask={() => undefined}
      onDelegate={() => undefined} onRefresh={() => undefined}
      hasMore={false} loadingMore={false} onLoadMore={() => undefined} />
  </QueryClientProvider>);
}

afterEach(() => vi.unstubAllGlobals());

it("shows the short Russian history returned by the API", async () => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input);
    if (path.startsWith("/api/v1/work-history?")) {
      return Response.json({ history: [{ task_id: task.id, text: "Этап успешно завершён" }] });
    }
    return Response.json(path === "/api/v1/verdicts" ? { verdicts: {} }
      : path === "/api/v1/questions" ? { questions: [] } : {});
  }));
  renderHistory();

  fireEvent.click(screen.getByText("Понятная история"));
  expect(await screen.findByText("Этап успешно завершён")).toBeVisible();
});

it("keeps the work screen usable when the history API fails", async () => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input);
    if (path.startsWith("/api/v1/work-history?")) throw new Error("API unavailable");
    return Response.json(path === "/api/v1/verdicts" ? { verdicts: {} }
      : path === "/api/v1/questions" ? { questions: [] } : {});
  }));
  renderHistory();

  fireEvent.click(screen.getByText("Понятная история"));
  expect(await screen.findByText("отработала")).toBeVisible();
  expect(screen.queryByText("Этап успешно завершён")).not.toBeInTheDocument();
});

it("loads and combines history for more than 100 tasks in batches", async () => {
  const tasks = Array.from({ length: 101 }, (_, index): Task => ({
    ...task,
    id: `task-${index + 1}`,
    title: `[auto] [3/5 Implement + Test] Работа ${index + 1}`,
  }));
  const historyRequests: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input);
    if (path.startsWith("/api/v1/work-history?")) {
      historyRequests.push(path);
      const ids = new URL(path, "http://localhost").searchParams.getAll("task_id");
      return Response.json({ history: ids.map((id) => ({ task_id: id, text: `История ${id}` })) });
    }
    return Response.json(path === "/api/v1/verdicts" ? { verdicts: {} }
      : path === "/api/v1/questions" ? { questions: [] } : {});
  }));

  renderHistory(tasks);

  fireEvent.click(screen.getByText("Работа 101"));
  expect(await screen.findByText("История task-101")).toBeVisible();
  expect(historyRequests).toHaveLength(2);
  expect(historyRequests.map((path) => new URL(path, "http://localhost").searchParams.getAll("task_id").length))
    .toEqual([100, 1]);
}, 10_000);

it("revives only stopped work once and shows API errors", async () => {
  let reviveCalls = 0;
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (path === "/api/v1/work-status") return Response.json({ "Понятная история": { state: "stopped_owner", text: "остановлена" } });
    if (path.includes("/revive")) {
      reviveCalls += 1;
      expect(init?.method).toBe("POST");
      return new Response(JSON.stringify({ error: { code: "failed", message: "Пилот недоступен" } }), { status: 503 });
    }
    if (path.startsWith("/api/v1/work-history?")) return Response.json({ history: [] });
    return Response.json(path === "/api/v1/verdicts" ? { verdicts: {} }
      : path === "/api/v1/questions" ? { questions: [] } : {});
  }));
  renderHistory();

  const button = await screen.findByRole("button", { name: "Оживить" });
  fireEvent.click(button);
  fireEvent.click(button);
  expect(await screen.findByRole("alert")).toHaveTextContent("Пилот недоступен");
  expect(reviveCalls).toBe(1);
  expect(screen.getByRole("button", { name: "Оживить" })).toBeEnabled();
  await waitFor(() => expect(screen.getByText("Понятная история")).toBeVisible());
});

it("does not offer revive for ordinary failed work", async () => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input);
    if (path === "/api/v1/work-status") return Response.json({});
    if (path.startsWith("/api/v1/work-history?")) return Response.json({ history: [] });
    return Response.json(path === "/api/v1/verdicts" ? { verdicts: {} }
      : path === "/api/v1/questions" ? { questions: [] } : {});
  }));
  renderHistory([{ ...task, state: "failed" }]);
  await waitFor(() => expect(screen.getByText("Понятная история")).toBeVisible());
  expect(screen.queryByRole("button", { name: "Оживить" })).not.toBeInTheDocument();
});
