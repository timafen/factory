import { existsSync } from "node:fs";
import { defineConfig, devices } from "@playwright/test";

const defaultBrowserLauncher = "/usr/local/libexec/factory/factory-browser-sandbox";
const intakePython = process.env.FACTORY_INTAKE_PYTHON ?? "/opt/factory-data/intake/venv/bin/python";
export const testWorkerBootstrapCredential =
  process.env.FACTORY_E2E_WORKER_BOOTSTRAP_CREDENTIAL ??
  "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";

export function serverBrowserLaunchOptions(
  launcher = process.env.FACTORY_BROWSER_LAUNCHER ?? defaultBrowserLauncher,
) {
  if (!existsSync(launcher)) return undefined;
  return { executablePath: launcher, chromiumSandbox: true };
}

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 45_000,
  expect: { timeout: 8_000 },
  reporter: [["list"], ["html", { open: "never" }]],
  outputDir: "test-results/artifacts",
  use: {
    baseURL: "http://127.0.0.1:17437",
    launchOptions: serverBrowserLaunchOptions(),
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 1000 } },
    },
  ],
  webServer: [
    {
      command: "node e2e/server.mjs",
      url: "http://127.0.0.1:17437/healthz",
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        FACTORY_E2E_WORKER_BOOTSTRAP_CREDENTIAL: testWorkerBootstrapCredential,
      },
    },
    {
      command: `${intakePython} e2e/intake-fixture.py`,
      url: "http://127.0.0.1:17438/healthz",
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
});
