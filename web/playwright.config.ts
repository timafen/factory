import { existsSync } from "node:fs";
import { defineConfig, devices } from "@playwright/test";

const defaultBrowserLauncher = "/usr/local/libexec/factory/factory-browser-sandbox";

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
  webServer: {
    command: "node e2e/server.mjs",
    url: "http://127.0.0.1:17437/healthz",
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
