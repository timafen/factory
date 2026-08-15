import {
  expect,
  request,
  test,
  type APIRequestContext,
  type Locator,
  type Page,
} from "@playwright/test";
import {
  coldHTTPSFixtureSetupTimeout,
  configureColdHTTPSFixtureSetupTimeout,
  testWorkerBootstrapCredential,
} from "../playwright.config";

test.describe.configure({ mode: "serial" });
test.setTimeout(coldHTTPSFixtureSetupTimeout);

const workerOnline = "worker-online-e2e";
const workerOffline = "worker-offline-e2e";
const managedWorker = "worker-managed-e2e";
const automationWorker = "worker-automation-e2e";
const realWorker = "11111111-1111-4111-8111-111111111111";
const pausedHTTPSWork = "HTTPS proxy resumes paused work";
const completedHTTPSWork = "HTTPS proxy clears completed pause";
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

async function waitForHTTPSProxyFixture(api: APIRequestContext) {
  const readyTitle = `[auto] [5/5 Verify] ${completedHTTPSWork}`;
  for (let attempt = 0; attempt < 120; attempt += 1) {
    const response = await api.get("/api/v1/tasks?limit=200");
    if (response.ok()) {
      const body = await response.json() as { tasks: Array<{ title: string; state: string }> };
      if (body.tasks.some((task) => task.title === readyTitle && task.state === "succeeded")) return;
    }
    await new Promise((resolveWait) => setTimeout(resolveWait, 250));
  }
  throw new Error("HTTPS reverse-proxy browser fixture did not finish");
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
  configureColdHTTPSFixtureSetupTimeout((timeout) => test.setTimeout(timeout));
  const api = await request.newContext({ baseURL: baseURL, ignoreHTTPSErrors: true });
  fixtureAPI = api;
  const real = await waitForRealWorker(api);
  await waitForHTTPSProxyFixture(api);
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
  const api = await request.newContext({ baseURL: baseURL, ignoreHTTPSErrors: true });
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
  await page.goto("/");
  const activeServiceWorker = await page.evaluate(async () => {
    const registration = await navigator.serviceWorker.ready;
    return registration.active?.scriptURL ?? null;
  });
  expect(activeServiceWorker).toMatch(/\/sw\.js$/);
  const dashboard = await page.evaluate(async () => {
    const response = await fetch("/api/v1/dashboard");
    if (!response.ok) throw new Error(`dashboard returned ${response.status}`);
    return response.json();
  }) as { projects: Array<{ readiness?: unknown }> };
  await page.route("**/api/v1/dashboard", async (route) => {
    dashboard.projects[0].readiness = {
      verdict: "ready", checked_at: "2026-08-10T12:00:00Z", checks,
    };
    dashboard.projects[1].readiness = {
      verdict: "ready", checked_at: "2026-08-10T12:00:00Z",
      checks: checks.map((check) => check.key === "safe_environment"
        ? { ...check, state: "unknown", reason: "Для Factory отдельный безопасный стенд не выбран." }
        : check),
    };
    await route.fulfill({ json: dashboard });
  });

  await page.reload();
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

test("@critical sends release and rollback through the browser", async ({ page }) => {
  const browser = observeBrowser(page);
  const projectID = "critical-release-project";
  const commitSHA = "a".repeat(40);
  const now = "2026-08-14T12:00:00Z";
  const project = {
    id: projectID,
    repository_id: "critical-release-repository",
    name: "Critical release",
    remote_identity: "github.com/timafen/factory",
    main_branch: "main",
    project_type: "factory-single-instance",
    executor_group: "factory",
    required_checks: ["secret-scan", "static-typecheck", "tests", "build"],
    environments: [{
      name: "staging",
      url: "https://factory.timafen.com",
      health_url: "https://factory.timafen.com/api/v1/dashboard",
      blocked: false,
      release_adapter: "fx-factory-release",
      rollback_adapter: "fx-factory-rollback",
      required_secrets: ["GITHUB_TOKEN"],
      web_hosts: ["factory.timafen.com"],
    }],
    created_at: now,
    updated_at: now,
  };
  const operations = new Map<string, Record<string, unknown>>();
  const requestedKinds: string[] = [];

  await page.route("**/api/v1/projects", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ json: { projects: [project] } });
      return;
    }
    await route.continue();
  });
  await page.route(`**/api/v1/projects/${projectID}/**`, async (route) => {
    const { pathname } = new URL(route.request().url());
    if (pathname.endsWith("/readiness")) {
      await route.fulfill({ json: {
        ready: true,
        commit_sha: commitSHA,
        gates: ["secret-scan", "static-typecheck", "tests", "build"].map((name) => ({
          name, ready: true, reason: `${name} passed`, commit_sha: commitSHA, checked_at: now,
        })),
        secrets: [{ name: "GITHUB_TOKEN", present: true }],
      } });
      return;
    }
    const kind = pathname.endsWith("/release") ? "release" : pathname.endsWith("/rollback") ? "rollback" : "";
    if (route.request().method() === "POST" && kind) {
      const body = route.request().postDataJSON() as { commit_sha: string };
      expect(body.commit_sha).toBe(commitSHA);
      requestedKinds.push(kind);
      const operation = {
        id: `critical-${kind}`,
        project_id: projectID,
        environment: "staging",
        kind,
        commit_sha: commitSHA,
        status: "succeeded",
        message: kind === "release" ? "Выпуск подтверждён" : "Откат подтверждён",
        owner_confirmed: true,
        created_at: now,
        updated_at: now,
      };
      operations.set(operation.id, operation);
      await route.fulfill({ json: operation });
      return;
    }
    const operationID = pathname.split("/").at(-1)!;
    if (route.request().method() === "GET" && operations.has(operationID)) {
      await route.fulfill({ json: operations.get(operationID) });
      return;
    }
    await route.continue();
  });

  await page.goto("/projects");
  await page.getByLabel("Проверенный SHA Critical release").fill(commitSHA);
  await page.getByRole("button", { name: "Выпустить staging" }).click();
  await expect(page.getByRole("status")).toHaveText("Выпуск подтверждён");
  await page.getByRole("button", { name: "Вернуть staging" }).click();
  await expect(page.getByRole("status")).toHaveText("Откат подтверждён");
  expect(requestedKinds).toEqual(["release", "rollback"]);
  browser.assertClean();
});

