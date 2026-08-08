import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Overview } from "./Overview";
import { metrics } from "./test/fixtures";

function renderOverview(dashboard: unknown, works: unknown, worksStatus = 200) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const path = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    if (path.startsWith("/api/v1/metrics/summary")) return Response.json(metrics);
    if (path === "/api/v1/dashboard") return Response.json(dashboard);
    if (path === "/api/v1/works") return Response.json(works, { status: worksStatus });
    return new Response(null, { status: 404 });
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><Overview /></QueryClientProvider>);
}

describe("Overview active work", () => {
  it("shows the clean work title, source type, and localized pipeline stage", async () => {
    renderOverview({ now: { running: [
      { id: "one", title: "[auto] [3/5 Implement + Test] Экран Обзор" },
      { id: "two", title: "[auto] [4/5 Review] Вторая работа" },
    ] } }, {
      "Экран Обзор": { origin: "owner" },
      "Вторая работа": { origin: "orchestrator" },
    });

    const section = await screen.findByRole("region", { name: "Сейчас в работе" });
    expect(within(section).getByText("Экран Обзор")).toBeVisible();
    expect(within(section).queryByText(/\[auto\]/)).not.toBeInTheDocument();
    expect(within(section).getByText("Поставил: владелец")).toBeVisible();
    expect(within(section).getByText("Этап: 3/5 · Разработка и тесты")).toBeVisible();
    expect(within(section).getByText("Поставил: оркестратор")).toBeVisible();
    expect(within(section).getByText("Этап: 4/5 · Ревью")).toBeVisible();
  });

  it("does not invent a person or stage when metadata is absent", async () => {
    renderOverview({ now: { running: [{ id: "one", title: "Обычная работа" }] } }, {});

    const section = await screen.findByRole("region", { name: "Сейчас в работе" });
    expect(within(section).getByText("Поставил: не указано")).toBeVisible();
    expect(within(section).getByText("Этап: не указан")).toBeVisible();
  });

  it("keeps active work visible when source metadata cannot be loaded", async () => {
    renderOverview(
      { now: { running: [{ id: "one", title: "[auto] [2/5 Specification] Надёжная работа" }] } },
      { error: { code: "unavailable", message: "unavailable" } },
      503,
    );

    const section = await screen.findByRole("region", { name: "Сейчас в работе" });
    expect(within(section).getByText("Надёжная работа")).toBeVisible();
    expect(within(section).getByText(/могут быть неполными/)).toBeVisible();
  });

  it("shows an explicit empty state", async () => {
    renderOverview({ now: { running: [] } }, {});
    expect(await screen.findByText("Сейчас активной работы нет.")).toBeVisible();
  });
});
