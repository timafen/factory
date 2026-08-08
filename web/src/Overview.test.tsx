import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Overview } from "./Overview";

afterEach(() => vi.restoreAllMocks());

function renderOverview(dashboard: unknown, works: unknown, worksStatus = 200, rejectWorks = false, malformedWorks = false) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const path = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    if (path === "/api/v1/dashboard") return Response.json(dashboard);
    if (path === "/api/v1/works") {
      if (rejectWorks) throw new TypeError("network connection lost");
      if (malformedWorks) return new Response("not json", { status: 200 });
      return Response.json(works, { status: worksStatus });
    }
    return new Response(null, { status: 404 });
  });
  return render(<Overview />);
}

describe("Overview active work", () => {
  it("shows an accurate headline, count, title, source, and localized stage", async () => {
    renderOverview({ now: { queued_count: 0, running: [
      { id: "one", title: "[auto] [3/5 Implement + Test] Экран Обзор" },
      { id: "two", title: "[auto] [4/5 Review] Проверить Обзор" },
    ] } }, {
      one: { origin: "owner", stage: "Implement + Test" },
      two: { origin: "orchestrator", stage: "Review" },
    });

    const section = await screen.findByRole("region", { name: "Сейчас в работе" });
    expect(screen.getByText("Всё идёт")).toBeVisible();
    expect(screen.getByText("в работе 2 · в очереди 0")).toBeVisible();
    expect(within(section).getByText(/Экран Обзор/)).toBeVisible();
    expect(within(section).queryByText(/\[auto\]/)).not.toBeInTheDocument();
    expect(within(section).getByText("поставил владелец")).toBeVisible();
    expect(within(section).getByText("Этап: Разработка и тесты")).toBeVisible();
    expect(within(section).getByText("поставила Фабрика (управляющий)")).toBeVisible();
    expect(within(section).getByText("Этап: Ревью")).toBeVisible();
  });

  it("does not invent metadata when it is absent", async () => {
    renderOverview({ now: { running: [{ id: "one", title: "Обычная работа" }] } }, {});
    const section = await screen.findByRole("region", { name: "Сейчас в работе" });
    expect(await within(section).findByText("постановщик не указан")).toBeVisible();
    expect(within(section).getByText("Этап: не указан")).toBeVisible();
  });

  it("keeps active work visible when metadata cannot be loaded", async () => {
    renderOverview({ now: { running: [{ id: "one", title: "Работа при обрыве сети" }] } }, {}, 200, true);
    const section = await screen.findByRole("region", { name: "Сейчас в работе" });
    expect(await within(section).findByText(/Работа при обрыве сети/)).toBeVisible();
    expect(within(section).getByText(/могут быть неполными/)).toBeVisible();
  });

  it("warns about incomplete metadata when works returns malformed JSON", async () => {
    renderOverview({ now: { running: [{ id: "one", title: "Работа при ошибке JSON" }] } }, {}, 200, false, true);
    const section = await screen.findByRole("region", { name: "Сейчас в работе" });
    expect(await within(section).findByText(/Работа при ошибке JSON/)).toBeVisible();
    expect(within(section).getByText(/могут быть неполными/)).toBeVisible();
  });

  it("shows an explicit empty state", async () => {
    renderOverview({ now: { running: [] } }, {});
    expect(await screen.findByText("Сейчас активной работы нет.")).toBeVisible();
  });
});
