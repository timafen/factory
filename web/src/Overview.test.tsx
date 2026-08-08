import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Overview } from "./Overview";
import { metrics } from "./test/fixtures";

afterEach(() => vi.restoreAllMocks());

function renderOverview(dashboard: unknown, works: unknown, worksStatus = 200, rejectWorks = false) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const path = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    if (path.startsWith("/api/v1/metrics/summary")) return Response.json(metrics);
    if (path === "/api/v1/dashboard") return Response.json(dashboard);
    if (path === "/api/v1/works") {
      if (rejectWorks) throw new TypeError("network connection lost");
      return Response.json(works, { status: worksStatus });
    }
    return new Response(null, { status: 404 });
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><Overview /></QueryClientProvider>);
}

describe("Overview active work", () => {
  it("shows the clean work title, source type, and structured localized stage", async () => {
    renderOverview({ now: { running: [
      { id: "one", title: "[auto] [3/5 Implement + Test] Экран Обзор" },
      { id: "two", title: "[auto] [4/5 Review] Вторая работа" },
    ] } }, {
      one: { origin: "owner", stage: "Implement + Test" },
      two: { origin: "orchestrator", stage: "Review" },
    });

    const section = await screen.findByRole("region", { name: "Сейчас в работе" });
    expect(within(section).getByText(/Экран Обзор/)).toBeVisible();
    expect(within(section).queryByText(/\[auto\]/)).not.toBeInTheDocument();
    expect(within(section).getByText("поставил владелец")).toBeVisible();
    expect(within(section).getByText("Этап: Разработка и тесты")).toBeVisible();
    expect(within(section).getByText("поставила Фабрика (управляющий)")).toBeVisible();
    expect(within(section).getByText("Этап: Ревью")).toBeVisible();
  });

  it("keeps origin metadata separate for works with identical titles", async () => {
    renderOverview({ now: { running: [
      { id: "owner-work", title: "Одинаковая работа" },
      { id: "automated-work", title: "Одинаковая работа" },
    ] } }, {
      "owner-work": { origin: "owner" },
      "automated-work": { origin: "orchestrator" },
    });

    const section = await screen.findByRole("region", { name: "Сейчас в работе" });
    expect(within(section).getByText("поставил владелец")).toBeVisible();
    expect(within(section).getByText("поставила Фабрика (управляющий)")).toBeVisible();
  });

  it("does not invent a person or stage when metadata is absent", async () => {
    renderOverview({ now: { running: [{ id: "one", title: "[auto] [4/5 Review] Обычная работа" }] } }, {});

    const section = await screen.findByRole("region", { name: "Сейчас в работе" });
    expect(await within(section).findByText("постановщик не указан")).toBeVisible();
    expect(within(section).getByText("Этап: не указан")).toBeVisible();
  });

  it("keeps active work visible when source metadata cannot be loaded", async () => {
    renderOverview(
      { now: { running: [{ id: "one", title: "[auto] [2/5 Specification] Надёжная работа" }] } },
      { error: { code: "unavailable", message: "unavailable" } },
      503,
    );

    const section = await screen.findByRole("region", { name: "Сейчас в работе" });
    expect(await within(section).findByText(/Надёжная работа/)).toBeVisible();
    expect(within(section).getByText(/могут быть неполными/)).toBeVisible();
  });

  it("keeps dashboard data visible when the metadata request is rejected", async () => {
    renderOverview(
      { now: { running: [{ id: "one", title: "[auto] [2/5 Specification] Работа при обрыве сети" }] } },
      {},
      200,
      true,
    );

    const section = await screen.findByRole("region", { name: "Сейчас в работе" });
    expect(await within(section).findByText(/Работа при обрыве сети/)).toBeVisible();
    expect(within(section).getByText(/могут быть неполными/)).toBeVisible();
  });

  it("shows an explicit empty state", async () => {
    renderOverview({ now: { running: [] } }, {});
    expect(await screen.findByText("Сейчас активной работы нет.")).toBeVisible();
  });
});
