import {
  expect,
  request,
  test,
  type APIRequestContext,
  type Locator,
  type Page,
} from "@playwright/test";
import { testWorkerBootstrapCredential } from "../playwright.config";

test.describe.configure({ mode: "serial" });
test.setTimeout(120_000);

const workerOnline = "worker-online-e2e";
const workerOffline = "worker-offline-e2e";
const managedWorker = "worker-managed-e2e";
const automationWorker = "worker-automation-e2e";
const realWorker = "11111111-1111-4111-8111-111111111111";
const onlineRepositories = [
  { key: "factory", remote_identity: "github.com/example/factory", retained_count: 1 },
  { key: "handbook", remote_identity: "github.com/example/handbook", retained_count: 0 },
];
const offlineRepositories = [
  { key: "archive", remote_identity: "github.com/example/archive", retained_count: 0 },
];
const identifiers: Record<string, string> = {};
const workerCredentials: Record<string, string> = {};
let fixtureAPI: APIRequestContext | undefined;
let runningHeartbeat: ReturnType<typeof setInterval> | undefined;

interface TaskDetail {
  task: { id: string; title: string; description?: string; state?: string };
  context?: string;
  execution: { id: string; assigned_worker_id: string };
  repository: { id: string };
  attempts: Array<{ id: string; state?: string; result?: string; error?: string }>;
  workflow?: { id: string; revision_id: string; name: string; revision_number: number };
  resolved_prompt?: string;
}

async function json<T>(response: Awaited<ReturnType<APIRequestContext["get"]>>): Promise<T> {
  if (!response.ok()) {
    throw new Error(`API ${response.status()}: ${await response.text()}`);
  }
  return response.json() as Promise<T>;
}

async function registerWorker(
  api: APIRequestContext,
  id: string,
  name: string,
  repositories: typeof onlineRepositories,
  activeCount = 0,
  disposedAttemptIDs: string[] = [],
  runtime: "codex" | "claude-code" = "codex",
  sourceAccess: Array<{ provider: "github"; hostname: string }> = [],
) {
  const response = await api.put(`/api/v1/workers/${id}`, {
    headers: {
      "X-Factory-Worker-Bootstrap-Credential": testWorkerBootstrapCredential,
    },
    data: {
      name,
      worker_version: "2.0.0-test",
      runtime,
      runtime_version: runtime === "claude-code" ? "2.1.220-test" : "0.42.0-test",
      capacity: 2,
      active_count: activeCount,
      health: "healthy",
      source_access: sourceAccess,
      capacity_handoff_version: 1,
      disposed_attempt_ids: disposedAttemptIDs,
      repositories,
      retained_worktrees:
        id === workerOnline
          ? [
              {
                attempt_id: "attempt-retained-001",
                repository_id: identifiers.factoryRepository ?? "",
                path: "/tmp/factory-e2e/worktrees/attempt-retained-001",
                reason: "failed with local changes",
                cleanup_command: "factory-worker cleanup attempt-retained-001 --confirm",
              },
            ]
          : [],
    },
  });
  const credential = response.headers()["x-factory-worker-credential"];
  if (response.ok() && !credential) {
    throw new Error(`worker ${id} registration did not return a credential`);
  }
  if (credential) workerCredentials[id] = credential;
  return json<{
    repositories: Array<{ id: string; key: string }>;
  }>(response);
}

async function createTask(
  api: APIRequestContext,
  key: string,
  title: string,
  workerID: string,
  repositoryID: string,
  description = "A representative task created through the real control-plane API.",
) {
  return json<TaskDetail>(
    await api.post("/api/v1/tasks", {
      data: {
        request_key: key,
        title,
        description,
        worker_id: workerID,
        repository_id: repositoryID,
        timeout_seconds: 7200,
      },
    }),
  );
}

async function claimAndStart(api: APIRequestContext, requestID: string) {
  const token = `lease-token-${requestID}-0123456789abcdef0123456789`;
  const claim = await json<{
    attempt: { id: string };
    execution: { id: string };
    task: { id: string };
  }>(
    await api.post(`/api/v1/workers/${workerOnline}/claims`, {
      headers: {
        "X-Factory-Worker-Credential": workerCredentials[workerOnline],
      },
      data: { request_id: requestID, lease_token: token },
    }),
  );
  await json(
    await api.post(`/api/v1/attempts/${claim.attempt.id}/start`, {
      data: { lease_token: token, process_identity: `e2e-${requestID}` },
    }),
  );
  return { ...claim, token };
}

async function complete(
  api: APIRequestContext,
  requestID: string,
  state: "succeeded" | "failed",
  result: string,
) {
  const claim = await claimAndStart(api, requestID);
  await json(
    await api.post(`/api/v1/attempts/${claim.attempt.id}/complete`, {
      data: {
        lease_token: claim.token,
        state,
        ...(state === "succeeded" ? { result } : { error: result }),
      },
    }),
  );
  return claim;
}

async function waitForRealWorker(api: APIRequestContext) {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    const response = await api.get("/api/v1/workers");
    if (response.ok()) {
      const body = (await response.json()) as {
        workers: Array<{
          id: string;
          health: string;
          online: boolean;
          repositories: Array<{ id: string; key: string }>;
        }> | null;
      };
      const worker = body.workers?.find((candidate) => candidate.id === realWorker);
      if (worker?.online && worker.health === "healthy") return worker;
    }
    await new Promise((resolveWait) => setTimeout(resolveWait, 500));
  }
  throw new Error("real Factory worker did not register as healthy within 30 seconds");
}

function observeBrowser(page: Page) {
  const problems: string[] = [];
  const realtime: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") problems.push(`console: ${message.text()}`);
  });
  page.on("requestfailed", (failed) => {
    problems.push(`request: ${failed.url()} ${failed.failure()?.errorText ?? "failed"}`);
  });
  page.on("websocket", (socket) => realtime.push(`websocket: ${socket.url()}`));
  page.on("response", (response) => {
    if (response.headers()["content-type"]?.includes("text/event-stream")) {
      realtime.push(`event-stream: ${response.url()}`);
    }
  });
  return {
    assertClean() {
      expect(problems, "browser console and network failures").toEqual([]);
      expect(realtime, "the UI must use HTTP polling only").toEqual([]);
    },
  };
}

type AuditScreen = {
  name: string;
  path: string;
  ready: (page: Page) => Locator;
};

type AuditedLayout = {
  documentFits: boolean;
  documentWidth: number;
  mainFits: boolean;
  actionOverlaps: string[];
  horizontalOffenders: Array<{ element: string; left: number; right: number }>;
  overflowElements: Array<{ element: string; left: number; right: number }>;
  interactiveOffenders: Array<{ element: string; reason: string }>;
  horizontalScrollerOffenders: Array<{ element: string; left: number; right: number }>;
  sidebar: { left: number; right: number } | null;
  mainShell: { left: number; right: number } | null;
  topbar: { left: number; right: number } | null;
  viewportWidth: number;
};

