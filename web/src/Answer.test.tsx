import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { createElement } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { AnswerView } from "./Answer";

afterEach(() => vi.unstubAllGlobals());

it("keeps an answered reservation visible without presenting it as a new question", async () => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    if (String(input) === "/api/v1/questions") {
      return Response.json({ questions: [{
        id: "https", task_id: "task-https", stage: "Specification",
        resume_stage: "Implement + Test",
        title: "Весь HTTPS-набор проходит с реальным service worker",
        status: "answered", answer: "Продолжай полный прогон",
        escalation_reason: "ответ принят, ожидает зарезервированный слот из-за загрузки сервера",
        reservation: { stage: "Implement + Test", answered_at: "2026-08-12T10:00:00Z" },
      }] });
    }
    return Response.json({});
  }));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(createElement(QueryClientProvider, { client }, createElement(AnswerView)));

  const waiting = await screen.findByRole("region", {
    name: "Ответ принят — ожидает зарезервированный слот",
  });
  expect(waiting).toHaveTextContent("Весь HTTPS-набор проходит с реальным service worker");
  expect(waiting).toHaveTextContent("ответ принят, ожидает зарезервированный слот из-за загрузки сервера");
  expect(screen.queryByPlaceholderText("Твой ответ — можно надиктовать кнопкой ниже")).not.toBeInTheDocument();
  expect(screen.queryByText("Вопросов к тебе нет — конвейер едет сам. 👌")).not.toBeInTheDocument();
});
