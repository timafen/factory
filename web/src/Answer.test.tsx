import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AnswerView } from "./Answer";

function renderAnswer() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><AnswerView /></QueryClientProvider>);
}

describe("AnswerView", () => {
  it("shows the owner question on one line and sends the selected decision", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (input === "/api/v1/questions" && !init) {
        return Response.json({ questions: [{ id: "decision-1", task_id: "task-1", stage: "Specification", title: "Новая доставка", status: "open", question: "Делаем новую доставку для всех заказов?" }] });
      }
      return Response.json({ ok: true, status: "answered" });
    });

    renderAnswer();

    const question = await screen.findByTitle("Делаем новую доставку для всех заказов?");
    expect(question).toHaveStyle({ whiteSpace: "nowrap", textOverflow: "ellipsis" });
    fireEvent.click(screen.getByRole("button", { name: "Делаем" }));

    expect(fetch).toHaveBeenCalledWith("/api/v1/questions/decision-1/answer", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ answer: "Делаем" }),
    }));
    expect(screen.getByRole("button", { name: "Не делаем" })).toBeVisible();
  });
});
