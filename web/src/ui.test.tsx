import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { ErrorState, StaleBanner, StatusBadge, ViewHeader } from "./ui";

it("shows shared refresh, error, retry, and task-state copy in Russian", () => {
  const refresh = vi.fn();
  const { rerender } = render(
    <>
      <ViewHeader title="Работы" fetching={false} updatedAt={Date.now()} onRefresh={refresh} />
      <StatusBadge state="queued" />
    </>,
  );

  expect(screen.getByText("Обновлено только что")).toBeVisible();
  expect(screen.getByRole("button", { name: "Обновить" })).toBeVisible();
  expect(screen.getByText("В очереди")).toBeVisible();

  rerender(<ErrorState error={new Error("Нет соединения")} onRetry={refresh} />);
  expect(screen.getByRole("heading", { name: "Не удалось загрузить страницу" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Повторить" })).toBeVisible();

  rerender(<StaleBanner error={new Error("Нет соединения")} />);
  expect(screen.getByRole("status")).toHaveTextContent(
    "Показаны последние доступные данные. Обновление не удалось: Нет соединения",
  );
});