async function readAuditedLayout(page: Page) {
  return page.evaluate<AuditedLayout>(`(() => {
    const visible = (element) => {
      const style = window.getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
    };
    const viewportWidth = document.documentElement.clientWidth;
    const horizontalScrollerFor = (element) => {
      let parent = element.parentElement;
      while (parent && parent !== document.body) {
        const style = window.getComputedStyle(parent);
        if (["auto", "scroll"].includes(style.overflowX) && parent.scrollWidth > parent.clientWidth) {
          return parent;
        }
        parent = parent.parentElement;
      }
      return null;
    };
    const horizontalOffenders = Array.from(
      document.querySelectorAll(".topbar, main, main .button, main button, main input, main select, main textarea, .modal"),
    )
      .filter((element) => visible(element) && !horizontalScrollerFor(element))
      .map((element) => {
        const rect = element.getBoundingClientRect();
        return {
          element: element.tagName.toLowerCase() + "." + String(element.className).trim().split(" ").join("."),
          left: Math.round(rect.left),
          right: Math.round(rect.right),
        };
      })
      .filter(({ left, right }) => left < -1 || right > viewportWidth + 1);
    const horizontalScrollerOffenders = Array.from(document.querySelectorAll("*"))
      .filter((element) => {
        const style = window.getComputedStyle(element);
        return visible(element)
          && ["auto", "scroll"].includes(style.overflowX)
          && element.scrollWidth > element.clientWidth;
      })
      .map((element) => {
        const bounds = element.getBoundingClientRect();
        return {
          element: element.tagName.toLowerCase() + "." + String(element.className).trim().split(" ").join("."),
          left: Math.round(bounds.left),
          right: Math.round(bounds.right),
        };
      })
      .filter(({ left, right }) => left < -1 || right > viewportWidth + 1);
    const rect = (selector) => {
      const bounds = document.querySelector(selector)?.getBoundingClientRect();
      return bounds ? { left: bounds.left, right: bounds.right } : null;
    };
    const main = document.querySelector("main");
    const contentControls = Array.from(document.querySelectorAll("main input, main select, main textarea, main button"))
      .filter(visible);
    const actionOverlaps = Array.from(document.querySelectorAll("main *"))
      .filter((element) => visible(element) && ["fixed", "sticky"].includes(window.getComputedStyle(element).position))
      .flatMap((floating) => {
        const floatingBounds = floating.getBoundingClientRect();
        return contentControls
          .filter((control) => !floating.contains(control))
          .filter((control) => {
            const bounds = control.getBoundingClientRect();
            return floatingBounds.left < bounds.right && floatingBounds.right > bounds.left
              && floatingBounds.top < bounds.bottom && floatingBounds.bottom > bounds.top;
          })
          .map((control) => floating.className + " overlaps " + control.tagName.toLowerCase());
      });
    const auditedElements = Array.from(document.querySelectorAll(".topbar, .topbar *, main, main *, .modal, .modal *"));
    const overflowElements = auditedElements
      .filter((element) => visible(element) && !horizontalScrollerFor(element))
      .map((element) => {
        const bounds = element.getBoundingClientRect();
        return {
          element: element.tagName.toLowerCase() + "." + String(element.className).trim().split(" ").join("."),
          left: Math.round(bounds.left),
          right: Math.round(bounds.right),
        };
      })
      .filter(({ left, right }) => left < -1 || right > viewportWidth + 1);
    const interactiveOffenders = Array.from(document.querySelectorAll(
      ".topbar button, .topbar a[href], main button, main input, main select, main textarea, main a[href], main [role=button], .modal button, .modal input, .modal select, .modal textarea, .modal a[href], .modal [role=button]",
    ))
      .filter(visible)
      .filter((element) => !horizontalScrollerFor(element))
      .flatMap((element) => {
        const bounds = element.getBoundingClientRect();
        const name = element.tagName.toLowerCase() + "." + String(element.className).trim().split(" ").join(".");
        if (bounds.left < -1 || bounds.right > viewportWidth + 1) {
          return [{ element: name, reason: "outside viewport" }];
        }
        let parent = element.parentElement;
        while (parent && parent !== document.body) {
          const style = window.getComputedStyle(parent);
          if (["hidden", "clip"].includes(style.overflowX)) {
            const parentBounds = parent.getBoundingClientRect();
            if (bounds.left < parentBounds.left - 1 || bounds.right > parentBounds.right + 1) {
              const parentName = parent.tagName.toLowerCase() + "." + String(parent.className).trim().split(" ").join(".");
              return [{ element: name, reason: "clipped by " + parentName }];
            }
          }
          parent = parent.parentElement;
        }
        return [];
      });
    return {
      documentFits: document.documentElement.scrollWidth <= viewportWidth + 1,
      documentWidth: document.documentElement.scrollWidth,
      mainFits: Boolean(main && main.scrollWidth <= main.clientWidth + 1),
      actionOverlaps,
      horizontalOffenders,
      overflowElements,
      interactiveOffenders,
      horizontalScrollerOffenders,
      sidebar: rect(".sidebar"),
      mainShell: rect(".main-shell"),
      topbar: rect(".topbar"),
      viewportWidth,
    };
  })()`);
}

async function expectAuditedLayout(page: Page, desktop: boolean) {
  const layout = await readAuditedLayout(page);
  expect(layout.documentFits, `the document must not scroll horizontally: ${JSON.stringify(layout)}`).toBe(true);
  expect(layout.mainFits, "main content must not scroll horizontally").toBe(true);
  expect(layout.actionOverlaps, "sticky actions must not cover form controls").toEqual([]);
  expect(layout.horizontalOffenders, "controls and shell must stay inside the viewport").toEqual([]);
  expect(layout.overflowElements, "audited content must stay inside the viewport").toEqual([]);
  expect(layout.interactiveOffenders, "interactive elements must not be outside or clipped").toEqual([]);
  expect(layout.horizontalScrollerOffenders, "horizontal scrollers must stay inside the viewport").toEqual([]);
  expect(layout.topbar?.left ?? -1).toBeGreaterThanOrEqual(0);
  expect(layout.topbar?.right ?? Infinity).toBeLessThanOrEqual(layout.viewportWidth + 1);
  if (desktop) {
    expect(layout.sidebar?.right ?? Infinity).toBeLessThanOrEqual((layout.mainShell?.left ?? 0) + 1);
  } else {
    expect(layout.mainShell?.left ?? -1).toBe(0);
  }
}

async function expectInteractiveOverflowRegression(page: Page) {
  await page.evaluate(`(() => {
    const clippingFixture = document.createElement("div");
    clippingFixture.className = "visual-audit-clipping-fixture";
    clippingFixture.style.cssText = "width: 4px; overflow-x: hidden";
    const clippedButton = document.createElement("button");
    clippedButton.className = "visual-audit-clipped-native-button";
    clippedButton.style.width = "80px";
    clippedButton.textContent = "clipped audit fixture";
    clippingFixture.append(clippedButton);

    const outsideButton = document.createElement("button");
    outsideButton.className = "visual-audit-outside-native-button";
    outsideButton.style.cssText = "position: fixed; left: calc(100vw + 10px); width: 80px";
    outsideButton.textContent = "outside audit fixture";
    document.querySelector("main").append(clippingFixture, outsideButton);
  })()`);

  const layout = await readAuditedLayout(page);
  expect(layout.interactiveOffenders, "native main buttons must be checked for clipping").toContainEqual({
    element: "button.visual-audit-clipped-native-button",
    reason: "clipped by div.visual-audit-clipping-fixture",
  });
  expect(layout.interactiveOffenders, "native main buttons must be checked against the viewport").toContainEqual({
    element: "button.visual-audit-outside-native-button",
    reason: "outside viewport",
  });
  expect(layout.overflowElements.map(({ element }) => element), "overflow findings must be retained for assertions")
    .toContain("button.visual-audit-outside-native-button");

  await page.evaluate(`document.querySelector(".visual-audit-clipping-fixture").remove();
    document.querySelector(".visual-audit-outside-native-button").remove()`);
}

async function exerciseMobileNavigation(page: Page) {
  const toggle = page.getByRole("button", { name: "Открыть навигацию" });
  const sidebar = page.locator(".sidebar");
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(sidebar).toBeInViewport();
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(toggle).toBeFocused();
  await expect(sidebar).not.toBeInViewport();

  await toggle.click();
  const scrim = page.getByRole("button", { name: "Закрыть навигацию" });
  await expect(scrim).toBeVisible();
  await scrim.click({ position: { x: 380, y: 100 } });
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(sidebar).not.toBeInViewport();
  await expect(page.locator("main")).toBeVisible();
}

