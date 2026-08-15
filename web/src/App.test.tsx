import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { mockControlPlane as mockFixtureControlPlane } from "./test/fixtures";

function mockControlPlane(options?: Parameters<typeof mockFixtureControlPlane>[0]) {
  const fetch = mockFixtureControlPlane(options);
  const fixtureImplementation = fetch.getMockImplementation();
  fetch.mockImplementation((input, init) => {
    const path = typeof input === "string"
      ? input
      : input instanceof URL
        ? input.toString()
        : input.url;
    const fixturePath = path
      .replace("/api/v1/tasks?limit=200", "/api/v1/tasks?limit=50")
      .replace(/(\/api\/v1\/automations\/[^/]+\/occurrences\?)limit=200/, "$1limit=50");
    return fixtureImplementation!(fixturePath, init);
  });
  return fetch;
}

function renderApp() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return {
    ...render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
    ),
    client,
  };
}

function workflowRequestPaths(fetch: ReturnType<typeof mockControlPlane>) {
  return fetch.mock.calls
    .map(([input]) => typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url)
    .filter((path) => path.startsWith("/api/v1/workflows?limit=200"));
}

describe("App", () => {
  beforeEach(() => {
    window.history.replaceState({}, "", "/work");
  });

  it("renders the renamed main screen on the default route", async () => {
    window.history.replaceState({}, "", "/");
    const fetch = mockControlPlane();
    renderApp();

    expect(await screen.findByRole("heading", { name: "Обзор" })).toBeVisible();
    expect(screen.getByRole("button", { name: /^Обзор$/ })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(fetch).toHaveBeenCalledWith("/api/v1/dashboard");
  });

  it("opens sandbox keys directly and marks its navigation item", () => {
    window.history.replaceState({}, "", "/sandbox-keys");
    mockControlPlane();
    renderApp();

    expect(screen.getByRole("heading", { name: "Ключи песочницы" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Ключи песочницы" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: "Получить ключи продавца" })).toBeVisible();
  });

  it("marks only exact navigation destinations as the current page", async () => {
    mockControlPlane();
    const user = userEvent.setup();
    renderApp();

    const work = await screen.findByRole("button", { name: /^Работа$/ });
    const workers = screen.getByRole("button", { name: /^Исполнители$/ });
    expect(screen.getByRole("button", { name: /^Обзор$/ })).not.toHaveAttribute("aria-current");
    expect(work).toHaveAttribute("aria-current", "page");
    expect(workers).not.toHaveAttribute("aria-current");

    await user.click(workers);

    expect(work).not.toHaveAttribute("aria-current");
    expect(workers).toHaveAttribute("aria-current", "page");
  });

  it("highlights the work section without marking task detail as current", async () => {
    window.history.replaceState({}, "", "/tasks/task-running");
    mockControlPlane();
    renderApp();

    await screen.findByRole("heading", { name: "running task" });
    const work = screen.getByRole("button", { name: /^Работа$/ });
    expect(work).toHaveClass("active");
    expect(work).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("button", { name: /^Исполнители$/ })).not.toHaveAttribute("aria-current");
  });

  it("highlights the workers section without marking worker detail as current", async () => {
    window.history.replaceState({}, "", "/workers/worker-online");
    mockControlPlane();
    renderApp();

    await screen.findByRole("heading", { name: "Build Mac" });
    const workers = screen.getByRole("button", { name: /^Исполнители$/ });
    expect(workers).toHaveClass("active");
    expect(workers).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("button", { name: /^Работа$/ })).not.toHaveAttribute("aria-current");
  });

  it("lists managed repositories and shows current acquisition readiness", async () => {
    window.history.replaceState({}, "", "/repositories/repo-factory");
    mockControlPlane();
    renderApp();

    expect(await screen.findByRole("heading", { name: "github.com/example/factory" })).toBeVisible();
    expect(screen.getByText("1 исполнителей готовы получать задачи")).toBeVisible();
    const workerRow = screen.getByText("Build Mac").closest(".repository-worker-row");
    expect(workerRow).not.toBeNull();
    expect(within(workerRow as HTMLElement).getByText("В кэше")).toBeVisible();
    expect(within(workerRow as HTMLElement).getByText("Объявлен")).toBeVisible();
    expect(within(workerRow as HTMLElement).getByText("Готов")).toBeVisible();
    const navigation = screen.getByRole("button", { name: /^Репозитории$/ });
    expect(navigation).toHaveClass("active");
    expect(navigation).not.toHaveAttribute("aria-current");
  });

  it("adds, disables, and enables a managed repository", async () => {
    window.history.replaceState({}, "", "/repositories");
    mockControlPlane();
    const user = userEvent.setup();
    renderApp();

    expect(await screen.findByText("github.com/example/disabled")).toBeVisible();
    await user.type(screen.getByLabelText("Канонический адрес"), "github.com/example/new-repository");
    await user.click(screen.getByRole("button", { name: "Добавить репозиторий" }));

    expect(await screen.findByRole("heading", { name: "github.com/example/new-repository" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Отключить репозиторий" }));
    expect(screen.getByText(/Отключение запретит новые назначения/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Отключить маршрутизацию" }));
    expect(await screen.findByText("Маршрутизация отключена")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Включить репозиторий" }));
    expect(await screen.findByRole("button", { name: "Отключить репозиторий" })).toBeVisible();
  });

  it("shows actionable repository validation errors", async () => {
    window.history.replaceState({}, "", "/repositories");
    mockControlPlane();
    const user = userEvent.setup();
    renderApp();

    const input = await screen.findByLabelText("Канонический адрес");
    await user.type(input, "example.com/not-github");
    await user.click(screen.getByRole("button", { name: "Добавить репозиторий" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "remote_identity must use the canonical github.com/owner/repository form (invalid_repository)",
    );
    expect(input).toHaveAttribute("aria-invalid", "true");
  });

  it("identifies duplicate repositories and opens the existing entry", async () => {
    window.history.replaceState({}, "", "/repositories");
    mockControlPlane();
    const user = userEvent.setup();
    renderApp();

    const input = await screen.findByLabelText("Канонический адрес");
    await user.type(input, "github.com/example/factory");
    await user.click(screen.getByRole("button", { name: "Добавить репозиторий" }));

    expect(await screen.findByRole("status")).toHaveTextContent("уже подключён");
    expect(screen.queryByRole("heading", { name: "github.com/example/factory" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Открыть репозиторий" }));
    expect(await screen.findByRole("heading", { name: "github.com/example/factory" })).toBeVisible();
  });

  it("shows repository limit and failed mutation errors", async () => {
    window.history.replaceState({}, "", "/repositories");
    mockControlPlane({ repositoryToggleFailure: true });
    const user = userEvent.setup();
    renderApp();

    const input = await screen.findByLabelText("Канонический адрес");
    await user.type(input, "github.com/example/over-limit");
    await user.click(screen.getByRole("button", { name: "Добавить репозиторий" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "the managed repository limit has been reached (repository_limit_reached)",
    );

    await user.click(screen.getByText("github.com/example/disabled"));
    await user.click(await screen.findByRole("button", { name: "Включить репозиторий" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "repository update could not be saved (storage_unavailable)",
    );
  });

  it("shows server readiness even when the worker list fails", async () => {
    window.history.replaceState({}, "", "/repositories/repo-factory");
    mockControlPlane({ workerFailure: true });
    renderApp();

    expect(await screen.findByRole("heading", { name: "github.com/example/factory" })).toBeVisible();
    expect(screen.getByText("1 исполнителей готовы получать задачи")).toBeVisible();
    expect(screen.getByText("Готовность исполнителей")).toBeVisible();
  });

  it("preserves repository form focus and input during background polling", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      window.history.replaceState({}, "", "/repositories");
      mockControlPlane();
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      renderApp();

      const input = await screen.findByLabelText("Канонический адрес");
      await user.type(input, "github.com/example/in-progress");
      expect(input).toHaveFocus();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(10_000);
      });

      expect(input).toHaveValue("github.com/example/in-progress");
      expect(input).toHaveFocus();
    } finally {
      vi.useRealTimers();
    }
  });

  it("creates, revises, and disables a Workflow through its bounded views", async () => {
    const fetch = mockControlPlane();
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("button", { name: /^Сценарии$/ }));
    expect(await screen.findByRole("heading", { name: "Сценарии" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Создать сценарий" }));
    const createDialog = screen.getByRole("dialog", { name: "Создать сценарий" });
    const workflowTitle = within(createDialog).getByLabelText("Название");
    expect(workflowTitle).toHaveAttribute("name", "title");
    expect(workflowTitle).toHaveAttribute("autocomplete", "off");
    expect(createDialog.querySelector('[name="name"]')).not.toBeInTheDocument();
    await user.type(workflowTitle, "Security review");
    await user.type(within(createDialog).getByLabelText("Описание"), "Review trust boundaries.");
    await user.type(within(createDialog).getByLabelText("Инструкции Markdown"), "Inspect inputs and permissions.");
    await user.click(within(createDialog).getByRole("button", { name: "Создать сценарий" }));

    expect(await screen.findByRole("heading", { name: "Security review" })).toBeVisible();
    expect(screen.getByText("Inspect inputs and permissions.", { selector: ".long-copy" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Новая версия" }));
    const revisionDialog = screen.getByRole("dialog", { name: "Создать версию" });
    const instructions = within(revisionDialog).getByLabelText("Инструкции Markdown");
    await user.clear(instructions);
    await user.type(instructions, "Inspect inputs, permissions, and recovery.");
    await user.click(within(revisionDialog).getByRole("button", { name: "Создать версию" }));
    expect(await screen.findByText("Версия 2", { selector: ".panel-heading span" })).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Выключить" }));
    await user.click(screen.getByRole("button", { name: "Подтвердить выключение" }));
    expect(await screen.findByRole("button", { name: "Включить" })).toBeVisible();
    expect(fetch.mock.calls.some(([input, init]) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      return path.endsWith("/enabled") && init?.method === "PUT";
    })).toBe(true);
  });

  it("keeps runbook editor focus during background polling", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      window.history.replaceState({}, "", "/workflows");
      mockControlPlane();
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      renderApp();

      await user.click(await screen.findByRole("button", { name: "Создать сценарий" }));
      const dialog = screen.getByRole("dialog", { name: "Создать сценарий" });
      const instructions = within(dialog).getByLabelText("Инструкции Markdown");
      await user.type(instructions, "Keep this cursor here.");
      expect(instructions).toHaveFocus();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(10_000);
      });

      expect(instructions).toHaveValue("Keep this cursor here.");
      expect(instructions).toHaveFocus();
    } finally {
      vi.useRealTimers();
    }
  });

  it("creates, tests, enables, runs, and disables a typed GitHub issue Automation", async () => {
    window.history.replaceState({}, "", "/automations");
    const fetch = mockControlPlane();
    const user = userEvent.setup();
    renderApp();

    expect(await screen.findByRole("heading", { name: "Автоматизации" })).toBeVisible();
    const existingRow = screen.getByRole("button", { name: /Ready issues/ });
    expect(existingRow).toHaveTextContent("Автоматизация выключена.");
    expect(existingRow).toHaveTextContent("0 найдено");
    expect(existingRow).toHaveTextContent("Следующая проверка");
    expect(existingRow).toHaveTextContent("Запусков ещё нет");
    await user.click(screen.getByRole("button", { name: "Создать автоматизацию" }));
    const dialog = screen.getByRole("dialog", { name: "Создать автоматизацию" });
    const automationTitle = within(dialog).getByLabelText("Название");
    expect(automationTitle).toHaveAttribute("name", "title");
    expect(automationTitle).toHaveAttribute("autocomplete", "off");
    expect(dialog.querySelector('[name="name"]')).not.toBeInTheDocument();
    await user.type(automationTitle, "Factory ready issues");
    await user.selectOptions(within(dialog).getByLabelText("Сценарий"), "workflow-implement");
    await user.selectOptions(within(dialog).getByLabelText("Репозиторий"), "repo-factory");
    await user.type(within(dialog).getByLabelText("Контекст автоматизации"), "Fetch and revalidate live state.");
    await user.click(within(dialog).getByRole("button", { name: "Создать автоматизацию" }));

    expect(await screen.findByRole("heading", { name: "Factory ready issues" })).toBeVisible();
    expect(screen.getByText("Автоматизация выключена.")).toBeVisible();
    expect(screen.getByText("Зафиксированных запусков пока нет.")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Изменить" }));
    const editDialog = screen.getByRole("dialog", { name: "Изменить автоматизацию" });
    const editName = within(editDialog).getByLabelText("Название");
    await user.clear(editName);
    await user.type(editName, "Edited ready issues");
    await user.click(within(editDialog).getByRole("button", { name: "Сохранить изменения" }));
    expect(await screen.findByRole("heading", { name: "Edited ready issues" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Проверить триггер" }));
    expect(await screen.findByText("#184 Typed Automations")).toBeVisible();
    expect(screen.getByText("Проверка не создаёт задачу или постоянную запись запуска.")).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Включить" }));
    expect(screen.queryByRole("checkbox", { name: /factory-poller is stopped/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Подтвердить включение" }));
    expect(await screen.findByRole("button", { name: "Выключить" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Проверить сейчас" }));
    expect(await screen.findByText("GitHub проверяется сейчас.")).toBeVisible();
    expect(fetch.mock.calls.some(([input, init]) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      return path.endsWith("/check") && init?.method === "POST";
    })).toBe(true);
  });

  it("filters a multi-repository Automation workspace by repository and status", async () => {
    window.history.replaceState({}, "", "/automations");
    mockControlPlane({ multiRepositoryAutomations: true });
    const user = userEvent.setup();
    renderApp();

    expect(await screen.findByText("Docs review")).toBeVisible();
    await user.selectOptions(screen.getByLabelText("Репозиторий"), "github.com/example/disabled");
    expect(screen.getByText("Docs review")).toBeVisible();
    expect(screen.queryByText("Ready issues")).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Статус"), "disabled");
    expect(await screen.findByRole("heading", { name: "Подходящих автоматизаций нет" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Сбросить фильтры" }));
    expect(await screen.findByText("Ready issues")).toBeVisible();
    expect(screen.getByText("Docs review")).toBeVisible();
  });

  it("shows every Factory automation category and honest missing data", async () => {
    window.history.replaceState({}, "", "/automations");
    mockControlPlane();
    renderApp();

    const status = await screen.findByLabelText("Живой статус автоматик");
    expect(within(status).getByText("Factory pilot")).toBeVisible();
    expect(within(status).getByText("Release broker")).toBeVisible();
    expect(within(status).getByText("Factory intake")).toBeVisible();
    expect(within(status).getByText("Factory janitor")).toBeVisible();
    expect(within(status).getAllByText("нет данных")).toHaveLength(2);
    expect(within(status).getAllByText("Нет данных")).toHaveLength(2);
  });

  it("shows the newest durable Run instead of an older dispatched task", async () => {
    window.history.replaceState({}, "", "/automations");
    mockControlPlane({ automationRunWithoutTaskState: "failed" });
    renderApp();

    const row = await screen.findByRole("button", { name: /Ready issues/ });
    expect(row).toHaveTextContent("#185 Newest run without task");
    expect(row).toHaveTextContent("Ошибка");
    expect(row).not.toHaveTextContent("Older dispatched task");
  });

  it.each([
    ["queued", "В очереди"],
    ["running", "Выполняется"],
    ["succeeded", "Выполнено"],
    ["failed", "Ошибка"],
    ["cancelled", "Отменено"],
  ] as const)("shows a linked %s task as the Automation Run state", async (taskState, label) => {
    window.history.replaceState({}, "", "/automations/automation-ready");
    mockControlPlane({ automationTaskState: taskState });
    renderApp();

    const identity = await screen.findByText("#184 Typed Automation run state", { selector: ".occurrence-identity strong" });
    const row = identity.closest(".occurrence-row");
    expect(row).not.toBeNull();
    expect(within(row as HTMLElement).getByText(label, { selector: ".status-badge" })).toBeVisible();
    expect(within(row as HTMLElement).getByRole("link", { name: "Источник GitHub" })).toHaveAttribute(
      "href",
      "https://github.com/example/factory/issues/184",
    );
    expect(await screen.findByText("Implement the change and run the required checks.", { selector: ".runbook-copy" })).toBeVisible();
  });

	 it.each([
		["queued", "queued", "Повтор ожидает запуска"],
		["running", "running", "Повтор выполняется"],
		["failed", "final_failed", "Сбой после повтора"],
		["failed", "skipped_disabled", "Сбой — автоматизация отключена"],
		["failed", "skipped_worker_unavailable", "Сбой — исполнитель недоступен"],
	 ] as const)("shows owner-facing retry status %s", async (taskState, retryStatus, label) => {
		window.history.replaceState({}, "", "/automations/automation-ready");
		mockControlPlane({ automationTaskState: taskState, automationRetryStatus: retryStatus });
		renderApp();

		const badges = await screen.findAllByText(label, { selector: ".status-badge" });
		expect(badges).toHaveLength(2);
	 });

  it("previews, imports, resolves, and finalizes a legacy poller migration", async () => {
    window.history.replaceState({}, "", "/automations");
    const fetch = mockControlPlane();
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("button", { name: "Перенести старый опросчик" }));
    const dialog = screen.getByRole("dialog", { name: "Перенос старого опросчика" });
    expect(within(dialog).getByRole("button", { name: "Проверить заблокированный снимок" })).toBeDisabled();
    await user.type(within(dialog).getByLabelText("Старый poller.toml"), "/tmp/legacy/poller.toml");
    await user.click(within(dialog).getByRole("checkbox", { name: /Все процессы factory-poller остановлены/ }));
    await user.click(within(dialog).getByRole("button", { name: "Проверить заблокированный снимок" }));

    expect(await within(dialog).findByText("1 поддерживается · 0 не поддерживается")).toBeVisible();
    expect(within(dialog).getAllByText("/tmp/legacy", { exact: true })).toHaveLength(2);
    expect(within(dialog).getByText("/tmp/legacy/poller", { exact: true })).toBeVisible();
    expect(within(dialog).getByText(/^Репозиторий:/)).toHaveTextContent("github.com/example/factory");
    expect(within(dialog).getByText(/^Репозиторий:/)).toHaveTextContent("repo-factory");
    expect(within(dialog).getByText(/0 отправлено · 1 ожидает · каждые 30 с/)).toBeVisible();
    const workflowTitle = within(dialog).getByLabelText("Название сценария");
    const automationTitle = within(dialog).getByLabelText("Название автоматизации");
    await user.clear(workflowTitle);
    await user.type(workflowTitle, "Imported implementation workflow");
    await user.clear(automationTitle);
    await user.type(automationTitle, "Imported ready issues");
    await user.click(within(dialog).getByRole("button", { name: "Импортировать выключенными" }));

    expect(await within(dialog).findByText("1 не решено")).toBeVisible();
    expect(within(dialog).getByRole("button", { name: "Завершить и архивировать" })).toBeDisabled();
    await user.click(within(dialog).getAllByRole("button", { name: "Закрыть" })[1]);
    await user.click(screen.getByRole("button", { name: "Перенести старый опросчик" }));
    const resumedDialog = screen.getByRole("dialog", { name: "Перенос старого опросчика" });
    expect(await within(resumedDialog).findByText("1 не решено")).toBeVisible();
    const reconfirm = within(resumedDialog).getByRole("checkbox", { name: /Все процессы factory-poller по-прежнему остановлены/ });
    expect(reconfirm).not.toBeChecked();
    expect(within(resumedDialog).getByRole("button", { name: "Пропустить" })).toBeDisabled();
    await user.click(reconfirm);
    await user.click(within(resumedDialog).getByRole("button", { name: "Пропустить" }));
    await vi.waitFor(() => expect(within(resumedDialog).getByText("0 не решено")).toBeVisible());
    await user.click(within(resumedDialog).getByRole("button", { name: "Завершить и архивировать" }));

    expect(await within(resumedDialog).findByText("Перенос завершён")).toBeVisible();
    expect(within(resumedDialog).getByText("/tmp/legacy/archive/legacy-migration")).toBeVisible();
    expect(within(resumedDialog).getByRole("button", { name: "Проверить Imported ready issues" })).toBeVisible();
    const importCall = fetch.mock.calls.find(([input, init]) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      return path === "/api/v1/migrations/legacy-poller/import" && init?.method === "POST";
    });
    expect(importCall).toBeDefined();
    expect(JSON.parse(String(importCall?.[1]?.body))).toMatchObject({
      migration_id: "legacy-migration",
      mappings: [{
        queue_id: "legacy-queue",
        workflow_title: "Imported implementation workflow",
        automation_title: "Imported ready issues",
      }],
    });
  });

  it("requires Skip for an imported invalid pending observation", async () => {
    window.history.replaceState({}, "", "/automations");
    mockControlPlane({ failedLegacyOccurrence: true });
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("button", { name: "Перенести старый опросчик" }));
    const dialog = screen.getByRole("dialog", { name: "Перенос старого опросчика" });
    await user.click(within(dialog).getByRole("checkbox", { name: /Все процессы factory-poller остановлены/ }));
    await user.click(within(dialog).getByRole("button", { name: "Проверить заблокированный снимок" }));
    await user.click(await within(dialog).findByRole("button", { name: "Импортировать выключенными" }));

    expect(await within(dialog).findByText("legacy_pending_invalid_requires_skip")).toBeVisible();
    expect(within(dialog).queryByRole("button", { name: "Продолжить" })).not.toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Пропустить" })).toBeEnabled();
  });

  it("archives a command-only legacy migration without creating Automations", async () => {
    window.history.replaceState({}, "", "/automations");
    mockControlPlane({ commandOnlyMigration: true });
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("button", { name: "Перенести старый опросчик" }));
    const dialog = screen.getByRole("dialog", { name: "Перенос старого опросчика" });
    await user.click(within(dialog).getByRole("checkbox", { name: /Все процессы factory-poller остановлены/ }));
    await user.click(within(dialog).getByRole("button", { name: "Проверить заблокированный снимок" }));
    expect(await within(dialog).findByText("0 поддерживается · 1 не поддерживается")).toBeVisible();
    expect(within(dialog).getByText("1 отправлено · 1 ожидает", { exact: true })).toBeVisible();
    await user.click(within(dialog).getByRole("button", { name: "Перейти к архиву" }));
    expect(await within(dialog).findByRole("button", { name: "Завершить и архивировать" })).toBeEnabled();
    expect(within(dialog).getByText("0 поддерживается · 1 не поддерживается")).toBeVisible();
    await user.click(within(dialog).getAllByRole("button", { name: "Закрыть" })[1]);
    await user.click(screen.getByRole("button", { name: "Перенести старый опросчик" }));
    const resumedDialog = screen.getByRole("dialog", { name: "Перенос старого опросчика" });
    expect(await within(resumedDialog).findByText("0 поддерживается · 1 не поддерживается")).toBeVisible();
    expect(within(resumedDialog).getByText("1 отправлено · 1 ожидает", { exact: true })).toBeVisible();
    await user.click(within(resumedDialog).getByRole("checkbox", { name: /Все процессы factory-poller по-прежнему остановлены/ }));
    await user.click(within(resumedDialog).getByRole("button", { name: "Завершить и архивировать" }));
    expect(await within(resumedDialog).findByText("Перенос завершён")).toBeVisible();
  });

  it("blocks Import when the ledger contains a removed queue", async () => {
    window.history.replaceState({}, "", "/automations");
    const fetch = mockControlPlane({ ledgerOnlyMigration: true });
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("button", { name: "Перенести старый опросчик" }));
    const dialog = screen.getByRole("dialog", { name: "Перенос старого опросчика" });
    await user.click(within(dialog).getByRole("checkbox", { name: /Все процессы factory-poller остановлены/ }));
    await user.click(within(dialog).getByRole("button", { name: "Проверить заблокированный снимок" }));

    expect(await within(dialog).findByText("1 поддерживается · 1 не поддерживается")).toBeVisible();
    expect(within(dialog).getByText(/restore the matching queue before Import/)).toBeVisible();
    expect(within(dialog).getByRole("button", { name: "Восстановите отсутствующую очередь" })).toBeDisabled();
    expect(fetch.mock.calls.some(([input]) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      return path === "/api/v1/migrations/legacy-poller/import";
    })).toBe(false);
  });

  it("creates, previews, enables, and runs a typed schedule Automation", async () => {
    window.history.replaceState({}, "", "/automations");
    const fetch = mockControlPlane({ runFailures: 1 });
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("button", { name: "Создать автоматизацию" }));
    const dialog = screen.getByRole("dialog", { name: "Создать автоматизацию" });
    await user.type(within(dialog).getByLabelText("Название"), "Daily Factory maintenance");
    await user.selectOptions(within(dialog).getByLabelText("Сценарий"), "workflow-implement");
    await user.selectOptions(within(dialog).getByLabelText("Репозиторий"), "repo-factory");
    await user.selectOptions(within(dialog).getByLabelText("Триггер"), "schedule");
    await user.selectOptions(within(dialog).getByLabelText("Частота"), "custom");
    await user.clear(within(dialog).getByLabelText("Cron (пять полей)"));
    await user.type(within(dialog).getByLabelText("Cron (пять полей)"), "0 9 * * 1");
    await user.clear(within(dialog).getByLabelText("Часовой пояс"));
    await user.type(within(dialog).getByLabelText("Часовой пояс"), "Europe/London");
    await user.click(within(dialog).getByRole("button", { name: "Создать автоматизацию" }));

    expect(await screen.findByRole("heading", { name: "Daily Factory maintenance" })).toBeVisible();
    expect(screen.getByText("0 9 * * 1")).toBeVisible();
    expect(screen.getByText("Europe/London")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Проверить триггер" }));
    expect(await screen.findByText(/Следующий подходящий момент UTC/i)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Включить патруль конвейера" }));
    expect(screen.getByText(/Cron и часовой пояс не изменятся/i)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Подтвердить патруль" }));
    expect(await screen.findByText("Патруль конвейера настроен по существующему расписанию.")).toBeVisible();
    expect(fetch.mock.calls.some(([input, init]) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      return path.endsWith("/api/v1/automations/automation-created/pipeline-patrol") && init?.method === "POST";
    })).toBe(true);
    await user.click(await screen.findByRole("button", { name: "Запустить сейчас" }));
    expect(await screen.findByText(/connection lost after Run now commit/i)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Запустить сейчас" }));
    expect(await screen.findByText("Ручной запуск", { selector: ".occurrence-identity strong" })).toBeVisible();
    expect(screen.getAllByText("Ручной запуск", { selector: ".occurrence-identity strong" })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "Открыть задачу" })).toHaveLength(1);
    const runBodies = fetch.mock.calls
      .filter(([input, init]) => {
        const path = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
        return path.endsWith("/run") && init?.method === "POST";
      })
      .map(([, init]) => JSON.parse(String(init?.body)) as { request_key: string });
    expect(runBodies).toHaveLength(2);
    expect(runBodies[0].request_key).toBe(runBodies[1].request_key);
  });

  it("preserves Automation form focus and typed input during background refresh", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      window.history.replaceState({}, "", "/automations");
      mockControlPlane();
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      renderApp();

      await user.click(await screen.findByRole("button", { name: "Создать автоматизацию" }));
      const input = screen.getByLabelText("Контекст автоматизации");
      await user.type(input, "In progress Automation context");
      expect(input).toHaveFocus();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(5_000);
      });

      expect(input).toHaveValue("In progress Automation context");
      expect(input).toHaveFocus();
    } finally {
      vi.useRealTimers();
    }
  });

  it("creates and previews a typed GitHub pull-request Automation", async () => {
    window.history.replaceState({}, "", "/automations");
    mockControlPlane();
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("button", { name: "Создать автоматизацию" }));
    const dialog = screen.getByRole("dialog", { name: "Создать автоматизацию" });
    await user.type(within(dialog).getByLabelText("Название"), "Factory pull request reviews");
    await user.selectOptions(within(dialog).getByLabelText("Сценарий"), "workflow-implement");
    await user.selectOptions(within(dialog).getByLabelText("Репозиторий"), "repo-factory");
    await user.selectOptions(within(dialog).getByLabelText("Триггер"), "github_pull_request");
    await user.selectOptions(within(dialog).getByLabelText("Состояние pull request"), "open");
    await user.click(within(dialog).getByLabelText("Включать черновики"));
    await user.clear(within(dialog).getByLabelText("Обязательные метки"));
    await user.type(within(dialog).getByLabelText("Обязательные метки"), "factory:review");
    await user.type(within(dialog).getByLabelText("Базовые ветки"), "main, release");
    await user.click(within(dialog).getByRole("button", { name: "Создать автоматизацию" }));

    expect(await screen.findByRole("heading", { name: "Factory pull request reviews" })).toBeVisible();
    expect(screen.getByText("Включены")).toBeVisible();
    expect(screen.getByText("main, release")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Проверить триггер" }));
    expect(await screen.findByText("#185 Typed pull-request Automations")).toBeVisible();
    expect(screen.getByText(/база main/)).toBeVisible();
  });

  it("loads every Workflow page in the Automation form", async () => {
    window.history.replaceState({}, "", "/automations");
    mockControlPlane({ paginatedAutomationWorkflows: true });
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("button", { name: "Создать автоматизацию" }));
    const workflow = screen.getByLabelText("Сценарий");
    expect(await within(workflow).findByRole("option", { name: "Historical workflow" })).toHaveValue("workflow-history");
  });

  it("keeps direct-detail Automation selections while form options load", async () => {
    window.history.replaceState({}, "", "/automations/automation-ready");
    const fetch = mockControlPlane();
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("button", { name: "Изменить" }));
    const dialog = screen.getByRole("dialog", { name: "Изменить автоматизацию" });
    expect(within(dialog).getByLabelText("Сценарий")).toHaveValue("workflow-implement");
    expect(within(dialog).getByLabelText("Репозиторий")).toHaveValue("repo-factory");
    await user.type(within(dialog).getByLabelText("Название"), " updated");
    await user.click(within(dialog).getByRole("button", { name: "Сохранить изменения" }));
    expect(fetch.mock.calls.some(([input, init]) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (!path.endsWith("/api/v1/automations/automation-ready") || init?.method !== "PUT") return false;
      const body = JSON.parse(String(init.body)) as { workflow_id: string };
      return body.workflow_id === "workflow-implement";
    })).toBe(true);
  });

  it("loads additional Automation and Occurrence pages", async () => {
    window.history.replaceState({}, "", "/automations");
    mockControlPlane({ paginatedAutomations: true, paginatedAutomationOccurrences: true });
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("button", { name: "Показать ещё автоматизации" }));
    expect(await screen.findByText("Historical Automation")).toBeVisible();

    await user.click(screen.getByRole("button", { name: /Ready issues/ }));
    expect(await screen.findByText("#184 Paged issue 184", { selector: ".occurrence-identity strong" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Показать ещё запуски" }));
    expect(await screen.findByText("#183 Paged issue 183", { selector: ".occurrence-identity strong" })).toBeVisible();
  });

  it("keeps a refreshed Workflow head entry over its stale loaded history copy", async () => {
    window.history.replaceState({}, "", "/workflows");
    mockControlPlane({ refreshesHistoricalWorkflow: true });
    const user = userEvent.setup();
    const { client } = renderApp();

    await user.click(await screen.findByRole("button", { name: "Показать ещё сценарии" }));
    expect(await screen.findByText("Historical workflow")).toBeVisible();

    await client.refetchQueries({ queryKey: ["workflows", "head"] });

    expect(await screen.findByText("Refreshed workflow")).toBeVisible();
    expect(screen.queryByText("Historical workflow")).not.toBeInTheDocument();
    const refreshedRow = screen.getByText("Refreshed workflow").closest(".workflow-row");
    expect(refreshedRow).not.toBeNull();
    expect(within(refreshedRow as HTMLElement).getByText("#2")).toBeVisible();
    expect(within(refreshedRow as HTMLElement).getByText("Выключен")).toBeVisible();
  });

  it("restarts Workflow history from a changed head boundary", async () => {
    window.history.replaceState({}, "", "/workflows");
    let releaseWorkflowHistory!: () => void;
    const workflowHistoryGate = new Promise<void>((resolve) => {
      releaseWorkflowHistory = resolve;
    });
    const fetch = mockControlPlane({ shiftingWorkflowBoundary: true, workflowHistoryGate });
    const user = userEvent.setup();
    const { client } = renderApp();

    await user.click(await screen.findByRole("button", { name: "Показать ещё сценарии" }));
    await vi.waitFor(() => expect(workflowRequestPaths(fetch)).toContain(
      "/api/v1/workflows?limit=200&cursor=old-workflow-boundary",
    ));

    await client.refetchQueries({ queryKey: ["workflows", "head"] });
    releaseWorkflowHistory();
    expect(await screen.findByText("Historical workflow")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Показать ещё сценарии" }));

    expect(await screen.findByText("Shifted boundary workflow")).toBeVisible();
    expect(workflowRequestPaths(fetch)).toEqual([
      "/api/v1/workflows?limit=200",
      "/api/v1/workflows?limit=200&cursor=old-workflow-boundary",
      "/api/v1/workflows?limit=200",
      "/api/v1/workflows?limit=200&cursor=new-workflow-boundary",
    ]);
  });

  it("pins an enabled Workflow revision while preserving free-text context", async () => {
    const fetch = mockControlPlane();
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("button", { name: "Поставить задачу" }));
    const dialog = screen.getByRole("dialog", { name: "Delegate task" });
    await user.type(within(dialog).getByLabelText("Title"), "Implement #183");
    await user.selectOptions(within(dialog).getByLabelText("Workflow"), "workflow-revision-1");
    await user.type(within(dialog).getByLabelText("Context"), "Issue #183 remains ordinary text.");
    await user.selectOptions(within(dialog).getByLabelText("Worker"), "worker-online");
    await user.selectOptions(within(dialog).getByLabelText("Repository"), "repo-factory");
    await user.click(within(dialog).getByRole("button", { name: "Delegate task" }));

    expect(await screen.findByRole("heading", { name: "Implement #183" })).toBeVisible();
    expect(screen.getByText("Implement · revision 1")).toBeVisible();
    await user.click(screen.getByText("Задание агенту (техническое) — развернуть"));
    expect(screen.getByText("Issue #183 remains ordinary text.", { selector: ".long-copy" })).toBeVisible();
    await user.click(screen.getByText("Полный промпт (инструкция + контекст) — развернуть"));
    expect(screen.getByText(/Workflow instructions:/)).toBeVisible();
    const taskCreate = fetch.mock.calls.find(([input, init]) => input === "/api/v1/tasks" && init?.method === "POST");
    expect(JSON.parse(String(taskCreate?.[1]?.body))).toMatchObject({
      context: "Issue #183 remains ordinary text.",
      workflow_revision_id: "workflow-revision-1",
    });
  });

  it("keeps task submission disabled throughout attachment upload and creation", async () => {
    const fetch = mockControlPlane();
    const fixtureImplementation = fetch.getMockImplementation()!;
    let releaseUpload!: () => void;
    const uploadGate = new Promise<void>((resolve) => { releaseUpload = resolve; });
    fetch.mockImplementation(async (input, init) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (path === "/api/v1/task-attachments" && init?.method === "POST") {
        await uploadGate;
        return Response.json({ id: "attachment-1", name: "screen.png", content_type: "image/png", size: 5, sha256: "hash" }, { status: 201 });
      }
      return fixtureImplementation(input, init);
    });
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("button", { name: "Поставить задачу" }));
    const dialog = screen.getByRole("dialog", { name: "Delegate task" });
    await user.type(within(dialog).getByLabelText("Title"), "Inspect screenshot");
    await user.type(within(dialog).getByLabelText("Context"), "Use the supplied screenshot.");
    await user.selectOptions(within(dialog).getByLabelText("Worker"), "worker-online");
    await user.selectOptions(within(dialog).getByLabelText("Repository"), "repo-factory");
    await user.upload(within(dialog).getByLabelText("Files"), new File(["image"], "screen.png", { type: "image/png" }));
    await user.click(within(dialog).getByRole("button", { name: "Delegate task" }));

    const submitting = within(dialog).getByRole("button", { name: "Delegating…" });
    expect(submitting).toBeDisabled();
    expect(fetch.mock.calls.some(([input, init]) => input === "/api/v1/tasks" && init?.method === "POST")).toBe(false);
    await user.click(submitting);
    expect(fetch.mock.calls.filter(([input]) => input === "/api/v1/task-attachments")).toHaveLength(1);

    releaseUpload();
    expect(await screen.findByRole("heading", { name: "Inspect screenshot" })).toBeVisible();
  });

  it("renders every task status in the operational board", async () => {
    mockControlPlane();
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("button", { name: "Показать по этапам" }));
    for (const [heading, title] of [
      ["Задачи: ожидают запуска", "queued task"],
      ["В работе", "running task"],
      ["Отработали", "succeeded task"],
      ["Сорвались", "failed task"],
      ["Отменены", "cancelled task"],
    ]) {
      const column = screen.getByRole("heading", { name: heading }).closest("section");
      expect(column).not.toBeNull();
      expect(within(column as HTMLElement).getByText(title)).toBeVisible();
    }
  });

  it("counts available capacity only from online healthy workers", async () => {
    mockControlPlane();
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("button", { name: /^Исполнители$/ }));
    const summary = screen.getByLabelText("Сводка исполнителей");
    expect(within(summary).getByText("Свободно мест").closest("div")).toHaveTextContent("4");
    expect(screen.getByLabelText("6 из 10 мест занято")).toBeVisible();
  });

  it("loads another bounded task page without duplicating existing work", async () => {
    mockControlPlane({ paginatedTasks: true });
    const user = userEvent.setup();
    renderApp();

    expect(await screen.findByText("queued task")).toBeVisible();
    expect(screen.queryByText("running task")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Показать ещё" }));

    expect(await screen.findByText("running task")).toBeVisible();
    expect(screen.getAllByText("queued task")).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Показать ещё" })).not.toBeInTheDocument();
  });

  it("polls only the live head page after older work is loaded", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const fetch = mockControlPlane({ paginatedTasks: true });
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      renderApp();
      await user.click(await screen.findByRole("button", { name: "Показать ещё" }));
      expect(await screen.findByText("running task")).toBeVisible();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(5_000);
      });

      const taskPaths = fetch.mock.calls
        .map(([input]) => typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url)
        .filter((path) => path.startsWith("/api/v1/tasks?"));
      expect(taskPaths.filter((path) => path === "/api/v1/tasks?limit=200")).toHaveLength(2);
      expect(
        taskPaths.filter((path) => path === "/api/v1/tasks?limit=200&cursor=next-page"),
      ).toHaveLength(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("does not retain tasks shifted out of the live head without loading history", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      mockControlPlane({ boundedLiveHead: true });
      renderApp();
      expect(await screen.findByText("queued task")).toBeVisible();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(5_000);
      });

      expect(screen.getByText("new head task")).toBeVisible();
      expect(screen.queryByText("queued task")).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("exposes a new history cursor when the live head grows beyond one page", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      mockControlPlane({ growingTaskHistory: true });
      renderApp();
      expect(await screen.findByText("queued task")).toBeVisible();
      expect(screen.queryByRole("button", { name: "Показать ещё" })).not.toBeInTheDocument();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(5_000);
      });

      expect(screen.getByRole("button", { name: "Показать ещё" })).toBeVisible();
    } finally {
      vi.useRealTimers();
    }
  });

  it("reopens exhausted history from a changed live-head boundary without duplicates", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const fetch = mockControlPlane({ shiftingTaskBoundary: true });
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      renderApp();

      await user.click(await screen.findByRole("button", { name: "Показать ещё" }));
      expect(await screen.findByText("running task")).toBeVisible();
      expect(screen.queryByText("succeeded task")).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Показать ещё" })).not.toBeInTheDocument();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(5_000);
      });
      expect(screen.getByText("new head task")).toBeVisible();
      await user.click(screen.getByRole("button", { name: "Показать ещё" }));

      expect(screen.getByRole("heading", { name: "Сделано" })).toBeVisible();
      expect(await screen.findByText("succeeded task")).toBeVisible();
      expect(screen.getAllByText("running task")).toHaveLength(1);
      await user.click(screen.getByRole("button", { name: "Показать по этапам" }));
      const succeededColumn = screen.getByRole("heading", { name: "Отработали" }).closest("section");
      expect(succeededColumn).not.toBeNull();
      expect(within(succeededColumn as HTMLElement).getByText("running task")).toBeVisible();
      const taskPaths = fetch.mock.calls
        .map(([input]) => typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url)
        .filter((path) => path.startsWith("/api/v1/tasks?"));
      expect(taskPaths).toEqual([
        "/api/v1/tasks?limit=200",
        "/api/v1/tasks?limit=200&cursor=old-boundary",
        "/api/v1/tasks?limit=200",
        "/api/v1/tasks?limit=200&cursor=new-boundary",
      ]);
    } finally {
      vi.useRealTimers();
    }
  });

  it("restricts repositories to the selected worker and warns for offline work", async () => {
    mockControlPlane();
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("button", { name: "Поставить задачу" }));
    const dialog = screen.getByRole("dialog", { name: "Delegate task" });
    await user.selectOptions(within(dialog).getByLabelText("Worker"), "worker-online");
    const repository = within(dialog).getByLabelText("Repository");
    expect(within(repository).getByRole("option", { name: /factory/ })).toBeInTheDocument();
    expect(within(repository).getByRole("option", { name: /github.com\/example\/docs/ })).toBeEnabled();
    expect(within(repository).queryByRole("option", { name: /archive/ })).not.toBeInTheDocument();

    await user.selectOptions(within(dialog).getByLabelText("Worker"), "worker-offline");
    expect(within(dialog).getByText(/task will queue until it returns/i)).toBeVisible();
    expect(within(repository).getByRole("option", { name: /archive/ })).toBeEnabled();
    expect(within(repository).getByRole("option", { name: /github.com\/example\/factory/ })).toBeDisabled();
  });

  it("confirms permanent deletion only for terminal task history", async () => {
    window.history.replaceState({}, "", "/tasks/task-succeeded");
    const fetch = mockControlPlane();
    const user = userEvent.setup();
    const { client } = renderApp();

    expect(await screen.findByRole("heading", { name: "succeeded task" })).toBeVisible();
    expect(await screen.findByText("Terminal event")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Delete history" }));
    expect(screen.getByText(/Permanently delete this task, prompt, attempts, and events/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Keep history" }));
    expect(screen.queryByRole("button", { name: "Confirm delete" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Delete history" }));
    await user.click(screen.getByRole("button", { name: "Confirm delete" }));

    expect(await screen.findByText("queued task")).toBeVisible();
    expect(screen.queryByText("succeeded task")).not.toBeInTheDocument();
    const deleteCall = fetch.mock.calls.find(([, init]) => init?.method === "DELETE");
    expect(deleteCall?.[0]).toBe("/api/v1/tasks/task-succeeded");
    expect(deleteCall?.[1]?.body).toBe("{}");
    expect(client.getQueryData(["task", "task-succeeded"])).toBeUndefined();
    expect(client.getQueryData(["events", "attempt-succeeded"])).toBeUndefined();
    expect(
      client
        .getQueryData<{ tasks: Array<{ id: string }> }>(["tasks", "head"])
        ?.tasks.some((task) => task.id === "task-succeeded"),
    ).toBe(false);
  });

  it("does not offer history deletion for active work", async () => {
    window.history.replaceState({}, "", "/tasks/task-running");
    mockControlPlane();
    renderApp();
    expect(await screen.findByRole("heading", { name: "running task" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Delete history" })).not.toBeInTheDocument();
  });

  it("does not restore deleted work when an older history request finishes late", async () => {
    const fetch = mockControlPlane({ staleHistoryAfterDelete: true });
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("button", { name: "Показать ещё" }));
    await user.click(screen.getByRole("button", { name: "Показать по этапам" }));
    await user.click(screen.getByText("succeeded task"));
    expect(await screen.findByRole("heading", { name: "succeeded task" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Delete history" }));
    await user.click(screen.getByRole("button", { name: "Confirm delete" }));

    expect(await screen.findByText("queued task")).toBeVisible();
    await vi.waitFor(() => {
      expect(screen.queryByRole("button", { name: "Показать ещё" })).not.toBeInTheDocument();
    });
    expect(screen.queryByText("succeeded task")).not.toBeInTheDocument();
    expect(fetch.mock.calls.some(([input]) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      return path === "/api/v1/tasks?limit=200&cursor=stale-page";
    })).toBe(true);
  });

  it("validates the delegate form and creates a normalized task", async () => {
    const fetch = mockControlPlane();
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("button", { name: "Поставить задачу" }));
    const dialog = screen.getByRole("dialog", { name: "Delegate task" });
    await user.click(within(dialog).getByRole("button", { name: "Delegate task" }));
    expect(within(dialog).getByText("Enter a task title.")).toBeVisible();
    expect(within(dialog).getByText("Enter task context.")).toBeVisible();

    await user.type(within(dialog).getByLabelText("Title"), "Ship the UI");
    await user.type(within(dialog).getByLabelText("Context"), "Build and verify the real interface.");
    await user.selectOptions(within(dialog).getByLabelText("Worker"), "worker-online");
    await user.selectOptions(within(dialog).getByLabelText("Repository"), "repo-factory");
    await user.click(within(dialog).getByRole("button", { name: "Delegate task" }));

    expect(await screen.findByRole("heading", { name: "Ship the UI" })).toBeVisible();
    expect(screen.getByText("Progress will appear when the worker starts this task.")).toBeVisible();
    const createCall = fetch.mock.calls.find(([, init]) => init?.method === "POST");
    expect(createCall).toBeDefined();
    expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
      title: "Ship the UI",
      description: "Build and verify the real interface.",
      worker_id: "worker-online",
      repository_id: "repo-factory",
      timeout_seconds: 7200,
    });
  });

  it("delegates the selected repository to the selected worker", async () => {
    const fetch = mockControlPlane();
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("button", { name: "Поставить задачу" }));
    const dialog = screen.getByRole("dialog", { name: "Delegate task" });
    await user.type(within(dialog).getByLabelText("Title"), "Work in selected repository");
    await user.type(within(dialog).getByLabelText("Context"), "Use the repository selected for this worker.");
    await user.selectOptions(within(dialog).getByLabelText("Worker"), "worker-online");
    const repositoryPicker = within(dialog).getByLabelText("Repository");
    expect(within(repositoryPicker).getByRole("option", { name: /docs · github\.com\/example\/docs/ })).toBeEnabled();
    await user.selectOptions(repositoryPicker, "repo-docs");
    await user.click(within(dialog).getByRole("button", { name: "Delegate task" }));

    expect(await screen.findByRole("heading", { name: "Work in selected repository" })).toBeVisible();
    const createCall = fetch.mock.calls.find(([input, init]) => input === "/api/v1/tasks" && init?.method === "POST");
    expect(createCall).toBeDefined();
    const createBody = JSON.parse(String(createCall?.[1]?.body));
    expect(createBody).toMatchObject({
      title: "Work in selected repository",
      worker_id: "worker-online",
      repository_id: "repo-docs",
    });
  });

  it("closes the keyboard-accessible drawer with Escape", async () => {
    mockControlPlane();
    const user = userEvent.setup();
    renderApp();
    const trigger = await screen.findByRole("button", { name: "Поставить задачу" });
    await user.click(trigger);
    expect(screen.getByRole("dialog")).toBeVisible();
    expect(screen.getByLabelText("Title")).toHaveFocus();
    await user.tab({ shift: true });
    expect(screen.getByRole("button", { name: "Close" })).toHaveFocus();
    await user.tab({ shift: true });
    expect(within(screen.getByRole("dialog")).getByRole("button", { name: "Delegate task" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await vi.waitFor(() => expect(trigger).toHaveFocus());
  });

  it("preselects the worker when assigning from worker detail", async () => {
    window.history.replaceState({}, "", "/workers/worker-online");
    mockControlPlane();
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("button", { name: "Назначить работу" }));

    expect(screen.getByRole("dialog", { name: "Delegate task" })).toBeVisible();
    expect(screen.getByLabelText("Worker")).toHaveValue("worker-online");
    expect(screen.getByLabelText("Repository")).toBeEnabled();
  });

  it("presents worker facts in accessible profile tabs with read-only execution settings", async () => {
    window.history.replaceState({}, "", "/workers/worker-online");
    mockControlPlane();
    const user = userEvent.setup();
    renderApp();

    expect(await screen.findByRole("heading", { name: "Build Mac" })).toBeVisible();
    const tabs = screen.getByRole("tablist", { name: "Профиль исполнителя" });
    const overview = within(tabs).getByRole("tab", { name: "Обзор" });
    const work = within(tabs).getByRole("tab", { name: "Работа" });
    const capabilities = within(tabs).getByRole("tab", { name: "Возможности" });
    const settings = within(tabs).getByRole("tab", { name: "Настройки" });
    for (const tab of [overview, work, capabilities, settings]) {
      expect(document.getElementById(tab.getAttribute("aria-controls") ?? "")).not.toBeNull();
    }
    expect(overview).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("region", { name: "Сводка исполнителя" })).toHaveTextContent("6 / 10");

    overview.focus();
    await user.keyboard("{ArrowRight}");
    expect(work).toHaveFocus();
    expect(work).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Сохранённые рабочие копии");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Последняя из сеансов: 6 занято");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Последняя активная задача");

    await user.keyboard("{End}");
    expect(settings).toHaveFocus();
    const settingsPanel = screen.getByRole("tabpanel");
    expect(within(settingsPanel).getByRole("heading", { name: "Выполнение" })).toBeVisible();
    expect(within(settingsPanel).getByText("Только чтение")).toBeVisible();
    expect(within(settingsPanel).getByText("6 / 10")).toBeVisible();
    expect(within(settingsPanel).getByRole("meter", { name: "Параллельность исполнителя" })).toHaveAttribute("max", "10");
    expect(settingsPanel).toHaveTextContent("max_concurrent");
    expect(settingsPanel).toHaveTextContent("перезапустите исполнитель");
    expect(within(settingsPanel).queryByRole("textbox")).not.toBeInTheDocument();
    expect(within(settingsPanel).queryByRole("spinbutton")).not.toBeInTheDocument();
    expect(within(settingsPanel).queryByRole("combobox")).not.toBeInTheDocument();

    await user.keyboard("{Home}");
    expect(overview).toHaveFocus();
    await user.click(capabilities);
    const capabilitiesPanel = screen.getByRole("tabpanel");
    expect(capabilitiesPanel).toHaveTextContent("Codex");
    expect(capabilitiesPanel).toHaveTextContent("github.com");
    expect(capabilitiesPanel).toHaveTextContent("github.com/example/factory");
  });

  it("keeps the active delegate field focused while worker data refreshes", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      mockControlPlane();
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      renderApp();

      await user.click(await screen.findByRole("button", { name: "Поставить задачу" }));
      const description = screen.getByLabelText("Context");
      await user.type(description, "Keep typing here.");
      expect(description).toHaveFocus();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(10_000);
      });

      expect(description).toHaveFocus();
      expect(description).toHaveValue("Keep typing here.");
    } finally {
      vi.useRealTimers();
    }
  });

  it("offers an enabled managed repository for on-demand acquisition by the selected worker", async () => {
    mockControlPlane();
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("button", { name: "Поставить задачу" }));
    const dialog = screen.getByRole("dialog", { name: "Delegate task" });
    await user.selectOptions(within(dialog).getByLabelText("Worker"), "worker-online");

    const option = await within(dialog).findByRole("option", { name: /github\.com\/example\/managed.*acquired on demand/ });
    expect(option).toBeEnabled();
  });

  it("reuses the request key after an ambiguous create failure and accepts 200 Unicode characters", async () => {
    const fetch = mockControlPlane({ createFailures: 1 });
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("button", { name: "Поставить задачу" }));
    const dialog = screen.getByRole("dialog", { name: "Delegate task" });
    const validUnicodeTitle = "😀".repeat(200);
    fireEvent.change(within(dialog).getByLabelText("Title"), { target: { value: validUnicodeTitle } });
    await user.type(within(dialog).getByLabelText("Context"), "Prove idempotent browser retries.");
    await user.selectOptions(within(dialog).getByLabelText("Worker"), "worker-online");
    await user.selectOptions(within(dialog).getByLabelText("Repository"), "repo-factory");

    await user.click(within(dialog).getByRole("button", { name: "Delegate task" }));
    expect(await within(dialog).findByText(/connection lost after submit/i)).toBeVisible();
    await user.click(within(dialog).getByRole("button", { name: "Delegate task" }));
    expect(await screen.findByRole("heading", { name: validUnicodeTitle })).toBeVisible();

    const createBodies = fetch.mock.calls
      .filter(([, init]) => init?.method === "POST")
      .map(([, init]) => JSON.parse(String(init?.body)) as { request_key: string; title: string });
    expect(createBodies).toHaveLength(2);
    expect(createBodies[0].request_key).toBe(createBodies[1].request_key);
    expect(createBodies[1].title).toBe(validUnicodeTitle);
  });

  it("rejects a title over the server's 200-code-point limit", async () => {
    mockControlPlane();
    const user = userEvent.setup();
    renderApp();
    await user.click(await screen.findByRole("button", { name: "Поставить задачу" }));
    const dialog = screen.getByRole("dialog", { name: "Delegate task" });
    fireEvent.change(within(dialog).getByLabelText("Title"), { target: { value: "😀".repeat(201) } });
    await user.type(within(dialog).getByLabelText("Context"), "This should not submit.");
    await user.selectOptions(within(dialog).getByLabelText("Worker"), "worker-online");
    await user.selectOptions(within(dialog).getByLabelText("Repository"), "repo-factory");
    await user.click(within(dialog).getByRole("button", { name: "Delegate task" }));
    expect(within(dialog).getByText("Keep the title to 200 characters.")).toBeVisible();
  });

  it("keeps cached task detail visible after a background refresh fails", async () => {
    window.history.replaceState({}, "", "/tasks/task-running");
    mockControlPlane({ taskDetailFailuresAfter: 1 });
    const { client } = renderApp();
    expect(await screen.findByRole("heading", { name: "running task" })).toBeVisible();

    await client.refetchQueries({ queryKey: ["task", "task-running"] });

    expect(screen.getByRole("heading", { name: "running task" })).toBeVisible();
    expect(await screen.findByText(/Showing the last available data/)).toBeVisible();
    expect(screen.getByText(/temporary read failure/)).toBeVisible();
  });

  it("keeps cached ordered progress visible after an events refresh fails", async () => {
    window.history.replaceState({}, "", "/tasks/task-running");
    mockControlPlane({ eventFailuresAfter: 1 });
    const { client } = renderApp();
    expect(await screen.findByText("Cached ordered progress")).toBeVisible();

    await client.refetchQueries({ queryKey: ["events", "attempt-running"] });

    expect(screen.getByText("Cached ordered progress")).toBeVisible();
    expect(await screen.findByText(/progress refresh failed/)).toBeVisible();
  });

  it("drains bounded event pages and later polls after the last cached sequence", async () => {
    window.history.replaceState({}, "", "/tasks/task-running");
    const fetch = mockControlPlane({ incrementalEvents: true });
    const { client } = renderApp();

    expect(await screen.findByText("Incremental event 0")).toBeVisible();
    expect(await screen.findByText("Incremental event 1")).toBeVisible();
    await client.refetchQueries({ queryKey: ["events", "attempt-running"] });
    expect(await screen.findByText("Incremental event 2")).toBeVisible();

    const eventPaths = fetch.mock.calls
      .map(([input]) => typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url)
      .filter((path) => path.includes("/events?"));
    expect(eventPaths).toEqual([
      "/api/v1/attempts/attempt-running/events?after=-1&limit=100",
      "/api/v1/attempts/attempt-running/events?after=0&limit=100",
      "/api/v1/attempts/attempt-running/events?after=1&limit=100",
    ]);
    expect(screen.getAllByText(/Incremental event/)).toHaveLength(3);
  });

  it("starts a distinct empty event cache when the latest attempt changes", async () => {
    window.history.replaceState({}, "", "/tasks/task-running");
    const fetch = mockControlPlane({ switchAttemptAfter: 1 });
    const { client } = renderApp();
    expect(await screen.findByText("Cached ordered progress")).toBeVisible();

    await client.refetchQueries({ queryKey: ["task", "task-running"] });

    expect(await screen.findByText("New attempt starts with an empty event cache")).toBeVisible();
    expect(screen.queryByText("Cached ordered progress")).not.toBeInTheDocument();
    expect(fetch.mock.calls.some(([input]) => {
      const path = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      return path === "/api/v1/attempts/attempt-next/events?after=-1&limit=100";
    })).toBe(true);
  });

  it("performs one final incremental event fetch when active work becomes terminal", async () => {
    window.history.replaceState({}, "", "/tasks/task-running");
    const fetch = mockControlPlane({ terminalTaskAfter: 1 });
    const { client } = renderApp();
    expect(await screen.findByText("Progress before completion")).toBeVisible();

    await client.refetchQueries({ queryKey: ["task", "task-running"] });

    expect(await screen.findByText("Final terminal progress")).toBeVisible();
    const eventPaths = fetch.mock.calls
      .map(([input]) => typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url)
      .filter((path) => path.includes("/events?"));
    expect(eventPaths).toEqual([
      "/api/v1/attempts/attempt-running/events?after=-1&limit=100",
      "/api/v1/attempts/attempt-running/events?after=0&limit=100",
    ]);
  });

  it("does not add a catch-up request when task detail is initially terminal", async () => {
    window.history.replaceState({}, "", "/tasks/task-running");
    const fetch = mockControlPlane({ terminalTaskAfter: 0 });
    renderApp();
    expect(await screen.findByText("Progress before completion")).toBeVisible();

    const eventPaths = fetch.mock.calls
      .map(([input]) => typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url)
      .filter((path) => path.includes("/events?"));
    expect(eventPaths).toEqual([
      "/api/v1/attempts/attempt-running/events?after=-1&limit=100",
    ]);
  });

  it("retries a failed terminal catch-up until one read succeeds, then stops", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      window.history.replaceState({}, "", "/tasks/task-running");
      const fetch = mockControlPlane({ terminalTaskAfter: 1, terminalEventFailures: 1 });
      const { client } = renderApp();
      expect(await screen.findByText("Progress before completion")).toBeVisible();

      await client.refetchQueries({ queryKey: ["task", "task-running"] });
      await vi.waitFor(() => {
        const eventCalls = fetch.mock.calls.filter(([input]) => {
          const path = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
          return path.includes("/events?");
        });
        expect(eventCalls).toHaveLength(2);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2_000);
      });
      expect(screen.getByText("Final terminal progress")).toBeVisible();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(6_000);
      });
      const eventPaths = fetch.mock.calls
        .map(([input]) => typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url)
        .filter((path) => path.includes("/events?"));
      expect(eventPaths).toEqual([
        "/api/v1/attempts/attempt-running/events?after=-1&limit=100",
        "/api/v1/attempts/attempt-running/events?after=0&limit=100",
        "/api/v1/attempts/attempt-running/events?after=0&limit=100",
      ]);
    } finally {
      vi.useRealTimers();
    }
  });
});
