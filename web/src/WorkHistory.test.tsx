import { fireEvent, render, screen } from "@testing-library/react";
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

function renderHistory() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}>
    <WorkView tasks={[task]} workers={[]} pending={false} error={null}
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
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