test.beforeAll(async ({ baseURL }) => {
  const api = await request.newContext({ baseURL: baseURL });
  fixtureAPI = api;
  const real = await waitForRealWorker(api);
  identifiers.realFactoryRepository = real.repositories.find(
    (repository) => repository.key === "factory-demo",
  )!.id;
  identifiers.realHandbookRepository = real.repositories.find(
    (repository) => repository.key === "handbook-demo",
  )!.id;

  const offline = await registerWorker(
    api,
    workerOffline,
    "Archive Mac",
    offlineRepositories,
    0,
    [],
    "claude-code",
  );
  identifiers.offlineRepository = offline.repositories[0].id;

  // Registrations become offline after the server's documented 30 second window.
  await new Promise((resolveWait) => setTimeout(resolveWait, 31_000));

  const online = await registerWorker(api, workerOnline, "Build Mac", onlineRepositories);
  identifiers.factoryRepository = online.repositories.find((repo) => repo.key === "factory")!.id;
  identifiers.handbookRepository = online.repositories.find((repo) => repo.key === "handbook")!.id;
  const automation = await registerWorker(
    api,
    automationWorker,
    "Automation fixture",
    [
      {
        key: "automation-fixture",
        remote_identity: "github.com/example/automation-fixture",
        retained_count: 0,
      },
    ],
    0,
    [],
    "codex",
    [{ provider: "github", hostname: "github.com" }],
  );
  const managedAutomationRepository = await json<{ id: string }>(
    await api.post("/api/v1/repositories", {
      data: { remote_identity: "github.com/example/automation-fixture" },
    }),
  );
  expect(managedAutomationRepository.id).toBe(automation.repositories[0].id);
  identifiers.automationRepository = managedAutomationRepository.id;

  const queued = await createTask(
    api,
    "e2e-queued",
    "Queued for the offline archive worker",
    workerOffline,
    identifiers.offlineRepository,
  );
  identifiers.queuedTask = queued.task.id;

  const cancelled = await createTask(
    api,
    "e2e-cancelled",
    "Cancelled queue cleanup",
    workerOffline,
    identifiers.offlineRepository,
  );
  await json(await api.post(`/api/v1/tasks/${cancelled.task.id}/cancel`, { data: {} }));

  const succeeded = await createTask(
    api,
    "e2e-succeeded",
    "Ship the stable API client",
    workerOnline,
    identifiers.factoryRepository,
  );
  const succeededAttempt = await complete(
    api,
    "claim-succeeded",
    "succeeded",
    "API client shipped with all checks passing.",
  );
  identifiers.succeededTask = succeeded.task.id;

  const failed = await createTask(
    api,
    "e2e-failed",
    "Repair a failed release check",
    workerOnline,
    identifiers.factoryRepository,
  );
  const failedAttempt = await complete(
    api,
    "claim-failed",
    "failed",
    "The release check found a deterministic failure.",
  );
  identifiers.failedTask = failed.task.id;

  const longTitle = `Long operational title ${"with bounded content ".repeat(8)}`.slice(0, 200);
  const longTask = await createTask(
    api,
    "e2e-long",
    longTitle,
    workerOffline,
    identifiers.offlineRepository,
    `${"Long descriptions remain readable and do not escape their surface. ".repeat(80)}\nEnd of description.`,
  );
  identifiers.longTask = longTask.task.id;

  const running = await createTask(
    api,
    "e2e-running",
    "Implement the modern control-plane UI",
    workerOnline,
    identifiers.factoryRepository,
    "Build the complete browser interface, verify it against the real server, and preserve unrelated state.",
  );
  const active = await claimAndStart(api, "claim-running");
  await api.post(`/api/v1/attempts/${active.attempt.id}/events`, {
    data: {
      lease_token: active.token,
      events: [
        {
          sequence: 0,
          kind: "codex",
          payload: {
            type: "item.completed",
            item: { type: "agent_message", text: "Inspected the control-plane contract." },
          },
        },
        {
          sequence: 1,
          kind: "codex",
          payload: {
            type: "item.completed",
            item: {
              type: "command_execution",
              command: "npm test",
              aggregated_output: "RAW_COMMAND_OUTPUT_SHOULD_NOT_RENDER",
              exit_code: 0,
            },
          },
        },
        { sequence: 2, kind: "codex", payload: { type: "thread.started", thread_id: "thread-e2e" } },
        { sequence: 3, kind: "check", payload: { summary: "Running browser verification." } },
      ],
    },
  });
  identifiers.runningTask = running.task.id;
  identifiers.runningAttempt = active.attempt.id;
  identifiers.runningLeaseToken = active.token;
  runningHeartbeat = setInterval(() => {
    void api.put(`/api/v1/attempts/${active.attempt.id}/heartbeat`, {
      data: { lease_token: active.token },
    });
  }, 5_000);

  await registerWorker(
    api,
    workerOnline,
    "Build Mac",
    onlineRepositories,
    1,
    [succeededAttempt.attempt.id, failedAttempt.attempt.id],
  );
});

test.afterAll(async () => {
  if (runningHeartbeat) clearInterval(runningHeartbeat);
  await fixtureAPI?.dispose();
});

test("shows every project product and saves the overview", async ({ page, baseURL }) => {
  const browser = observeBrowser(page);
  const api = await request.newContext({ baseURL: baseURL });
  const dashboard = await json<{
    projects: Array<{ name: string }>;
  }>(await api.get("/api/v1/dashboard"));
  await api.dispose();

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Обзор", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Обзор", exact: true })).toHaveAttribute(
    "aria-current",
    "page",
  );
  const products = page.getByRole("region", { name: /Продукт —/ });
  await expect(products).toHaveCount(dashboard.projects.length);
  await expect(products.locator("strong").filter({ hasText: /^Продукт —/ })).toHaveText(
    dashboard.projects.map((project) => `Продукт — ${project.name}`),
  );
  const factoryProduct = page.getByRole("region", { name: "Продукт — factory-demo" });
  await expect(factoryProduct).toContainText("Show every project product on the overview");
  await expect(factoryProduct).toContainText("Production");
  await expect(factoryProduct).toContainText("factory-e2e-release");
  await expect(factoryProduct).toContainText("отвечает");
  const handbookProduct = page.getByRole("region", { name: "Продукт — handbook-demo" });
  await expect(handbookProduct).toContainText("Document the product overview");
  await expect(handbookProduct).toContainText("Стенд не настроен");
  await page.screenshot({ path: "test-results/screenshots/overview-desktop.png", fullPage: true });
  browser.assertClean();
});

test("shows project readiness card", async ({ page }) => {
  const browser = observeBrowser(page);
  const checks = [
    ["repository", "Репозиторий"], ["workers", "Исполнители"],
    ["safe_environment", "Безопасный стенд"], ["access", "Доступы"],
    ["tests", "Тесты"], ["release", "Выпуск"], ["rollback", "Откат"],
    ["secrets", "Секреты"], ["browser", "Браузерный доступ"],
  ].map(([key, title]) => ({ key, title, state: "ready", reason: `${title} подтверждено` }));
  await page.route("**/api/v1/dashboard", async (route) => {
    const response = await route.fetch();
    const dashboard = await response.json();
    dashboard.projects[0].readiness = {
      verdict: "ready", checked_at: "2026-08-10T12:00:00Z", checks,
    };
    dashboard.projects[1].readiness = {
      verdict: "ready", checked_at: "2026-08-10T12:00:00Z",
      checks: checks.map((check) => check.key === "safe_environment"
        ? { ...check, state: "unknown", reason: "Для Factory отдельный безопасный стенд не выбран." }
        : check),
    };
    await route.fulfill({ response, json: dashboard });
  });

  await page.goto("/");
  const factory = page.getByRole("region", { name: "Продукт — factory-demo" });
  await expect(factory.getByLabel("Готовность проекта")).toContainText("Готов");
  await expect(factory.getByLabel("Готовность проекта").locator("strong")).toHaveCount(10);
  const handbook = page.getByRole("region", { name: "Продукт — handbook-demo" });
  await expect(handbook.getByLabel("Готовность проекта")).toContainText("Требует настройки");
  await expect(handbook.getByLabel("Готовность проекта")).toContainText(
    "Для Factory отдельный безопасный стенд не выбран.",
  );
  await page.screenshot({ path: "test-results/screenshots/project-readiness-card.png", fullPage: true });
  browser.assertClean();
});

