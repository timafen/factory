import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it, vi } from "vitest";
import { cpuLoadExplanation, fetchAllTasks, Overview, overviewWork, productState } from "./Overview";

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

describe("Overview Factory efficiency", () => {
  it("marks a small sample, shows exact denominators, and compares both periods", async () => {
    const share = (key: string, seconds: number, ratio: number, sample = 1) => ({
      key, seconds, sample, denominator_seconds: 7200, share: ratio,
      definition: `Определение ${key}`,
    });
    const period = (overrides: Record<string, unknown> = {}) => ({
      started_at: "2026-08-09T12:00:00Z", ended_at: "2026-08-10T12:00:00Z",
      completed_works: 2, product_stage_tasks: 14,
      lead_time_seconds: { sample: 2, median: 3600, p90: 7200 },
      time_shares: [
        share("queue", 720, 0.1, 2), share("Triage", 720, 0.1),
        share("Specification", 720, 0.1), share("Implement + Test", 720, 0.1),
        share("Review", 720, 0.1), share("Verify", 720, 0.1),
        share("stage_handoff_wait", 360, 0.05, 2), share("owner_decision_wait", 360, 0.05),
        share("merge_release_wait", 360, 0.05), share("unclassified", 1800, 0.25, 3),
      ],
      unclassified_too_high: true, unclassified_threshold: 0.2,
      review_first_pass: { count: 1, total: 2, rate: 0.5 },
      verify_first_pass: { count: 2, total: 2, rate: 1 },
      rounds: { sample: 2, median: 1.5, p90: 2 },
      final_dead_ends: { count: 1, total: 3, rate: 1 / 3 },
      automatic_recoveries: 1, release_failures: 1, rollbacks: 1,
      excluded: { patrol: 3, scheduled: 2, helper: 1, other: 4, total: 10 },
      ...overrides,
    });
    const efficiency = {
      generated_at: "2026-08-10T12:00:00Z", minimum_sample: 5,
      periods: {
        "24h": { assessment: "low_data", current: period(), previous: period({ completed_works: 1 }) },
        "7d": { assessment: "degraded", current: period({ completed_works: 8 }), previous: period({ completed_works: 10 }) },
      },
    };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      const body = path === "/api/v1/metrics/efficiency" ? efficiency
        : path.startsWith("/api/v1/tasks") ? { tasks: [], next_cursor: null }
        : path.endsWith("/works") ? {} : {};
      return { ok: true, json: async () => body } as Response;
    }));

    render(createElement(Overview, {}));
    const section = await screen.findByRole("region", { name: "Эффективность Factory" });
    expect(within(section).getByText("данных мало")).toBeVisible();
    expect(within(section).getByText("выборка: 2 влитых работ · минимум для оценки 5")).toBeVisible();
    expect(within(section).getByRole("alert")).toHaveTextContent("unclassified 25% превышает порог 20%");
    expect(within(section).queryByText("есть улучшение")).not.toBeInTheDocument();
    fireEvent.click(within(section).getByText("Показать детали и знаменатели"));
    expect(within(section).getByText("1 из 2 (50%)")).toBeVisible();
    expect(within(section).getByText("Ожидание решения владельца")).toBeVisible();
    expect(within(section).getByText("Определение owner_decision_wait")).toBeVisible();
    expect(within(section).getAllByText("360 сек · 5%")).toHaveLength(3);
    expect(within(section).getByText(/n=3 интервалов/)).toBeVisible();
    expect(within(section).getByText(/Служебные отдельно: патруль 3, по расписанию 2, helper 1, прочие 4/)).toBeVisible();

    fireEvent.click(within(section).getByRole("button", { name: "7 дней" }));
    expect(within(section).getByText("есть деградация")).toBeVisible();
    expect(within(section).getByText("выборка: 8 влитых работ · минимум для оценки 5")).toBeVisible();
    expect(within(section).getByText("предыдущий период: 10")).toBeVisible();
  });
});