test("creates, pins, revises, and disables a reusable Workflow", async ({ page, baseURL }) => {
  const browser = observeBrowser(page);
  await page.goto("/workflows");
  await expect(page.getByRole("heading", { name: "Сценарии", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Create runbook" }).first().click();
  const create = page.getByRole("dialog", { name: "Create runbook" });
  await create.getByLabel("Title").fill("E2E pinned review");
  await create.getByLabel("Summary").fill("Prove immutable prompt snapshots.");
  const instructions = create.getByLabel("Markdown instructions");
  await instructions.fill("Use revision one instructions exactly.");
  await Promise.all([
    page.waitForResponse((response) => response.url().includes("/api/v1/workflows?") && response.ok()),
    page.evaluate("document.dispatchEvent(new Event('visibilitychange'))"),
  ]);
  await expect(instructions).toBeFocused();
  await create.getByRole("button", { name: "Create runbook" }).click();
  await expect(page.getByRole("heading", { name: "E2E pinned review" })).toBeVisible();
  const workflowURL = page.url();

  await page.getByRole("button", { name: "Поставить задачу" }).click();
  const delegate = page.getByRole("dialog", { name: "Delegate task" });
  await delegate.getByLabel("Workflow").selectOption({ label: "E2E pinned review · revision 1" });
  await delegate.getByLabel("Title").fill("Pinned Workflow browser task");
  await delegate.getByLabel("Context").fill("JIRA-183 stays free text.");
  await delegate.getByLabel("Worker").selectOption(workerOffline);
  await delegate.getByLabel("Repository").selectOption(identifiers.offlineRepository);
  await delegate.getByRole("button", { name: "Delegate task" }).click();
  await expect(page.getByRole("heading", { name: "Pinned Workflow browser task" })).toBeVisible();
  await page.locator("details").filter({ hasText: "Задание агенту" }).locator("summary").click();
  await expect(page.getByText("JIRA-183 stays free text.", { exact: true })).toBeVisible();
  await page.locator("details").filter({ hasText: "Полный промпт" }).locator("summary").click();
  await expect(page.getByText(/Use revision one instructions exactly/)).toBeVisible();
  const taskID = new URL(page.url()).pathname.split("/").at(-1)!;

  await page.goto(workflowURL);
  await page.getByRole("button", { name: "New revision" }).click();
  const revise = page.getByRole("dialog", { name: "Create revision" });
  await revise.getByLabel("Markdown instructions").fill("Use revision two instructions instead.");
  await revise.getByRole("button", { name: "Create revision" }).click();
  await expect(page.getByText("Revision 2", { exact: true }).first()).toBeVisible();

  const api = await request.newContext({ baseURL: baseURL, ignoreHTTPSErrors: true });
  const pinned = await json<TaskDetail>(await api.get(`/api/v1/tasks/${taskID}`));
  expect(pinned.context).toBe("JIRA-183 stays free text.");
  expect(pinned.task.description).toBe(pinned.resolved_prompt);
  expect(pinned.workflow?.revision_number).toBe(1);
  expect(pinned.resolved_prompt).toContain("Use revision one instructions exactly.");
  expect(pinned.resolved_prompt).not.toContain("Use revision two instructions instead.");
  await api.dispose();

  await page.getByRole("button", { name: "Disable" }).click();
  await page.getByRole("button", { name: "Confirm disable" }).click();
  await expect(page.getByRole("button", { name: "Enable", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Поставить задачу" }).click();
  await expect(page.getByRole("dialog").getByLabel("Workflow").getByRole("option", { name: /E2E pinned review/ })).toHaveCount(0);
  await page.keyboard.press("Escape");
  browser.assertClean();
});

test("@critical starts work and completes it in a real Git worktree", async ({ page, baseURL }) => {
  const browser = observeBrowser(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Поставить задачу" }).first().click();
  const dialog = page.getByRole("dialog", { name: "Delegate task" });
  await dialog.getByLabel("Worker").selectOption(realWorker);
  await expect(
    dialog.getByLabel("Repository").getByRole("option", { name: /factory-demo/ }),
  ).toHaveCount(1);
  await expect(
    dialog.getByLabel("Repository").getByRole("option", { name: /handbook-demo/ }),
  ).toHaveCount(1);
  await dialog.getByLabel("Title").fill("Prove the complete local workflow");
  await dialog
    .getByLabel("Context")
    .fill("Create deterministic evidence in the assigned real Git worktree.");
  await dialog.getByLabel("Repository").selectOption(identifiers.realFactoryRepository);
  await page.screenshot({
    path: "test-results/screenshots/delegate-desktop.png",
    fullPage: true,
  });
  await dialog.getByRole("button", { name: "Delegate task" }).click();

  await expect(page.getByRole("heading", { name: "Prove the complete local workflow" })).toBeVisible();
  await expect(page.getByText("Succeeded", { exact: true }).first()).toBeVisible({
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

  const api = await request.newContext({ baseURL: baseURL, ignoreHTTPSErrors: true });
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
  const dialog = page.getByRole("dialog", { name: "Delegate task" });
  await dialog.getByLabel("Worker").selectOption(realWorker);
  await dialog.getByLabel("Title").fill("Cancel a real active Codex process");
  await dialog
    .getByLabel("Context")
    .fill("FACTORY_E2E_WAIT until the operator cancels this task.");
  await dialog.getByLabel("Repository").selectOption(identifiers.realHandbookRepository);
  await dialog.getByRole("button", { name: "Delegate task" }).click();

  await expect(page.getByText("Running", { exact: true }).first()).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByText("Waiting for operator cancellation.")).toBeVisible();
  await page.getByRole("button", { name: "Cancel" }).click();
  await page.getByRole("button", { name: "Confirm cancel" }).click();
  await expect(page.getByText("Cancelled", { exact: true }).first()).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.locator(".attempt-output.error-output")).toContainText("attempt cancelled");
  browser.assertClean();
});

test("@critical shows the pipeline stages in the Work view", async ({ page }) => {
  const browser = observeBrowser(page);
  await page.goto("/work");
  await expect(page.getByRole("heading", { name: "Работа", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Работа", exact: true })).toHaveAttribute(
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

test("@critical resumes a paused pipeline through the real HTTPS proxy and keeps Origin protected", async ({ page, baseURL }) => {
  expect(baseURL).toMatch(/^https:\/\/127\.0\.0\.1:/);
  const httpsOrigin = baseURL!;

  // Chromium preserves its own Origin even when route.continue() overrides
  // headers. Use the suite's loopback-only fixture client for this one forged
  // Origin request; its TLS bypass is scoped to the ephemeral local baseURL.
  if (!fixtureAPI) throw new Error("fixture API is not initialized");
  const hostileResponse = await fixtureAPI.post("/api/v1/works/resume", {
    headers: {
      Origin: "https://attacker.example",
      Forwarded: "for=192.0.2.1;host=attacker.example;proto=https",
      "X-Forwarded-Host": "attacker.example",
      "X-Forwarded-Proto": "http",
    },
    data: { title: pausedHTTPSWork },
  });
  expect(hostileResponse.status()).toBe(403);
  expect((await hostileResponse.json()) as { error: { code: string } }).toMatchObject({
    error: { code: "cross_origin_request" },
  });
  expect(hostileResponse.headers()).toMatchObject({
    "x-factory-e2e-client-origin": "https://attacker.example",
    "x-factory-e2e-client-forwarded": "for=192.0.2.1;host=attacker.example;proto=https",
    "x-factory-e2e-client-forwarded-host": "attacker.example",
    "x-factory-e2e-client-forwarded-proto": "http",
    "x-factory-e2e-backend-origin": "https://attacker.example",
    "x-factory-e2e-backend-forwarded": "<absent>",
    "x-factory-e2e-backend-forwarded-for": "<absent>",
    "x-factory-e2e-backend-real-ip": "<absent>",
    "x-factory-e2e-backend-forwarded-host": new URL(httpsOrigin).host,
    "x-factory-e2e-backend-forwarded-proto": "https",
  });

  await page.goto("/work");
  await expect(page.getByText(pausedHTTPSWork, { exact: true })).toBeVisible();
  const resume = page.getByRole("button", { name: "Продолжить" });
  await expect(resume).toBeVisible();

  // A browser-visible failure keeps a retry available, but never leaks the
  // control-plane Origin diagnostic that prompted this regression.
  await page.route("**/api/v1/works/resume", (route) => route.fulfill({
    status: 403,
    contentType: "application/json",
    body: JSON.stringify({ error: { code: "cross_origin_request", message: "browser mutations must be same-origin" } }),
  }));
  await resume.click();
  await expect(page.getByRole("alert")).toHaveText("Продолжение не выполнено. Проверь состояние Factory и повтори попытку.");
  await expect(page.getByText("browser mutations must be same-origin")).toHaveCount(0);
  await expect(resume).toBeVisible();
  await page.unroute("**/api/v1/works/resume");

  // Continue the successful retry through Chromium so scoped SPKI trust owns
  // the TLS request. Spoofed forwarding reaches the fixture proxy, but not its
  // backend request.
  await page.route("**/api/v1/works/resume", (route) => route.continue({
    headers: {
      ...route.request().headers(),
      forwarded: "for=192.0.2.1;host=attacker.example;proto=https",
      "x-forwarded-host": "attacker.example",
      "x-forwarded-proto": "http",
    },
  }));
  const resumedResponsePromise = page.waitForResponse((response) =>
    response.url().endsWith("/api/v1/works/resume") && response.request().method() === "POST",
  );
  await resume.click();
  const resumedResponse = await resumedResponsePromise;
  await page.unroute("**/api/v1/works/resume");
  expect(resumedResponse.status()).toBe(200);
  expect(await resumedResponse.allHeaders()).toMatchObject({
    "x-factory-e2e-client-origin": httpsOrigin,
    "x-factory-e2e-client-forwarded": "for=192.0.2.1;host=attacker.example;proto=https",
    "x-factory-e2e-client-forwarded-host": "attacker.example",
    "x-factory-e2e-client-forwarded-proto": "http",
    "x-factory-e2e-backend-origin": httpsOrigin,
    "x-factory-e2e-backend-forwarded": "<absent>",
    "x-factory-e2e-backend-forwarded-for": "<absent>",
    "x-factory-e2e-backend-real-ip": "<absent>",
    "x-factory-e2e-backend-forwarded-host": new URL(httpsOrigin).host,
    "x-factory-e2e-backend-forwarded-proto": "https",
  });
  await page.reload();
  // The real worker may claim and even finish the resumed task before the
  // next render. The contract here is that the work remains visible and is
  // no longer paused, not that it spends a minimum time in the queue.
  const resumedCard = page.getByText(pausedHTTPSWork, { exact: true })
    .locator("xpath=ancestor::section[contains(@class, 'work-card')]");
  await expect(resumedCard).toBeVisible();
  await expect(resumedCard.getByText("Поставлено на паузу")).toHaveCount(0);
  await page.screenshot({ path: "test-results/screenshots/pause-resume-https-desktop.png", fullPage: true });

  const resumedSettings = await page.evaluate(async () => {
    const response = await fetch("/api/v1/settings/pilot");
    if (!response.ok) throw new Error(`pilot settings returned ${response.status}`);
    return response.json() as Promise<{ settings: { stopped_pipelines: string[] } }>;
  });
  expect(resumedSettings.settings.stopped_pipelines).not.toContain(pausedHTTPSWork);

  const completed = await page.evaluate(async (title) => {
    const response = await fetch("/api/v1/works/resume", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    return { status: response.status, body: await response.json() };
  }, completedHTTPSWork);
  expect(completed.status).toBe(409);
  expect(completed.body as { error: { code: string } }).toMatchObject({
    error: { code: "pipeline_completed" },
  });
  const completedSettings = await page.evaluate(async () => {
    const response = await fetch("/api/v1/settings/pilot");
    if (!response.ok) throw new Error(`pilot settings returned ${response.status}`);
    return response.json() as Promise<{ settings: { stopped_pipelines: string[] } }>;
  });
  expect(completedSettings.settings.stopped_pipelines).not.toContain(completedHTTPSWork);

  await page.goto("/work");
  const completedCard = page.locator("section.work-card")
    .filter({ has: page.getByText(completedHTTPSWork, { exact: true }) })
    .filter({ has: page.getByText("Ожидает слияния и выпуска", { exact: true }) });
  await expect(completedCard).toBeVisible();
  await expect(completedCard.getByText("Поставлено на паузу")).toHaveCount(0);
  await expect(completedCard.getByText("Ожидает слияния и выпуска", { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: "test-results/screenshots/pause-resume-https-phone.png", fullPage: true });
});

test("confirms and deletes terminal task history", async ({ page, baseURL }) => {
  const browser = observeBrowser(page);
  await page.goto(`/tasks/${identifiers.succeededTask}`);
  await expect(page.getByRole("heading", { name: "Ship the stable API client" })).toBeVisible();
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: "Delete history" }).click();
  await expect(page.getByText(/Permanently delete this task, prompt, attempts, and events/)).toBeVisible();
  await page.getByRole("button", { name: "Confirm delete" }).click();
  await expect(page).toHaveURL("/work");
  await expect(page.getByText("Ship the stable API client")).toHaveCount(0);
  browser.assertClean();

  const api = await request.newContext({ baseURL: baseURL, ignoreHTTPSErrors: true });
  const response = await api.get(`/api/v1/tasks/${identifiers.succeededTask}`);
  expect(response.status()).toBe(404);
  await api.dispose();
});

test("@critical shows parallel worker capacity and current work", async ({ page, baseURL }) => {
  const browser = observeBrowser(page);
  if (runningHeartbeat) clearInterval(runningHeartbeat);
  const heartbeat = await fixtureAPI!.put(
    `/api/v1/attempts/${identifiers.runningAttempt}/heartbeat`,
    { data: { lease_token: identifiers.runningLeaseToken } },
  );
  expect(heartbeat.ok()).toBe(true);
  await fixtureAPI!.dispose();
  fixtureAPI = undefined;
  const api = await request.newContext({ baseURL: baseURL, ignoreHTTPSErrors: true });
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
  await expect(page.getByRole("heading", { name: "Execution" })).toBeVisible();
  await expect(page.getByText("Read only")).toBeVisible();
  await expect(page.getByRole("meter", { name: "Worker concurrency" })).toHaveAttribute("max", "2");
  await expect(page.getByRole("tabpanel")).toContainText("restart the worker");
  const assign = page.getByRole("button", { name: "Назначить работу" });
  await assign.click();
  await expect(page.getByRole("dialog").getByLabel("Worker")).toHaveValue(workerOnline);
  await page.keyboard.press("Escape");
  await expect(assign).toBeFocused();
  browser.assertClean();
});

test("delegates with worker-specific repositories and preserves the task on refresh", async ({ page }) => {
  const browser = observeBrowser(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Поставить задачу" }).first().click();
  const dialog = page.getByRole("dialog", { name: "Delegate task" });
  await dialog.getByLabel("Worker").selectOption(workerOffline);
  await expect(dialog.getByText(/task will queue until it returns/i)).toBeVisible();
  await expect(dialog.getByText("This becomes the Claude Code prompt.")).toBeVisible();
  await expect(dialog.getByLabel("Repository").getByRole("option", { name: /archive/ })).toHaveCount(1);
  await expect(dialog.getByLabel("Repository").locator(`option[value="${identifiers.factoryRepository}"]`)).toBeDisabled();
  await dialog.getByLabel("Title").fill("Durable delegated browser task");
  await dialog.getByLabel("Context").fill("Created in the real UI and stored by the real Go server.");
  await dialog.getByLabel("Repository").selectOption(identifiers.offlineRepository);
  await dialog.getByRole("button", { name: "Delegate task" }).click();
  await expect(page.getByRole("heading", { name: "Durable delegated browser task" })).toBeVisible();
  await expect(page.getByText("Claude Code", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Durable delegated browser task" })).toBeVisible();
  browser.assertClean();
});

test("confirms queued cancellation and explicitly retries a failure", async ({ page }) => {
  const browser = observeBrowser(page);
  await page.goto(`/tasks/${identifiers.queuedTask}`);
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByText("Cancel this task?")).toBeVisible();
  await page.getByRole("button", { name: "Confirm cancel" }).click();
  await expect(page.getByText("Cancelled", { exact: true }).first()).toBeVisible();

  await page.goto(`/tasks/${identifiers.failedTask}`);
  await page.getByRole("button", { name: "Retry task" }).click();
  await expect(page.getByText("Queued", { exact: true }).first()).toBeVisible();
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
  const workNavigation = page.getByRole("button", { name: "Работа", exact: true });
  await expect(workNavigation).toHaveClass(/active/);
  await expect(workNavigation).not.toHaveAttribute("aria-current");
  const events = page.locator(".event-list li");
  await expect(events).toHaveCount(3);
  await expect(events.nth(0)).toContainText("Inspected the control-plane contract.");
  await expect(events.nth(1)).toContainText("Succeeded: npm test");
  await expect(events.nth(2)).toContainText("Running browser verification.");
  await expect(page.getByText("RAW_COMMAND_OUTPUT_SHOULD_NOT_RENDER")).toHaveCount(0);
  await expect(page.getByText("3 updates")).toBeVisible();
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
  await expect(page.getByRole("heading", { name: "Работа", exact: true })).toBeVisible();
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
  const dialog = page.getByRole("dialog", { name: "Delegate task" });
  await dialog.getByLabel("Worker").selectOption(realWorker);
  await dialog.getByLabel("Title").fill("Narrow viewport delegation");
  await dialog.getByLabel("Context").fill("Review the complete narrow task form.");
  await dialog.getByLabel("Repository").selectOption(identifiers.realFactoryRepository);
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

test("keeps live Automation state and activity visible on a phone", async ({ page }) => {
  const browser = observeBrowser(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/automations");

  const liveStatuses = page.getByLabel("Живой статус автоматик");
  await expect(liveStatuses).toBeVisible();
  await expect(liveStatuses.getByText("Нет данных").first()).toBeVisible();
  await expect(liveStatuses.getByText("нет данных").first()).toBeVisible();
  await page.screenshot({ path: "test-results/screenshots/automations-narrow.png", fullPage: true });
  browser.assertClean();
});

test("audits every Factory screen on desktop and phone", async ({ context, baseURL }) => {
  test.setTimeout(240_000);
  const api = await request.newContext({ baseURL: baseURL, ignoreHTTPSErrors: true });
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
    { name: "work", path: "/work", ready: (page) => page.getByRole("heading", { name: "Работа", exact: true }) },
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
    const dialog = page.getByRole("dialog", { name: "Delegate task" });
    await expect(dialog).toBeVisible();
    await dialog.getByLabel("Worker").selectOption(workerOffline);
    await dialog.getByLabel("Repository").selectOption(identifiers.offlineRepository);
    await dialog.getByLabel("Title").fill("Delegate from the full desktop and phone visual audit");
    await dialog.getByLabel("Context").fill("All fields and actions remain reachable without page-level horizontal scrolling.");
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
  await expect(page.getByLabel("Title")).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(delegate).toBeFocused();
  browser.assertClean();
});

test("manages repository routing end to end and preserves add input while polling", async ({ page, baseURL }) => {
  const browser = observeBrowser(page);
  const api = await request.newContext({ baseURL: baseURL, ignoreHTTPSErrors: true });
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
  await expect(page.getByText("Routing disabled")).toBeVisible();

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

  await page.getByRole("button", { name: "Enable repository" }).click();
  await expect(page.getByRole("button", { name: "Disable repository" })).toBeVisible();
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
  const delegate = page.getByRole("dialog", { name: "Delegate task" });
  await delegate.getByLabel("Title").fill("Delegate configured managed repository");
  await delegate.getByLabel("Context").fill("Acquire this repository on the selected worker.");
  await delegate.getByLabel("Worker").selectOption(managedWorker);
  const repositoryPicker = delegate.getByLabel("Repository");
  const managedOption = repositoryPicker.locator("option").filter({ hasText: "github.com/example/browser-managed" });
  await expect(managedOption).toBeEnabled();
  await expect(managedOption).toContainText("acquired on demand");
  await repositoryPicker.selectOption((await managedOption.getAttribute("value"))!);
  await delegate.getByRole("button", { name: "Delegate task" }).click();
  await expect(page.getByRole("heading", { name: "Delegate configured managed repository" })).toBeVisible();
  const delegatedTaskID = new URL(page.url()).pathname.split("/").at(-1)!;
  const delegatedTask = await json<TaskDetail>(await api.get(`/api/v1/tasks/${delegatedTaskID}`));
  expect(delegatedTask.execution.assigned_worker_id).toBe(managedWorker);
  await api.dispose();
  browser.assertClean();
});

test("previews and dispatches one typed GitHub issue Automation without duplication", async ({ page, baseURL }) => {
  const browser = observeBrowser(page);
  const api = await request.newContext({ baseURL: baseURL, ignoreHTTPSErrors: true });
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
  await page.getByRole("button", { name: "Create runbook" }).first().click();
  const workflow = page.getByRole("dialog", { name: "Create runbook" });
  await workflow.getByLabel("Title").fill("E2E issue Automation");
  await workflow.getByLabel("Summary").fill("Dispatch the safe issue fixture.");
  await workflow.getByLabel("Markdown instructions").fill("Fetch the live issue, implement it, and verify the result.");
  await workflow.getByRole("button", { name: "Create runbook" }).click();
  await expect(page.getByRole("heading", { name: "E2E issue Automation" })).toBeVisible();

  await page.getByRole("button", { name: "Automations", exact: true }).click();
  await page.getByRole("button", { name: "Create Automation" }).first().click();
  const automation = page.getByRole("dialog", { name: "Create Automation" });
  await automation.getByLabel("Title").fill("E2E ready issues");
  await automation.getByLabel("Runbook").selectOption({ label: "E2E issue Automation" });
  await automation.getByLabel("Repository").selectOption(identifiers.automationRepository);
  await automation.getByLabel("Context for this Automation").fill("Use only the safe browser fixture repository.");
  await automation.getByRole("button", { name: "Create Automation" }).click();
  await expect(page.getByRole("heading", { name: "E2E ready issues" })).toBeVisible();

  await page.getByRole("button", { name: "Test trigger" }).click();
  await expect(page.getByText("#184 Typed Automation browser fixture")).toBeVisible();
  await expect(page.getByText("Testing creates no task or durable run.")).toBeVisible();
  await expect(page.getByText("No runs yet.")).toBeVisible();

  await page.getByRole("button", { name: "Enable", exact: true }).click();
  await expect(page.getByRole("checkbox", { name: /factory-poller is stopped/ })).toHaveCount(0);
  await page.getByRole("button", { name: "Confirm enable" }).click();
  await expect(page.locator(".automation-health").getByText("healthy", { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".occurrence-list").getByText("#184 Typed Automation browser fixture", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open task" })).toBeVisible();

  const before = await json<{ tasks: Array<{ request_key: string }> }>(await api.get("/api/v1/tasks?limit=200"));
  const automationTasksBefore = before.tasks.filter((task) => task.request_key.includes(":github_issue:184"));
  expect(automationTasksBefore).toHaveLength(1);

  await page.getByRole("button", { name: "Check now" }).click();
  await expect(page.locator(".automation-metrics > div").filter({ hasText: "Matched" }).locator("strong")).toHaveText("2", { timeout: 15_000 });
  const after = await json<{ tasks: Array<{ request_key: string }> }>(await api.get("/api/v1/tasks?limit=200"));
  const automationTasksAfter = after.tasks.filter((task) => task.request_key.includes(":github_issue:184"));
  expect(automationTasksAfter).toHaveLength(1);
  await api.dispose();
  browser.assertClean();
});

test("previews and dispatches one typed GitHub pull-request Automation without duplication", async ({ page, baseURL }) => {
  const browser = observeBrowser(page);
  const api = await request.newContext({ baseURL: baseURL, ignoreHTTPSErrors: true });
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
  await page.getByRole("button", { name: "Create runbook" }).first().click();
  const workflow = page.getByRole("dialog", { name: "Create runbook" });
  await workflow.getByLabel("Title").fill("E2E pull-request review");
  await workflow.getByLabel("Summary").fill("Review the safe pull-request fixture.");
  await workflow.getByLabel("Markdown instructions").fill("Fetch and revalidate the live pull request, review it, and do not merge it.");
  await workflow.getByRole("button", { name: "Create runbook" }).click();
  await expect(page.getByRole("heading", { name: "E2E pull-request review" })).toBeVisible();

  await page.getByRole("button", { name: "Automations", exact: true }).click();
  await page.getByRole("button", { name: "Create Automation" }).first().click();
  const automation = page.getByRole("dialog", { name: "Create Automation" });
  await automation.getByLabel("Title").fill("E2E pull-request Automation");
  await automation.getByLabel("Runbook").selectOption({ label: "E2E pull-request review" });
  await automation.getByLabel("Repository").selectOption(identifiers.automationRepository);
  await automation.getByLabel("Trigger").selectOption("github_pull_request");
  await automation.getByLabel("Required labels").fill("factory:review");
  await automation.getByLabel("Base branches").fill("main");
  await automation.getByLabel("Context for this Automation").fill("Review only the safe synthetic pull request and never merge it.");
  await automation.getByRole("button", { name: "Create Automation" }).click();
  await expect(page.getByRole("heading", { name: "E2E pull-request Automation" })).toBeVisible();

  await page.getByRole("button", { name: "Test trigger" }).click();
  await expect(page.getByText("#185 Typed pull-request Automation browser fixture")).toBeVisible();
  await expect(page.getByText("Testing creates no task or durable run.")).toBeVisible();
  await expect(page.getByText("No runs yet.")).toBeVisible();

  await page.getByRole("button", { name: "Enable", exact: true }).click();
  await expect(page.getByRole("checkbox", { name: /factory-poller is stopped/ })).toHaveCount(0);
  await page.getByRole("button", { name: "Confirm enable" }).click();
  await expect(page.locator(".automation-health").getByText("healthy", { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".occurrence-list").getByText("#185 Typed pull-request Automation browser fixture", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open task" })).toBeVisible();

  const before = await json<{ tasks: Array<{ request_key: string }> }>(await api.get("/api/v1/tasks?limit=200"));
  expect(before.tasks.filter((task) => task.request_key.includes(":github_pull_request:185"))).toHaveLength(1);

  await page.getByRole("button", { name: "Check now" }).click();
  await expect(page.locator(".automation-metrics > div").filter({ hasText: "Matched" }).locator("strong")).toHaveText("2", { timeout: 15_000 });
  const after = await json<{ tasks: Array<{ request_key: string }> }>(await api.get("/api/v1/tasks?limit=200"));
  expect(after.tasks.filter((task) => task.request_key.includes(":github_pull_request:185"))).toHaveLength(1);
  await api.dispose();
  browser.assertClean();
});

test("previews, enables, and runs a schedule Automation through the ordinary task path", async ({ page, baseURL }) => {
  const browser = observeBrowser(page);
  const api = await request.newContext({ baseURL: baseURL, ignoreHTTPSErrors: true });
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
  await page.getByRole("button", { name: "Create runbook" }).first().click();
  const workflow = page.getByRole("dialog", { name: "Create runbook" });
  await workflow.getByLabel("Title").fill("E2E scheduled maintenance");
  await workflow.getByLabel("Summary").fill("Run safe scheduled maintenance.");
  await workflow.getByLabel("Markdown instructions").fill("Inspect the fixture repository and report the scheduled maintenance result.");
  await workflow.getByRole("button", { name: "Create runbook" }).click();
  await expect(page.getByRole("heading", { name: "E2E scheduled maintenance" })).toBeVisible();

  await page.getByRole("button", { name: "Automations", exact: true }).click();
  await page.getByRole("button", { name: "Create Automation" }).first().click();
  const automation = page.getByRole("dialog", { name: "Create Automation" });
  await automation.getByLabel("Title").fill("E2E schedule Automation");
  await automation.getByLabel("Runbook").selectOption({ label: "E2E scheduled maintenance" });
  await automation.getByLabel("Repository").selectOption(identifiers.automationRepository);
  await automation.getByLabel("Trigger").selectOption("schedule");
  await automation.getByLabel("Frequency").selectOption("custom");
  await automation.getByText("Expert settings").click();
  await automation.getByLabel("Cron (five fields)").fill("0 0 1 JAN *");
  await automation.getByLabel("Timezone").fill("Europe/London");
  await automation.getByLabel("Context for this Automation").fill("Use only the safe synthetic repository.");
  await automation.getByRole("button", { name: "Create Automation" }).click();
  await expect(page.getByRole("heading", { name: "E2E schedule Automation" })).toBeVisible();

  await page.getByRole("button", { name: "Test trigger" }).click();
  await expect(page.getByText(/next matching UTC instant/i)).toBeVisible();
  await expect(page.getByText("No runs yet.")).toBeVisible();
  await page.getByRole("button", { name: "Enable", exact: true }).click();
  await expect(page.getByRole("checkbox", { name: /factory-poller is stopped/ })).toHaveCount(0);
  await page.getByRole("button", { name: "Confirm enable" }).click();
  const nextDue = page.getByText("Next due UTC").locator("..").locator("dd");
  await expect.poll(async () => {
    const instant = Date.parse((await nextDue.textContent()) ?? "");
    return Number.isFinite(instant) && instant > Date.now();
  }).toBe(true);

  await page.getByRole("button", { name: "Run now" }).click();
  await expect(page.locator(".occurrence-list").getByText("Run now", { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("button", { name: "Open task" })).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".automation-latest-task").getByText("Run now", { exact: true })).toBeVisible({ timeout: 15_000 });
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
  const api = await request.newContext({ baseURL: baseURL, ignoreHTTPSErrors: true });
  const legacyRoot = `${process.cwd()}/test-results/legacy-poller`;
  await page.goto("/automations");
  await page.getByRole("button", { name: "Migrate legacy poller" }).click();
  const migration = page.getByRole("dialog", { name: "Migrate legacy poller" });
  await migration.getByLabel("Legacy poller.toml").fill(`${legacyRoot}/poller.toml`);
  await migration.getByLabel("Legacy data home").fill(legacyRoot);
  await migration.getByLabel("Original working directory").fill(legacyRoot);
  await migration.getByRole("checkbox", { name: /I stopped every factory-poller process/ }).check();
  const previewResponse = page.waitForResponse((response) =>
    response.url().endsWith("/api/v1/migrations/legacy-poller/preview") && response.request().method() === "POST",
  );
  await migration.getByRole("button", { name: "Preview locked snapshot" }).click();
  const previewResult = await previewResponse;
  expect(previewResult.ok(), await previewResult.text()).toBe(true);

  await expect(migration.getByText("1 supported · 0 unsupported")).toBeVisible();
  await expect(migration.getByText("0 submitted · 1 pending", { exact: true })).toBeVisible();
  await expect(migration.getByText(`${legacyRoot}/poller/poller.sqlite3`, { exact: true })).toBeVisible();
  await expect(migration.getByText(/Repository mapping:/)).toContainText("github.com/example/automation-fixture");
  await migration.getByLabel("Runbook title").fill("E2E imported legacy workflow");
  await migration.getByLabel("Automation title").fill("E2E imported legacy issues");
  const importedResponse = page.waitForResponse((response) =>
    response.url().endsWith("/api/v1/migrations/legacy-poller/import") && response.request().method() === "POST",
  );
  await migration.getByRole("button", { name: "Import disabled Automations" }).click();
  const status = await (await importedResponse).json() as {
    id: string;
    automations: Array<{ id: string }>;
  };
  await expect(migration.getByText("1 unresolved")).toBeVisible();
  await expect(migration.getByRole("button", { name: "Finalize and archive" })).toBeDisabled();

  const blockedEnable = await api.put(`/api/v1/automations/${status.automations[0].id}/enabled`, {
    data: { enabled: true },
  });
  expect(blockedEnable.status()).toBe(409);
  expect(await blockedEnable.text()).toContain("migration_not_finalized");

  await page.reload();
  await page.getByRole("button", { name: "Migrate legacy poller" }).click();
  await expect(migration.getByText("1 unresolved")).toBeVisible();
  const recoveredResume = migration.getByRole("button", { name: "Resume" });
  await expect(recoveredResume).toBeDisabled();
  await migration.getByRole("checkbox", { name: /I reconfirmed every factory-poller process/ }).check();
  await expect(recoveredResume).toBeEnabled();
  await recoveredResume.click();
  await expect(migration.getByText("0 unresolved")).toBeVisible();
  await migration.getByRole("button", { name: "Finalize and archive" }).click();
  await expect(migration.getByText("Migration finalized")).toBeVisible();
  await expect(migration.getByText(`${legacyRoot}/archive/poller/${status.id}`)).toBeVisible();

  const tasks = await json<{ tasks: Array<{ request_key: string }> }>(await api.get("/api/v1/tasks?limit=200"));
  expect(tasks.tasks.filter((task) => task.request_key === "legacy-browser-request-187")).toHaveLength(1);
  await expect(migration.getByRole("button", { name: "Review E2E imported legacy issues" })).toBeVisible();
  await api.dispose();
  browser.assertClean();
});

test("edits pilot settings from the Settings screen", async ({ page }) => {
  const browser = observeBrowser(page);
  const settings = page.locator(".settings-page");
  await page.goto("/settings");
  await expect(settings.getByRole("heading", { name: "Настройки", exact: true })).toBeVisible();
  await expect(settings.getByText("Цепочка моделей")).toBeVisible();
  await expect(settings.getByLabel("Репозиторий продукта")).toHaveValue("github.com/example/factory");
  await expect(settings.getByLabel("Тип источника")).toHaveValue("factory");
  const poll = settings.getByLabel("Интервал проверки, секунд");
  await expect(poll).toHaveValue("10");
  await poll.fill("15");
  const response = page.waitForResponse((result) =>
    result.url().endsWith("/api/v1/settings/pilot") && result.request().method() === "PUT",
  );
  const saveSettings = settings.getByRole("button", { name: "Сохранить настройки", exact: true });
  await expect(saveSettings).toHaveCount(1);
  await saveSettings.click();
  expect((await response).ok()).toBe(true);
  await expect(settings.getByText(/Настройки сохранены/)).toBeVisible();
  await page.reload();
  const reloadedSettings = page.locator(".settings-page");
  await expect(reloadedSettings.getByLabel("Интервал проверки, секунд")).toHaveValue("15");
  await expect(reloadedSettings.getByLabel("Репозиторий продукта")).toHaveValue("github.com/example/factory");
  await expect(reloadedSettings.getByLabel("Тип источника")).toHaveValue("factory");
  browser.assertClean();
});
