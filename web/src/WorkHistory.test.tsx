import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
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

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

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

it("revives stuck work through its encoded name and removes the action after success", async () => {
  const stuck = { ...task, title: "[auto] [3/5 Implement + Test] Работа / с пробелом" };
  let requestedPath = "";
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (path === "/api/v1/work-status") {
      return Response.json({ "Работа / с пробелом": { state: "stuck", text: "застряла" } });
    }
    if (path.includes("/revive")) {
      requestedPath = path;
      expect(init?.method).toBe("POST");
      return Response.json({ work: "Работа / с пробелом", state: "reviving" });
    }
    if (path.startsWith("/api/v1/work-history?")) return Response.json({ history: [] });
    return Response.json(path === "/api/v1/verdicts" ? { verdicts: {} }
      : path === "/api/v1/questions" ? { questions: [] } : {});
  }));
  renderHistory([stuck]);

  fireEvent.click(await screen.findByRole("button", { name: "Оживить" }));

  await waitFor(() => expect(screen.queryByRole("button", { name: "Оживить" })).not.toBeInTheDocument());
  expect(requestedPath).toBe(`/api/v1/works/${encodeURIComponent("Работа / с пробелом")}/revive`);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it.each(["stopped_owner", "stuck"])(
  "keeps a revived work reviving through stale %s polling",
  async (staleState) => {
    let poll: (() => void) | undefined;
    const pollInterval = ((handler: TimerHandler, delay?: number) => {
      if (delay === 20_000) poll = handler as () => void;
      return 1 as unknown as ReturnType<typeof window.setInterval>;
    }) as unknown as typeof window.setInterval;
    const setInterval = vi.spyOn(window, "setInterval").mockImplementation(pollInterval);
    let statusRequests = 0;
    let resolveStalePoll: ((response: Response) => void) | undefined;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path === "/api/v1/work-status") {
        statusRequests += 1;
        if (statusRequests === 3) {
          return new Promise<Response>((resolve) => { resolveStalePoll = resolve; });
        }
        return Response.json({ "Понятная история": { state: staleState, text: "старый статус" } });
      }
      if (path.includes("/revive")) {
        return Response.json({ work: "Понятная история", state: "reviving" });
      }
      if (path.startsWith("/api/v1/work-history?")) return Response.json({ history: [] });
      return Response.json(path === "/api/v1/verdicts" ? { verdicts: {} }
        : path === "/api/v1/questions" ? { questions: [] } : {});
    }));
    renderHistory();

    fireEvent.click(await screen.findByRole("button", { name: "Оживить" }));
    expect(await screen.findByText("оживает: пилот продолжит со следующего этапа")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Оживить" })).not.toBeInTheDocument();
    await waitFor(() => expect(statusRequests).toBe(2));

    expect(setInterval).toHaveBeenCalledWith(expect.any(Function), 20_000);
    await act(async () => poll!());
    await waitFor(() => expect(statusRequests).toBe(3));
    await act(async () => resolveStalePoll!(Response.json({
      "Понятная история": { state: staleState, text: "старый статус" },
    })));

    expect(screen.getByText("оживает: пилот продолжит со следующего этапа")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Оживить" })).not.toBeInTheDocument();
  },
);

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

it("does not offer revive for closed or archived work with a stale stopped status", async () => {
  const archived = {
    ...task,
    id: "archived-task",
    title: "[auto] [3/5 Implement + Test] Старая остановленная работа",
    created_at: "2020-01-01T00:00:00Z",
  };
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input);
    if (path === "/api/v1/work-status") return Response.json({
      "Понятная история": { state: "stopped_owner", text: "остановлена" },
      "Старая остановленная работа": { state: "stopped_owner", text: "остановлена" },
    });
    if (path === "/api/v1/works") return Response.json({
      "Понятная история": { closed: "2026-08-09" },
    });
    if (path.startsWith("/api/v1/work-history?")) return Response.json({ history: [] });
    return Response.json(path === "/api/v1/verdicts" ? { verdicts: {} }
      : path === "/api/v1/questions" ? { questions: [] } : {});
  }));
  renderHistory([task, archived]);

  await waitFor(() => expect(screen.getByText("Понятная история")).toBeVisible());
  expect(screen.queryByRole("button", { name: "Оживить" })).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: /Архив/ }));
  expect(screen.getByText("Старая остановленная работа")).toBeVisible();
  expect(screen.queryByRole("button", { name: "Оживить" })).not.toBeInTheDocument();
});

it("sends the complete 200-character work name when reviving", async () => {
  const work = "я".repeat(200);
  const longTask = { ...task, title: `[auto] [3/5 Implement + Test] ${work}` };
  let requestedPath = "";
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input);
    if (path === "/api/v1/work-status") return Response.json({ [work]: { state: "stuck", text: "застряла" } });
    if (path.includes("/revive")) {
      requestedPath = path;
      return Response.json({ work, state: "reviving" });
    }
    if (path.startsWith("/api/v1/work-history?")) return Response.json({ history: [] });
    return Response.json(path === "/api/v1/verdicts" ? { verdicts: {} }
      : path === "/api/v1/questions" ? { questions: [] } : {});
  }));
  renderHistory([longTask]);

  fireEvent.click(await screen.findByRole("button", { name: "Оживить" }));

  await waitFor(() => expect(requestedPath).toBe(`/api/v1/works/${encodeURIComponent(work)}/revive`));
  expect(screen.getByText(work)).toBeVisible();
});