describe("Overview product capacity", () => {
  it("shows the four-stream history honestly and keeps unknown explicit", async () => {
    const period = { started_at: "2026-08-09T12:00:00Z", ended_at: "2026-08-10T12:00:00Z", observation_from: "2026-08-10T11:00:00Z", samples: 2, low_data: true,
      active_time: [0, 1, 2, 3, 4].map((active) => ({ active, seconds: active === 0 ? 3600 : 0, share: active === 0 ? 1 : 0 })), average_busy: 0, queue_p90: 2,
      underload: ["no_ready_work", "owner_question", "provider_limit", "repository_conflict", "release_lock", "unknown"].map((reason) => ({ reason, seconds: reason === "unknown" ? 3600 : 0, share: reason === "unknown" ? 1 : 0 })),
    };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      const body = path === "/api/v1/metrics/product-capacity" ? { generated_at: "2026-08-10T12:00:00Z", capacity: 4, periods: { "24h": period, "7d": period } }
        : path.startsWith("/api/v1/tasks") ? { tasks: [], next_cursor: null } : {};
      return { ok: true, json: async () => body } as Response;
    }));
    render(createElement(Overview, {}));
    const section = await screen.findByRole("region", { name: "Загрузка четырёх потоков" });
    expect(within(section).getByText("данных мало")).toBeVisible();
    expect(within(section).getByText("0.0 / 4")).toBeVisible();
    expect(within(section).getByText("p90 очереди")).toBeVisible();
    fireEvent.click(within(section).getByText("Показать причины недозагрузки"));
    expect(within(section).getByText(/unknown:/)).toBeVisible();
    fireEvent.click(within(section).getByRole("button", { name: "7 дней" }));
    expect(within(section).getByText("сэмплов: 2")).toBeVisible();
  });
});

describe("Overview products", () => {
  it("renders projects in snapshot order with honest provider states", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const path=String(input); const body=path==="/api/v1/dashboard"?{projects:[
        {id:"a",name:"shop",remote_identity:"github.com/acme/shop",main_subject:"Продажа без ошибок",provider_status:"configured",environments:[{name:"Стейдж",status:"available",release_label:"Летний выпуск",health:"healthy"}]},
        {id:"b",name:"factory",remote_identity:"github.com/acme/factory",provider_status:"not_configured",environments:[]},
      ]}:path.startsWith("/api/v1/tasks")?{tasks:[],next_cursor:null}:{};
      return {ok:true,json:async()=>body} as Response;
    }));
    render(createElement(Overview,{}));
    const blocks=await screen.findAllByRole("region",{name:/Продукт —/});
    expect(blocks.map((block)=>within(block).getByText(/Продукт —/).textContent)).toEqual(["Продукт — shop","Продукт — factory"]);
    expect(within(blocks[0]).getByText("Продажа без ошибок",{exact:false})).toBeVisible();
    expect(within(blocks[1]).getByText("Стенд не настроен")).toBeVisible();
  });

  it("classifies unavailable release without claiming an outage", () => {
    expect(productState({id:"a",name:"a",remote_identity:"a",provider_status:"configured",environments:[{name:"Прод",status:"unavailable"}]})).toBe("Сведения о выпуске недоступны");
  });
});

describe("Overview Codex spend", () => {
  it("shows tokens but no invented price for an unknown exact model", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      const body = path === "/api/v1/dashboard"
        ? { spend: { day_usd: 0, week_usd: 0, day_tokens: 1234, week_tokens: 5678,
            day_cost_defined: false, week_cost_defined: false,
            day_base_estimate: true, week_base_estimate: true,
            day_unknown_models: ["gpt-future-exact"],
            week_unknown_models: ["gpt-future-exact"] } }
        : path.startsWith("/api/v1/tasks") ? { tasks: [], next_cursor: null }
        : path.endsWith("/works") ? {} : {};
      return { ok: true, json: async () => body } as Response;
    }));

    render(createElement(Overview, {}));

    expect(await screen.findAllByText("стоимость не определена")).toHaveLength(2);
    expect(screen.getByText("1 234 токенов Codex")).toBeVisible();
    expect(screen.getByText("Нет точного API-тарифа: gpt-future-exact")).toBeVisible();
    expect(screen.getByText(/базовая оценка по API-тарифу/)).toBeVisible();
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
