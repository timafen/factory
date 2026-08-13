import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SolutionsView } from "./Solutions";

const questions = [
  { id: "open-1", task_id: "task-1", stage: "Specification", resume_stage: "Implement", title: "Новая доставка", status: "open", asked_at: "2026-08-10T08:00:00Z", situation: "Покупатели ждут доставку в выходные.", question: "Добавить доставку в выходные?" },
  { id: "answered-1", task_id: "task-2", stage: "Implement", resume_stage: "Review", title: "Выбор оплаты", status: "answered", asked_at: "2026-08-10T09:00:00Z", question: "Оставить оплату картой?", answer: "Да, оставить.", answered_by: "owner", answered_at: "2026-08-10T09:15:00Z" },
  { id: "resolved-1", task_id: "task-3", stage: "Review", resume_stage: "Verify", title: "Проверка возвратов", status: "resolved", asked_at: "2026-08-10T10:00:00Z", situation: "Нужна политика возвратов.", question: "Публиковать правила возврата?" },
  { id: "stale-1", task_id: "task-4", stage: "Triage", resume_stage: "Specification", title: "Старый вопрос", status: "stale", asked_at: "2026-08-10T11:00:00Z", question: "Этот вопрос больше актуален?" },
  { id: "unknown-1", task_id: "task-5", stage: "Verify", resume_stage: "Done", title: "Новый статус", status: "deferred", asked_at: "2026-08-10T12:00:00Z", question: "Показать неизвестный статус?" },
];

function renderSolutions() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><SolutionsView /></QueryClientProvider>);
}

describe("SolutionsView", () => {
  it("shows every question status as read-only history without mutation requests", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json({ questions }));
    renderSolutions();

    for (const question of questions) {
      expect(await screen.findByRole("article", { name: `Решение: ${question.title}` })).toHaveTextContent(question.question);
    }
    expect(screen.getByText("Статус: Открыт")).toBeVisible();
    expect(screen.getByText("Статус: Отвечен")).toBeVisible();
    expect(screen.getByText("Статус: Решён")).toBeVisible();
    expect(screen.getByText("Статус: Устарел")).toBeVisible();
    expect(screen.getByText("Статус: deferred")).toBeVisible();
    expect(screen.getByText(/Покупатели ждут доставку в выходные/)).toBeVisible();
    expect(screen.getByText(/Да, оставить/)).toBeVisible();
    expect(screen.getByText(/Ответил: owner/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Делаем" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Не делаем" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Отправить и продолжить/ })).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith("/api/v1/questions");
    expect(fetch.mock.calls.every(([, init]) => !init || !["POST", "DELETE"].includes(String(init.method)))).toBe(true);
  });
});