test("creates, pins, revises, and disables a reusable Workflow", async ({ page, baseURL }) => {
  const browser = observeBrowser(page);
  await page.goto("/workflows");
  await expect(page.getByRole("heading", { name: "Сценарии", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Создать сценарий" }).first().click();
  const create = page.getByRole("dialog", { name: "Создать сценарий" });
  await create.getByLabel("Название").fill("E2E pinned review");
  await create.getByLabel("Описание").fill("Prove immutable prompt snapshots.");
  const instructions = create.getByLabel("Инструкции Markdown");
  await instructions.fill("Use revision one instructions exactly.");
  await Promise.all([
    page.waitForResponse((response) => response.url().includes("/api/v1/workflows?") && response.ok()),
    page.evaluate("document.dispatchEvent(new Event('visibilitychange'))"),
  ]);
  await expect(instructions).toBeFocused();
  await create.getByRole("button", { name: "Создать сценарий" }).click();
  await expect(page.getByRole("heading", { name: "E2E pinned review" })).toBeVisible();
  const workflowURL = page.url();

  await page.getByRole("button", { name: "Поставить задачу" }).click();
  const delegate = page.getByRole("dialog", { name: "Поставить задачу" });
  await delegate.getByLabel("Сценарий").selectOption({ label: "E2E pinned review · версия 1" });
  await delegate.getByLabel("Название").fill("Pinned Workflow browser task");
  await delegate.getByLabel("Контекст").fill("JIRA-183 stays free text.");
  await delegate.getByLabel("Исполнитель").selectOption(workerOffline);
  await delegate.getByLabel("Репозиторий").selectOption(identifiers.offlineRepository);
  await delegate.getByRole("button", { name: "Поставить задачу" }).click();
  await expect(page.getByRole("heading", { name: "Pinned Workflow browser task" })).toBeVisible();
  await page.locator("details").filter({ hasText: "Задание агенту" }).locator("summary").click();
  await expect(page.getByText("JIRA-183 stays free text.", { exact: true })).toBeVisible();
  await page.locator("details").filter({ hasText: "Полный промпт" }).locator("summary").click();
  await expect(page.getByText(/Use revision one instructions exactly/)).toBeVisible();
  const taskID = new URL(page.url()).pathname.split("/").at(-1)!;

  await page.goto(workflowURL);
  await page.getByRole("button", { name: "Новая редакция" }).click();
  const revise = page.getByRole("dialog", { name: "Создать редакцию" });
  await revise.getByLabel("Инструкции Markdown").fill("Use revision two instructions instead.");
  await revise.getByRole("button", { name: "Создать редакцию" }).click();
  await expect(page.getByText("Редакция 2", { exact: true }).first()).toBeVisible();

  const api = await request.newContext({ baseURL: baseURL });
  const pinned = await json<TaskDetail>(await api.get(`/api/v1/tasks/${taskID}`));
  expect(pinned.context).toBe("JIRA-183 stays free text.");
  expect(pinned.task.description).toBe(pinned.resolved_prompt);
  expect(pinned.workflow?.revision_number).toBe(1);
  expect(pinned.resolved_prompt).toContain("Use revision one instructions exactly.");
  expect(pinned.resolved_prompt).not.toContain("Use revision two instructions instead.");
  await api.dispose();

  await page.getByRole("button", { name: "Выключить" }).click();
  await page.getByRole("button", { name: "Подтвердить: выключить" }).click();
  await expect(page.getByRole("button", { name: "Включить", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Поставить задачу" }).click();
  await expect(page.getByRole("dialog").getByLabel("Сценарий").getByRole("option", { name: /E2E pinned review/ })).toHaveCount(0);
  await page.keyboard.press("Escape");
  browser.assertClean();
});

test("runs the complete UI to real-worker and Git-worktree workflow", async ({ page, baseURL }) => {
  const browser = observeBrowser(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Поставить задачу" }).first().click();
  const dialog = page.getByRole("dialog", { name: "Поставить задачу" });
  await dialog.getByLabel("Исполнитель").selectOption(realWorker);
  await expect(
    dialog.getByLabel("Репозиторий").getByRole("option", { name: /factory-demo/ }),
  ).toHaveCount(1);
  await expect(
    dialog.getByLabel("Репозиторий").getByRole("option", { name: /handbook-demo/ }),
  ).toHaveCount(1);
  await dialog.getByLabel("Название").fill("Prove the complete local workflow");
  await dialog
    .getByLabel("Контекст")
    .fill("Create deterministic evidence in the assigned real Git worktree.");
  await dialog.getByLabel("Репозиторий").selectOption(identifiers.realFactoryRepository);
  await page.screenshot({
    path: "test-results/screenshots/delegate-desktop.png",
    fullPage: true,
  });
  await dialog.getByRole("button", { name: "Поставить задачу" }).click();

  await expect(page.getByRole("heading", { name: "Prove the complete local workflow" })).toBeVisible();
  await expect(page.getByText("Успешно", { exact: true }).first()).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByText("Created deterministic worktree evidence.")).toBeVisible();
  const technicalReport = page.locator(".attempt-output.success-output");
  await expect(technicalReport).toContainText("Completed by deterministic fake Codex.");
  await expect(technicalReport).toContainText(/Branch: factory\//);
  await expect(technicalReport).toContainText(/Worktree: .*factory-ui-e2e-.*\/worker\/worktrees\//);
  await page.screenshot({
    path: "test-results/screenshots/task-detail-desktop.png",
    fullPage: true,
  });

  const taskID = new URL(page.url()).pathname.split("/").at(-1)!;
  await page.reload();
  await expect(page.getByRole("heading", { name: "Prove the complete local workflow" })).toBeVisible();

  const api = await request.newContext({ baseURL: baseURL });
  const detail = await json<TaskDetail>(await api.get(`/api/v1/tasks/${taskID}`));
  expect(detail.task.state).toBe("succeeded");
  expect(detail.attempts).toHaveLength(1);
  expect(detail.attempts[0].result).toContain("Branch: factory/");
  const worker = await json<{
    retained_worktrees: Array<{ attempt_id: string; path: string; cleanup_command: string }>;
  }>(await api.get(`/api/v1/workers/${realWorker}`));
  const retained = worker.retained_worktrees.find(
    (worktree) => worktree.attempt_id === detail.attempts[0].id,
  );
  expect(retained?.path).toContain("/worker/worktrees/");
  expect(retained?.cleanup_command).toContain(`factory-worker cleanup ${detail.attempts[0].id}`);
  await api.dispose();
  browser.assertClean();
});

test("cancels active work running in the real worker", async ({ page }) => {
  const browser = observeBrowser(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Поставить задачу" }).first().click();
  const dialog = page.getByRole("dialog", { name: "Поставить задачу" });
  await dialog.getByLabel("Исполнитель").selectOption(realWorker);
  await dialog.getByLabel("Название").fill("Cancel a real active Codex process");
  await dialog
    .getByLabel("Контекст")
    .fill("FACTORY_E2E_WAIT until the operator cancels this task.");
  await dialog.getByLabel("Репозиторий").selectOption(identifiers.realHandbookRepository);
  await dialog.getByRole("button", { name: "Поставить задачу" }).click();

  await expect(page.getByText("В работе", { exact: true }).first()).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByText("Waiting for operator cancellation.")).toBeVisible();
  await page.getByRole("button", { name: "Отменить" }).click();
  await page.getByRole("button", { name: "Подтвердить отмену" }).click();
  await expect(page.getByText("Отменено", { exact: true }).first()).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.locator(".attempt-output.error-output")).toContainText("attempt cancelled");
  browser.assertClean();
});

test("renders grouped work and saves the desktop Work view", async ({ page }) => {
  const browser = observeBrowser(page);
  await page.goto("/work");
  await expect(page.getByRole("heading", { name: "Работа агентов" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Работы", exact: true })).toHaveAttribute(
    "aria-current",
    "page",
  );
  await expect(page.getByRole("heading", { name: "В работе" })).toBeVisible();
  await expect(page.getByText("Не вышло / остановлено")).toHaveCount(0);
  const doneSection = page.getByRole("heading", { name: "Сделано" }).locator("..").locator("..");
  await expect(doneSection.getByText("Ship the stable API client", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /Архив/ }).click();
  await expect(page.getByText("Ship the stable API client", { exact: true })).toBeVisible();
  await expect(page.getByText("Cancelled queue cleanup", { exact: true })).toBeVisible();
  await expect(page.getByText("Long operational title", { exact: false })).toBeVisible();
  await page.screenshot({ path: "test-results/screenshots/work-desktop.png", fullPage: true });
  browser.assertClean();
});

test("confirms and deletes terminal task history", async ({ page, baseURL }) => {
  const browser = observeBrowser(page);
  await page.goto(`/tasks/${identifiers.succeededTask}`);
  await expect(page.getByRole("heading", { name: "Ship the stable API client" })).toBeVisible();
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: "Удалить историю" }).click();
  await expect(page.getByText(/Удалить задачу, промпт, попытки и события/)).toBeVisible();
  await page.getByRole("button", { name: "Подтвердить удаление" }).click();
  await expect(page).toHaveURL("/work");
  await expect(page.getByText("Ship the stable API client")).toHaveCount(0);
  browser.assertClean();

  const api = await request.newContext({ baseURL: baseURL });
  const response = await api.get(`/api/v1/tasks/${identifiers.succeededTask}`);
  expect(response.status()).toBe(404);
  await api.dispose();
});

test("shows worker capacity, current work, retained cleanup, and saves Workers", async ({ page, baseURL }) => {
  const browser = observeBrowser(page);
  if (runningHeartbeat) clearInterval(runningHeartbeat);
  const heartbeat = await fixtureAPI!.put(
    `/api/v1/attempts/${identifiers.runningAttempt}/heartbeat`,
    { data: { lease_token: identifiers.runningLeaseToken } },
  );
  expect(heartbeat.ok()).toBe(true);
  await fixtureAPI!.dispose();
  fixtureAPI = undefined;
  const api = await request.newContext({ baseURL: baseURL });
  await registerWorker(
    api,
    workerOnline,
    "Build Mac",
    onlineRepositories,
    1,
  );
  await api.dispose();
  await page.goto("/workers");
  await expect(page.getByRole("heading", { name: "Исполнители" })).toBeVisible();
  const workersNavigation = page.getByRole("button", { name: "Исполнители", exact: true });
  await expect(workersNavigation).toHaveAttribute("aria-current", "page");
  await expect(page.getByText("Implement the modern control-plane UI")).toBeVisible();
  const offlineRow = page.getByRole("button", { name: /Archive Mac/ });
  await expect(offlineRow).toBeVisible();
  await expect(offlineRow).toContainText("Не в сети");
  await expect(offlineRow).toContainText("Claude Code");
  await page.screenshot({ path: "test-results/screenshots/workers-desktop.png", fullPage: true });

  await page.getByRole("button", { name: /Build Mac/ }).click();
  await expect(page.getByRole("heading", { name: "Build Mac" })).toBeVisible();
  await expect(workersNavigation).toHaveClass(/active/);
  await expect(workersNavigation).not.toHaveAttribute("aria-current");
  const profileTabs = page.getByRole("tablist", { name: "Профиль исполнителя" });
  await expect(profileTabs.getByRole("tab", { name: "Обзор" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("region", { name: "Сводка исполнителя" })).toBeVisible();

  await profileTabs.getByRole("tab", { name: "Работа" }).click();
  await expect(page.getByText("factory-worker cleanup attempt-retained-001 --confirm")).toBeVisible();

  await profileTabs.getByRole("tab", { name: "Возможности" }).click();
  await expect(page.getByRole("tabpanel")).toContainText("0.42.0-test");
  await expect(page.getByRole("tabpanel")).toContainText("github.com/example/factory");

  await profileTabs.getByRole("tab", { name: "Настройки" }).click();
  await expect(page.getByRole("heading", { name: "Исполнение" })).toBeVisible();
  await expect(page.getByText("Только чтение")).toBeVisible();
  await expect(page.getByRole("meter", { name: "Параллельность исполнителя" })).toHaveAttribute("max", "2");
  await expect(page.getByRole("tabpanel")).toContainText("Обнови файл и перезапусти исполнителя");
  const assign = page.getByRole("button", { name: "Назначить работу" });
  await assign.click();
  await expect(page.getByRole("dialog").getByLabel("Исполнитель")).toHaveValue(workerOnline);
  await page.keyboard.press("Escape");
  await expect(assign).toBeFocused();
  browser.assertClean();
});

test("delegates with worker-specific repositories and preserves the task on refresh", async ({ page }) => {
  const browser = observeBrowser(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Поставить задачу" }).first().click();
  const dialog = page.getByRole("dialog", { name: "Поставить задачу" });
  await dialog.getByLabel("Исполнитель").selectOption(workerOffline);
  await expect(dialog.getByText("Исполнитель не в сети. Задача будет ждать в очереди до его возвращения.")).toBeVisible();
  await expect(dialog.getByText("Это станет промптом для Claude Code.")).toBeVisible();
  await expect(dialog.getByLabel("Репозиторий").getByRole("option", { name: /archive/ })).toHaveCount(1);
  await expect(dialog.getByLabel("Репозиторий").locator(`option[value="${identifiers.factoryRepository}"]`)).toBeDisabled();
  await dialog.getByLabel("Название").fill("Durable delegated browser task");
  await dialog.getByLabel("Контекст").fill("Created in the real UI and stored by the real Go server.");
  await dialog.getByLabel("Репозиторий").selectOption(identifiers.offlineRepository);
  await dialog.getByRole("button", { name: "Поставить задачу" }).click();
  await expect(page.getByRole("heading", { name: "Durable delegated browser task" })).toBeVisible();
  await expect(page.getByText("Claude Code", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Durable delegated browser task" })).toBeVisible();
  browser.assertClean();
});

test("confirms queued cancellation and explicitly retries a failure", async ({ page }) => {
  const browser = observeBrowser(page);
  await page.goto(`/tasks/${identifiers.queuedTask}`);
  await page.getByRole("button", { name: "Отменить" }).click();
  await expect(page.getByText("Отменить эту задачу?")).toBeVisible();
  await page.getByRole("button", { name: "Подтвердить отмену" }).click();
  await expect(page.getByText("Отменено", { exact: true }).first()).toBeVisible();

  await page.goto(`/tasks/${identifiers.failedTask}`);
  await page.getByRole("button", { name: "Повторить задачу" }).click();
  await expect(page.getByText("В очереди", { exact: true }).first()).toBeVisible();
  browser.assertClean();
});

test("shows ordered progress and long task detail", async ({ page }) => {
  const browser = observeBrowser(page);
  const eventAfters: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname === `/api/v1/attempts/${identifiers.runningAttempt}/events`) {
      eventAfters.push(url.searchParams.get("after") ?? "");
    }
  });
  await page.goto(`/tasks/${identifiers.runningTask}`);
  const workNavigation = page.getByRole("button", { name: "Работы", exact: true });
  await expect(workNavigation).toHaveClass(/active/);
  await expect(workNavigation).not.toHaveAttribute("aria-current");
  const events = page.locator(".event-list li");
  await expect(events).toHaveCount(3);
  await expect(events.nth(0)).toContainText("Inspected the control-plane contract.");
  await expect(events.nth(1)).toContainText("Успешно: npm test");
  await expect(events.nth(2)).toContainText("Running browser verification.");
  await expect(page.getByText("RAW_COMMAND_OUTPUT_SHOULD_NOT_RENDER")).toHaveCount(0);
  await expect(page.getByText("3 обновл.")).toBeVisible();
  await expect.poll(() => eventAfters).toContain("-1");
  await expect.poll(() => eventAfters, { timeout: 8_000 }).toContain("3");

  await page.goto(`/tasks/${identifiers.longTask}`);
  const contextDetails = page.locator("details").filter({ hasText: "Задание агенту" });
  await contextDetails.locator("summary").click();
  await expect(contextDetails.getByText("End of description.")).toBeVisible();
  browser.assertClean();
});

test("supports narrow grouped layouts and saves narrow screenshots", async ({ page }) => {
  const browser = observeBrowser(page);
  await page.setViewportSize({ width: 800, height: 900 });
  await page.goto("/workers");
  const workerList = page.locator(".workers-list");
  const tabletListBounds = await workerList.boundingBox();
  const tabletRowBounds = await page.locator(".worker-row").first().boundingBox();
  expect(tabletRowBounds?.width ?? Infinity).toBeLessThanOrEqual(
    tabletListBounds?.width ?? 0,
  );

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Обзор", exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Продукт — factory-demo" })).toBeVisible();
  await page.screenshot({ path: "test-results/screenshots/overview-narrow.png", fullPage: true });

  await page.goto("/work");
  await expect(page.getByRole("heading", { name: "Работа агентов" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "В работе" })).toBeVisible();
  const explanation = page.locator(".work-explanation").first();
  await expect(explanation).toBeVisible();
  expect(await page.evaluate(
    "getComputedStyle(document.querySelector('.work-explanation')).gridTemplateColumns.split(' ').length",
  )).toBe(1);
  expect(await page.evaluate(
    "document.querySelector('main').scrollWidth <= document.querySelector('main').clientWidth",
  )).toBe(true);
  await page.screenshot({ path: "test-results/screenshots/work-narrow.png", fullPage: true });

  await page.goto("/workers");
  await expect(page.getByRole("heading", { name: "Исполнители" })).toBeVisible();
  await page.screenshot({ path: "test-results/screenshots/workers-narrow.png", fullPage: true });

  await page.getByRole("button", { name: "Поставить задачу" }).click();
  const dialog = page.getByRole("dialog", { name: "Поставить задачу" });
  await dialog.getByLabel("Исполнитель").selectOption(realWorker);
  await dialog.getByLabel("Название").fill("Narrow viewport delegation");
  await dialog.getByLabel("Контекст").fill("Review the complete narrow task form.");
  await dialog.getByLabel("Репозиторий").selectOption(identifiers.realFactoryRepository);
  await page.screenshot({ path: "test-results/screenshots/delegate-narrow.png", fullPage: true });
  await page.keyboard.press("Escape");

  await page.goto(`/tasks/${identifiers.runningTask}`);
  await expect(page.getByRole("heading", { name: "Implement the modern control-plane UI" })).toBeVisible();
  await page.screenshot({
    path: "test-results/screenshots/task-detail-narrow.png",
    fullPage: true,
  });
  browser.assertClean();
});

test("audits every Factory screen on desktop and phone", async ({ context, baseURL }) => {
  test.setTimeout(240_000);
  const api = await request.newContext({ baseURL: baseURL });
  const workflow = await json<{ workflow: { id: string } }>(
    await api.post("/api/v1/workflows", {
      data: {
        request_key: "e2e-full-visual-audit-workflow",
        title: "Full visual audit runbook",
        summary: "Keeps every Factory route available to the visual audit.",
        instructions: "Inspect the representative repository and report the verified result.",
      },
    }),
  );
  const automation = await json<{ automation: { id: string } }>(
    await api.post("/api/v1/automations", {
      data: {
        request_key: "e2e-full-visual-audit-automation",
        title: "Full visual audit Automation",
        workflow_id: workflow.workflow.id,
        repository_id: identifiers.automationRepository,
        context: "A disabled schedule fixture for deterministic visual inspection.",
        timeout_seconds: 60,
        trigger: { type: "schedule", cron: "0 9 * * 1", timezone: "UTC" },
      },
    }),
  );

  // This table mirrors every non-detail branch in App.readRoute/routePath.
  // Detail routes and Delegate task follow in the same audited sequence below.
  const routeScreens: AuditScreen[] = [
    { name: "overview", path: "/", ready: (page) => page.getByRole("heading", { name: "Обзор", exact: true }) },
    { name: "say", path: "/say", ready: (page) => page.getByRole("button", { name: "Начать запись" }) },
    { name: "epics", path: "/epics", ready: (page) => page.getByText(/Эпики — большие цели/) },
    { name: "answer", path: "/answer", ready: (page) => page.getByText(/Здесь конвейер спрашивает тебя/) },
    { name: "access", path: "/access", ready: (page) => page.getByRole("heading", { name: "Доступы" }) },
    { name: "sandbox-keys", path: "/sandbox-keys", ready: (page) => page.getByRole("heading", { name: "Ключи песочницы" }) },
    { name: "work", path: "/work", ready: (page) => page.getByRole("heading", { name: "Работа агентов" }) },
    { name: "workers", path: "/workers", ready: (page) => page.getByRole("heading", { name: "Исполнители" }) },
    { name: "repositories", path: "/repositories", ready: (page) => page.getByRole("heading", { name: "Репозитории" }) },
    { name: "projects", path: "/projects", ready: (page) => page.getByRole("heading", { name: "Безопасные проекты" }) },
    { name: "workflows", path: "/workflows", ready: (page) => page.getByRole("heading", { name: "Сценарии", exact: true }) },
    { name: "pipeline", path: "/pipeline", ready: (page) => page.getByRole("heading", { name: "Pipeline", exact: true }) },
    { name: "cards", path: "/cards", ready: (page) => page.getByRole("heading", { name: "Карточки", exact: true }) },
    { name: "automations", path: "/automations", ready: (page) => page.getByRole("heading", { name: "Автоматизации", exact: true }) },
    { name: "settings", path: "/settings", ready: (page) => page.getByRole("heading", { name: "Настройки" }) },
    { name: "dialog", path: "/dialog", ready: (page) => page.getByRole("heading", { name: "Диалог", exact: true }) },
  ];
  const detailScreens: AuditScreen[] = [
    { name: "task-detail", path: `/tasks/${identifiers.runningTask}`, ready: (page) => page.getByRole("heading", { name: "Implement the modern control-plane UI" }) },
    { name: "worker-detail", path: `/workers/${workerOnline}`, ready: (page) => page.getByRole("heading", { name: "Build Mac" }) },
    { name: "repository-detail", path: `/repositories/${identifiers.automationRepository}`, ready: (page) => page.getByRole("heading", { name: "github.com/example/automation-fixture" }) },
    { name: "workflow-detail", path: `/workflows/${workflow.workflow.id}`, ready: (page) => page.getByRole("heading", { name: "Full visual audit runbook" }) },
    { name: "automation-detail", path: `/automations/${automation.automation.id}`, ready: (page) => page.getByRole("heading", { name: "Full visual audit Automation" }) },
  ];
  const screens = [...routeScreens, ...detailScreens];

  for (const viewport of [
    { name: "desktop", width: 1440, height: 1000 },
    { name: "phone", width: 390, height: 844 },
  ] as const) {
    for (const screen of screens) {
      const page = await context.newPage();
      const browser = observeBrowser(page);
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.goto(screen.path);
      await expect(screen.ready(page), `${screen.name} must show meaningful content`).toBeVisible();
      if (viewport.name === "desktop" && screen.name === "overview") {
        await expectInteractiveOverflowRegression(page);
      }
      if (viewport.name === "phone") await exerciseMobileNavigation(page);
      await expectAuditedLayout(page, viewport.name === "desktop");
      await page.screenshot({
        path: `test-results/screenshots/${screen.name}-${viewport.name}.png`,
        fullPage: true,
      });
      browser.assertClean();
      await page.close();
    }

    const page = await context.newPage();
    const browser = observeBrowser(page);
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Обзор", exact: true })).toBeVisible();
    if (viewport.name === "phone") await exerciseMobileNavigation(page);
    await page.getByRole("button", { name: "Поставить задачу" }).click();
    const dialog = page.getByRole("dialog", { name: "Поставить задачу" });
    await expect(dialog).toBeVisible();
    await dialog.getByLabel("Исполнитель").selectOption(workerOffline);
    await dialog.getByLabel("Репозиторий").selectOption(identifiers.offlineRepository);
    await dialog.getByLabel("Название").fill("Delegate from the full desktop and phone visual audit");
    await dialog.getByLabel("Контекст").fill("All fields and actions remain reachable without page-level horizontal scrolling.");
    await expectAuditedLayout(page, viewport.name === "desktop");
    await page.screenshot({
      path: `test-results/screenshots/delegate-task-${viewport.name}.png`,
      fullPage: true,
    });
    browser.assertClean();
    await page.close();
  }
  await api.dispose();
});

test("opens and closes delegation from the keyboard", async ({ page }) => {
  const browser = observeBrowser(page);
  await page.goto("/");
  const delegate = page.getByRole("button", { name: "Поставить задачу" }).first();
  await delegate.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Название")).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(delegate).toBeFocused();
  browser.assertClean();
});

test("manages repository routing end to end and preserves add input while polling", async ({ page, baseURL }) => {
  const browser = observeBrowser(page);
  const api = await request.newContext({ baseURL: baseURL });
  await json(
    await api.put(`/api/v1/workers/${managedWorker}`, {
      headers: {
        "X-Factory-Worker-Bootstrap-Credential": testWorkerBootstrapCredential,
      },
      data: {
        name: "Managed repository worker",
        worker_version: "2.0.0-test",
        runtime: "codex",
        runtime_version: "0.42.0-test",
        capacity: 1,
        active_count: 0,
        health: "healthy",
        source_access: [{ provider: "github", hostname: "github.com" }],
        accepts_managed_repositories: true,
        managed_repository_ids: [],
        repositories: [],
        retained_worktrees: [],
      },
    }),
  );

  await page.goto("/repositories");
  const repositoriesNavigation = page.getByRole("button", { name: "Репозитории", exact: true });
  await expect(repositoriesNavigation).toHaveAttribute("aria-current", "page");
  const input = page.getByLabel("Canonical identity");
  await input.fill("github.com/example/browser-managed");
  await expect(input).toBeFocused();
  await page.waitForTimeout(10_500);
  await expect(input).toHaveValue("github.com/example/browser-managed");
  await expect(input).toBeFocused();
  await page.getByRole("button", { name: "Add repository" }).click();

  await expect(page.getByRole("heading", { name: "github.com/example/browser-managed" })).toBeVisible();
  await expect(repositoriesNavigation).toHaveClass(/active/);
  await expect(repositoriesNavigation).not.toHaveAttribute("aria-current");
  await expect(page.getByText(/\d+ workers? (?:is|are) ready to acquire routed work/)).toBeVisible();
  await expect(page.getByText("Managed repository worker")).toBeVisible();
  await page.screenshot({ path: "test-results/screenshots/repository-detail-desktop.png", fullPage: true });

  await page.getByRole("button", { name: "Disable repository" }).click();
  await expect(page.getByText(/Disabling rejects new routed work/)).toBeVisible();
  await page.getByRole("button", { name: "Disable routing" }).click();
  await expect(page.getByText("Маршрутизация выключена")).toBeVisible();

  const disabledRoute = await api.post("/api/v1/tasks", {
    data: {
      request_key: "e2e-disabled-managed-route",
      title: "Rejected while repository routing is disabled",
      description: "Prove disabled managed repositories reject new routed work.",
      route: {
        repository_remote_identity: "github.com/example/browser-managed",
        source_access: { provider: "github", hostname: "github.com" },
      },
      timeout_seconds: 60,
    },
  });
  expect(disabledRoute.status()).toBe(409);
  expect(await disabledRoute.json()).toMatchObject({ error: { code: "repository_not_managed" } });

  await page.getByRole("button", { name: "Включить репозиторий" }).click();
  await expect(page.getByRole("button", { name: "Выключить репозиторий" })).toBeVisible();
  const enabledRoute = await api.post("/api/v1/tasks", {
    data: {
      request_key: "e2e-enabled-managed-route",
      title: "Eligible after repository routing is enabled",
      description: "Prove enabled managed repositories become eligible for acquisition.",
      route: {
        repository_remote_identity: "github.com/example/browser-managed",
        source_access: { provider: "github", hostname: "github.com" },
      },
      timeout_seconds: 60,
    },
  });
  expect(enabledRoute.status()).toBe(201);
  const enabledTask = await enabledRoute.json() as { execution: { assigned_worker_id: string } };
  expect([managedWorker, realWorker]).toContain(enabledTask.execution.assigned_worker_id);

  await page.getByRole("button", { name: "Поставить задачу" }).click();
  const delegate = page.getByRole("dialog", { name: "Поставить задачу" });
  await delegate.getByLabel("Название").fill("Delegate configured managed repository");
  await delegate.getByLabel("Контекст").fill("Acquire this repository on the selected worker.");
  await delegate.getByLabel("Исполнитель").selectOption(managedWorker);
  const repositoryPicker = delegate.getByLabel("Репозиторий");
  const managedOption = repositoryPicker.locator("option").filter({ hasText: "github.com/example/browser-managed" });
  await expect(managedOption).toBeEnabled();
  await expect(managedOption).toContainText("получается по запросу");
  await repositoryPicker.selectOption((await managedOption.getAttribute("value"))!);
  await delegate.getByRole("button", { name: "Поставить задачу" }).click();
  await expect(page.getByRole("heading", { name: "Delegate configured managed repository" })).toBeVisible();
  const delegatedTaskID = new URL(page.url()).pathname.split("/").at(-1)!;
  const delegatedTask = await json<TaskDetail>(await api.get(`/api/v1/tasks/${delegatedTaskID}`));
  expect(delegatedTask.execution.assigned_worker_id).toBe(managedWorker);
  await api.dispose();
  browser.assertClean();
});

test("previews and dispatches one typed GitHub issue Automation without duplication", async ({ page, baseURL }) => {
  const browser = observeBrowser(page);
  const api = await request.newContext({ baseURL: baseURL });
  await registerWorker(
    api,
    automationWorker,
    "Automation fixture",
    [
      {
        key: "automation-fixture",
        remote_identity: "github.com/example/automation-fixture",
        retained_count: 0,
      },
    ],
    0,
    [],
    "codex",
    [{ provider: "github", hostname: "github.com" }],
  );
  await page.goto("/workflows");
  await page.getByRole("button", { name: "Создать сценарий" }).first().click();
  const workflow = page.getByRole("dialog", { name: "Создать сценарий" });
  await workflow.getByLabel("Название").fill("E2E issue Automation");
  await workflow.getByLabel("Описание").fill("Dispatch the safe issue fixture.");
  await workflow.getByLabel("Инструкции Markdown").fill("Fetch the live issue, implement it, and verify the result.");
  await workflow.getByRole("button", { name: "Создать сценарий" }).click();
  await expect(page.getByRole("heading", { name: "E2E issue Automation" })).toBeVisible();

  await page.getByRole("button", { name: "Автоматизации", exact: true }).click();
  await page.getByRole("button", { name: "Создать автоматизацию" }).first().click();
  const automation = page.getByRole("dialog", { name: "Создать автоматизацию" });
  await automation.getByLabel("Название").fill("E2E ready issues");
  await automation.getByLabel("Сценарий").selectOption({ label: "E2E issue Automation" });
  await automation.getByLabel("Репозиторий").selectOption(identifiers.automationRepository);
  await automation.getByLabel("Контекст автоматизации").fill("Use only the safe browser fixture repository.");
  await automation.getByRole("button", { name: "Создать автоматизацию" }).click();
  await expect(page.getByRole("heading", { name: "E2E ready issues" })).toBeVisible();

  await page.getByRole("button", { name: "Проверить триггер" }).click();
  await expect(page.getByText("#184 Typed Automation browser fixture")).toBeVisible();
  await expect(page.getByText("Проверка не создаёт задачу или постоянный запуск.")).toBeVisible();
  await expect(page.getByText("Постоянного запуска ещё не было.")).toBeVisible();

  await page.getByRole("button", { name: "Включить", exact: true }).click();
  await expect(page.getByRole("checkbox", { name: /factory-poller is stopped/ })).toHaveCount(0);
  await page.getByRole("button", { name: "Подтвердить: включить" }).click();
  await expect(page.locator(".automation-health").getByText("исправна", { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".occurrence-list").getByText("#184 Typed Automation browser fixture", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Открыть задачу" })).toBeVisible();

  const before = await json<{ tasks: Array<{ request_key: string }> }>(await api.get("/api/v1/tasks?limit=200"));
  const automationTasksBefore = before.tasks.filter((task) => task.request_key.includes(":github_issue:184"));
  expect(automationTasksBefore).toHaveLength(1);

  await page.getByRole("button", { name: "Проверить сейчас" }).click();
  await expect(page.locator(".automation-metrics > div").filter({ hasText: "Совпало" }).locator("strong")).toHaveText("2", { timeout: 15_000 });
  const after = await json<{ tasks: Array<{ request_key: string }> }>(await api.get("/api/v1/tasks?limit=200"));
  const automationTasksAfter = after.tasks.filter((task) => task.request_key.includes(":github_issue:184"));
  expect(automationTasksAfter).toHaveLength(1);
  await api.dispose();
  browser.assertClean();
});

test("previews and dispatches one typed GitHub pull-request Automation without duplication", async ({ page, baseURL }) => {
  const browser = observeBrowser(page);
  const api = await request.newContext({ baseURL: baseURL });
  await registerWorker(
    api,
    automationWorker,
    "Automation fixture",
    [{
      key: "automation-fixture",
      remote_identity: "github.com/example/automation-fixture",
      retained_count: 0,
    }],
    0,
    [],
    "codex",
    [{ provider: "github", hostname: "github.com" }],
  );
  await page.goto("/workflows");
  await page.getByRole("button", { name: "Создать сценарий" }).first().click();
  const workflow = page.getByRole("dialog", { name: "Создать сценарий" });
  await workflow.getByLabel("Название").fill("E2E pull-request review");
  await workflow.getByLabel("Описание").fill("Review the safe pull-request fixture.");
  await workflow.getByLabel("Инструкции Markdown").fill("Fetch and revalidate the live pull request, review it, and do not merge it.");
  await workflow.getByRole("button", { name: "Создать сценарий" }).click();
  await expect(page.getByRole("heading", { name: "E2E pull-request review" })).toBeVisible();

  await page.getByRole("button", { name: "Автоматизации", exact: true }).click();
  await page.getByRole("button", { name: "Создать автоматизацию" }).first().click();
  const automation = page.getByRole("dialog", { name: "Создать автоматизацию" });
  await automation.getByLabel("Название").fill("E2E pull-request Automation");
  await automation.getByLabel("Сценарий").selectOption({ label: "E2E pull-request review" });
  await automation.getByLabel("Репозиторий").selectOption(identifiers.automationRepository);
  await automation.getByLabel("Триггер").selectOption("github_pull_request");
  await automation.getByLabel("Обязательные метки").fill("factory:review");
  await automation.getByLabel("Базовые ветки").fill("main");
  await automation.getByLabel("Контекст автоматизации").fill("Review only the safe synthetic pull request and never merge it.");
  await automation.getByRole("button", { name: "Создать автоматизацию" }).click();
  await expect(page.getByRole("heading", { name: "E2E pull-request Automation" })).toBeVisible();

  await page.getByRole("button", { name: "Проверить триггер" }).click();
  await expect(page.getByText("#185 Typed pull-request Automation browser fixture")).toBeVisible();
  await expect(page.getByText("Проверка не создаёт задачу или постоянный запуск.")).toBeVisible();
  await expect(page.getByText("Постоянного запуска ещё не было.")).toBeVisible();

  await page.getByRole("button", { name: "Включить", exact: true }).click();
  await expect(page.getByRole("checkbox", { name: /factory-poller is stopped/ })).toHaveCount(0);
  await page.getByRole("button", { name: "Подтвердить: включить" }).click();
  await expect(page.locator(".automation-health").getByText("исправна", { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".occurrence-list").getByText("#185 Typed pull-request Automation browser fixture", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Открыть задачу" })).toBeVisible();

  const before = await json<{ tasks: Array<{ request_key: string }> }>(await api.get("/api/v1/tasks?limit=200"));
  expect(before.tasks.filter((task) => task.request_key.includes(":github_pull_request:185"))).toHaveLength(1);

  await page.getByRole("button", { name: "Проверить сейчас" }).click();
  await expect(page.locator(".automation-metrics > div").filter({ hasText: "Совпало" }).locator("strong")).toHaveText("2", { timeout: 15_000 });
  const after = await json<{ tasks: Array<{ request_key: string }> }>(await api.get("/api/v1/tasks?limit=200"));
  expect(after.tasks.filter((task) => task.request_key.includes(":github_pull_request:185"))).toHaveLength(1);
  await api.dispose();
  browser.assertClean();
});

test("previews, enables, and runs a schedule Automation through the ordinary task path", async ({ page, baseURL }) => {
  const browser = observeBrowser(page);
  const api = await request.newContext({ baseURL: baseURL });
  await registerWorker(
    api,
    automationWorker,
    "Schedule fixture",
    [{
      key: "automation-fixture",
      remote_identity: "github.com/example/automation-fixture",
      retained_count: 0,
    }],
    0,
    [],
    "codex",
    [],
  );
  await page.goto("/workflows");
  await page.getByRole("button", { name: "Создать сценарий" }).first().click();
  const workflow = page.getByRole("dialog", { name: "Создать сценарий" });
  await workflow.getByLabel("Название").fill("E2E scheduled maintenance");
  await workflow.getByLabel("Описание").fill("Run safe scheduled maintenance.");
  await workflow.getByLabel("Инструкции Markdown").fill("Inspect the fixture repository and report the scheduled maintenance result.");
  await workflow.getByRole("button", { name: "Создать сценарий" }).click();
  await expect(page.getByRole("heading", { name: "E2E scheduled maintenance" })).toBeVisible();

  await page.getByRole("button", { name: "Автоматизации", exact: true }).click();
  await page.getByRole("button", { name: "Создать автоматизацию" }).first().click();
  const automation = page.getByRole("dialog", { name: "Создать автоматизацию" });
  await automation.getByLabel("Название").fill("E2E schedule Automation");
  await automation.getByLabel("Сценарий").selectOption({ label: "E2E scheduled maintenance" });
  await automation.getByLabel("Репозиторий").selectOption(identifiers.automationRepository);
  await automation.getByLabel("Триггер").selectOption("schedule");
  await automation.getByLabel("Частота").selectOption("custom");
  await automation.getByText("Дополнительные настройки").click();
  await automation.getByLabel("Cron (пять полей)").fill("0 0 1 JAN *");
  await automation.getByLabel("Часовой пояс").fill("Europe/London");
  await automation.getByLabel("Контекст автоматизации").fill("Use only the safe synthetic repository.");
  await automation.getByRole("button", { name: "Создать автоматизацию" }).click();
  await expect(page.getByRole("heading", { name: "E2E schedule Automation" })).toBeVisible();

  await page.getByRole("button", { name: "Проверить триггер" }).click();
  await expect(page.getByText(/Следующий подходящий момент UTC/)).toBeVisible();
  await expect(page.getByText("Постоянного запуска ещё не было.")).toBeVisible();
  await page.getByRole("button", { name: "Включить", exact: true }).click();
  await expect(page.getByRole("checkbox", { name: /factory-poller is stopped/ })).toHaveCount(0);
  await page.getByRole("button", { name: "Подтвердить: включить" }).click();
  const nextDue = page.getByText("Следующий срок UTC").locator("..").locator("dd");
  await expect.poll(async () => {
    const instant = Date.parse((await nextDue.textContent()) ?? "");
    return Number.isFinite(instant) && instant > Date.now();
  }).toBe(true);

  await page.getByRole("button", { name: "Запустить сейчас" }).click();
  await expect(page.locator(".occurrence-list").getByText("Запущен вручную", { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("button", { name: "Открыть задачу" })).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".automation-latest-task").getByText("Запущен вручную", { exact: true })).toBeVisible({ timeout: 15_000 });
  await page.screenshot({ path: "test-results/screenshots/automation-detail-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator(".sidebar")).not.toBeInViewport();
  await page.screenshot({ path: "test-results/screenshots/automation-detail-narrow.png", fullPage: true });
  const overflow = await page.evaluate(`Array.from(document.querySelectorAll("*"))
    .filter((element) => element.getBoundingClientRect().right > document.documentElement.clientWidth + 1)
    .map((element) => ({ tag: element.tagName, className: element.className }))`);
  expect(overflow).toEqual([]);
  const tasks = await json<{ tasks: Array<{ request_key: string }> }>(await api.get("/api/v1/tasks?limit=200"));
  expect(tasks.tasks.filter((task) => task.request_key.includes(":schedule:run:"))).toHaveLength(1);
  await api.dispose();
  browser.assertClean();
});

test("migrates a locked legacy snapshot through Resume and Finalize", async ({ page, baseURL }) => {
  const browser = observeBrowser(page);
  const api = await request.newContext({ baseURL: baseURL });
  const legacyRoot = `${process.cwd()}/test-results/legacy-poller`;
  await page.goto("/automations");
  await page.getByRole("button", { name: "Перенести старый опросчик" }).click();
  const migration = page.getByRole("dialog", { name: "Перенести старый опросчик" });
  await migration.getByLabel("Старый poller.toml").fill(`${legacyRoot}/poller.toml`);
  await migration.getByLabel("Каталог данных старого опросчика").fill(legacyRoot);
  await migration.getByLabel("Исходный рабочий каталог").fill(legacyRoot);
  await migration.getByRole("checkbox", { name: /Я остановил все процессы factory-poller/ }).check();
  const previewResponse = page.waitForResponse((response) =>
    response.url().endsWith("/api/v1/migrations/legacy-poller/preview") && response.request().method() === "POST",
  );
  await migration.getByRole("button", { name: "Просмотреть заблокированный снимок" }).click();
  const previewResult = await previewResponse;
  expect(previewResult.ok(), await previewResult.text()).toBe(true);

  await expect(migration.getByText("1 поддержано · 0 не поддержано")).toBeVisible();
  await expect(migration.getByText("0 отправлено · 1 ожидает", { exact: true })).toBeVisible();
  await expect(migration.getByText(`${legacyRoot}/poller/poller.sqlite3`, { exact: true })).toBeVisible();
  await expect(migration.getByText(/Связанный репозиторий:/)).toContainText("github.com/example/automation-fixture");
  await migration.getByLabel("Название сценария").fill("E2E imported legacy workflow");
  await migration.getByLabel("Название автоматизации").fill("E2E imported legacy issues");
  const importedResponse = page.waitForResponse((response) =>
    response.url().endsWith("/api/v1/migrations/legacy-poller/import") && response.request().method() === "POST",
  );
  await migration.getByRole("button", { name: "Импортировать выключенные автоматизации" }).click();
  const status = await (await importedResponse).json() as {
    id: string;
    automations: Array<{ id: string }>;
  };
  await expect(migration.getByText("1 не разобрано")).toBeVisible();
  await expect(migration.getByRole("button", { name: "Завершить и архивировать" })).toBeDisabled();

  const blockedEnable = await api.put(`/api/v1/automations/${status.automations[0].id}/enabled`, {
    data: { enabled: true },
  });
  expect(blockedEnable.status()).toBe(409);
  expect(await blockedEnable.text()).toContain("migration_not_finalized");

  await page.reload();
  await page.getByRole("button", { name: "Перенести старый опросчик" }).click();
  await expect(migration.getByText("1 не разобрано")).toBeVisible();
  const recoveredResume = migration.getByRole("button", { name: "Возобновить" });
  await expect(recoveredResume).toBeDisabled();
  await migration.getByRole("checkbox", { name: /Я ещё раз подтвердил, что все процессы factory-poller остановлены/ }).check();
  await expect(recoveredResume).toBeEnabled();
  await recoveredResume.click();
  await expect(migration.getByText("0 не разобрано")).toBeVisible();
  await migration.getByRole("button", { name: "Завершить и архивировать" }).click();
  await expect(migration.getByText("Перенос завершён")).toBeVisible();
  await expect(migration.getByText(`${legacyRoot}/archive/poller/${status.id}`)).toBeVisible();

  const tasks = await json<{ tasks: Array<{ request_key: string }> }>(await api.get("/api/v1/tasks?limit=200"));
  expect(tasks.tasks.filter((task) => task.request_key === "legacy-browser-request-187")).toHaveLength(1);
  await expect(migration.getByRole("button", { name: "Review E2E imported legacy issues" })).toBeVisible();
  await api.dispose();
  browser.assertClean();
});

test("edits pilot settings from the Settings screen", async ({ page }) => {
  const browser = observeBrowser(page);
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Настройки" })).toBeVisible();
  await expect(page.getByText("Цепочка моделей")).toBeVisible();
  await expect(page.getByLabel("Репозиторий продукта")).toHaveValue("github.com/example/factory");
  await expect(page.getByLabel("Тип источника")).toHaveValue("factory");
  const poll = page.getByLabel("Интервал проверки, секунд");
  await expect(poll).toHaveValue("10");
  await poll.fill("15");
  const response = page.waitForResponse((result) =>
    result.url().endsWith("/api/v1/settings/pilot") && result.request().method() === "PUT",
  );
  await page.getByRole("button", { name: "Сохранить настройки" }).click();
  expect((await response).ok()).toBe(true);
  await expect(page.getByText(/Настройки сохранены/)).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Интервал проверки, секунд")).toHaveValue("15");
  await expect(page.getByLabel("Репозиторий продукта")).toHaveValue("github.com/example/factory");
  await expect(page.getByLabel("Тип источника")).toHaveValue("factory");
  browser.assertClean();
});
