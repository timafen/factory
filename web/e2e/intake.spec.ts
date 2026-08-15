import { expect, test, type Page } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { createServer } from "node:net";
import { resolve } from "node:path";

let fixture: ChildProcess | undefined;
let intakeOrigin = "";

async function freePort(): Promise<number> {
  return new Promise((resolvePort, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (!address || typeof address === "string") return reject(new Error("No fixture port"));
      server.close((error) => error ? reject(error) : resolvePort(address.port));
    });
  });
}

async function waitForFixture(origin: string) {
  for (let attempt = 0; attempt < 80; attempt += 1) {
    if (fixture?.exitCode !== null) throw new Error(`intake fixture exited with ${fixture?.exitCode}`);
    try {
      const response = await fetch(`${origin}/plan`);
      if (response.ok) return;
    } catch {
      // The ASGI listener is still starting.
    }
    await new Promise((resolveWait) => setTimeout(resolveWait, 100));
  }
  throw new Error("intake fixture did not start");
}

async function expectLayout(page: Page) {
  const result = await page.evaluate(() => {
    const root = document.documentElement;
    const clipped = [...document.querySelectorAll<HTMLElement>("a,button,summary,input,select,textarea")]
      .filter((element) => {
        const rect = element.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0 && (rect.left < -1 || rect.right > root.clientWidth + 1);
      })
      .map((element) => element.outerHTML.slice(0, 100));
    return { overflow: root.scrollWidth - root.clientWidth, clipped };
  });
  expect(result.overflow).toBeLessThanOrEqual(1);
  expect(result.clipped).toEqual([]);
}

test.beforeAll(async () => {
  const port = await freePort();
  intakeOrigin = `http://127.0.0.1:${port}`;
  fixture = spawn("python3", [resolve(process.cwd(), "e2e/intake-fixture.py"), "--port", String(port)], {
    cwd: resolve(process.cwd(), ".."),
    stdio: ["ignore", "pipe", "pipe"],
  });
  await waitForFixture(intakeOrigin);
});

test.afterAll(async () => {
  if (!fixture || fixture.exitCode !== null) return;
  await new Promise<void>((resolveStop) => {
    fixture!.once("exit", () => resolveStop());
    fixture!.kill("SIGTERM");
  });
});

test("shows the real intake Plan and Alerts", async ({ context }) => {
  for (const viewport of [
    { name: "desktop", width: 1440, height: 1000 },
    { name: "phone", width: 390, height: 844 },
  ] as const) {
    const page = await context.newPage();
    await page.setViewportSize(viewport);
    await page.goto(`${intakeOrigin}/plan`);
    await expect(page.getByRole("heading", { name: "План" })).toBeVisible();
    await expect(page.getByText("Проверить компактный План")).toBeVisible();
    await expect(page.getByRole("button", { name: "Завести задачу" })).toBeVisible();
    const reason = page.getByText(/Полное обоснование/);
    await expect(reason).toBeHidden();
    await page.getByText("Показать обоснование").click();
    await expect(reason).toBeVisible();
    await expectLayout(page);
    await page.screenshot({ path: `test-results/screenshots/plan-${viewport.name}.png`, fullPage: true });

    await page.goto(`${intakeOrigin}/alerts`);
    await expect(page.getByRole("heading", { name: "Уведомления" })).toBeVisible();
    await expect(page.locator("details.alert-group[open]")).toHaveCount(0);
    await page.getByRole("link", { name: "работа встала" }).click();
    const group = page.locator("details.alert-group[open]");
    await expect(group.getByText("Работа остановилась")).toBeVisible();
    await expect(group.getByText(/тихое: группа выключена/)).toBeVisible();
    await expectLayout(page);
    await page.screenshot({ path: `test-results/screenshots/alerts-${viewport.name}.png`, fullPage: true });
    await page.close();
  }
});
