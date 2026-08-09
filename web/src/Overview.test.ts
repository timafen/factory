import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it, vi } from "vitest";
import { cpuLoadExplanation, fetchAllTasks, Overview, overviewWork } from "./Overview";

describe("cpuLoadExplanation", () => {
  it("uses actual running work and slot values", () => {
    expect(cpuLoadExplanation(3, { busy: 2, capacity: 4 }))
      .toBe("Причина загрузки процессора: активно работ 3; занято мест 2 из 4.");
  });

  it("does not invent occupied slots when the API omits them", () => {
    expect(cpuLoadExplanation(1))
      .toBe("Причина загрузки процессора: активно работ 1. Данных о занятых местах нет.");
  });

  it("reports zero running work without hiding slot data", () => {
    expect(cpuLoadExplanation(0, { busy: 0, capacity: 4 }))
      .toBe("Причина загрузки процессора: активно работ 0; занято мест 0 из 4.");
  });
});

describe("overviewWork", () => {
  it("shows the work, submitter, and current pipeline stage from server data", () => {
    expect(overviewWork([
      { id: "running", title: "[auto] [3/5 Implement + Test] Экран обзора", state: "running" },
      { id: "done", title: "Завершено", state: "succeeded" },
    ], { "Экран обзора": { origin: "owner" } })).toEqual([{
      id: "running", title: "Экран обзора", stage: "Implement + Test",
      origin: "поставил ты", state: "running",
    }]);
  });

  it("keeps active work honest when stage and submitter metadata are absent", () => {
    expect(overviewWork([
      { id: "queued", title: "Обычная задача", state: "queued" },
    ], {})).toEqual([{
      id: "queued", title: "Обычная задача", stage: "Без этапа",
      origin: "кто поставил — не указано", state: "queued",
    }]);
  });
});

describe("Overview active work", () => {
  it("loads active work from the server and opens the work screen", async () => {
    const onNav = vi.fn();
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      const body = path.startsWith("/api/v1/tasks")
        ? { tasks: [{ id: "task-1", title: "[auto] [4/5 Review] Новый обзор", state: "running" }], next_cursor: null }
        : path.endsWith("/works") ? { "Новый обзор": { origin: "assistant" } } : {};
      return { ok: true, json: async () => body } as Response;
    }));

    render(createElement(Overview, { onNav }));
    const section = await screen.findByRole("region", { name: "Сейчас в работе" });
    expect(within(section).getByText("Новый обзор")).toBeVisible();
    expect(within(section).getByText("поставил Клод")).toBeVisible();
    expect(within(section).getByText("этап: Review")).toBeVisible();
    fireEvent.click(within(section).getByText("Новый обзор"));
    expect(onNav).toHaveBeenCalledWith("work");
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/v1/tasks?limit=200"));
  });
});

describe("fetchAllTasks", () => {
  it("walks every page instead of stopping at the server's default limit", async () => {
    const pageSize = 200;
    const totalTasks = 260; // more than one default (50) and one max (200) page
    const allTasks = Array.from({ length: totalTasks }, (_, i) => ({
      id: `task-${i}`,
      title: `Задача ${i}`,
      state: i === totalTasks - 1 ? "running" : "succeeded",
    }));

    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://localhost");
      const cursor = url.searchParams.get("cursor");
      const start = cursor ? Number(cursor) : 0;
      const page = allTasks.slice(start, start + pageSize);
      const nextStart = start + pageSize;
      const nextCursor = nextStart < allTasks.length ? String(nextStart) : null;
      return { ok: true, json: async () => ({ tasks: page, next_cursor: nextCursor }) } as Response;
    }));

    const tasks = await fetchAllTasks();

    expect(tasks).toHaveLength(totalTasks);
    expect(tasks[totalTasks - 1]).toMatchObject({ state: "running" });
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("stops once the server reports no further page", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      json: async () => ({ tasks: [{ id: "only", title: "Единственная", state: "queued" }], next_cursor: null }),
    } as Response)));

    const tasks = await fetchAllTasks();

    expect(tasks).toEqual([{ id: "only", title: "Единственная", state: "queued" }]);
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
