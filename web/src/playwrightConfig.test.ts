import { closeSync, mkdtempSync, openSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
  createE2EServerAddress,
  createPlaywrightConfig,
  serverBrowserLaunchOptions,
  testWorkerBootstrapCredential,
} from "../playwright.config";

const temporaryDirectories: string[] = [];

afterEach(() => {
  for (const directory of temporaryDirectories.splice(0)) {
    rmSync(directory, { recursive: true, force: true });
  }
});

describe("server browser launcher", () => {
  it("provides a valid isolated worker bootstrap credential to the browser fixture", () => {
    expect(testWorkerBootstrapCredential).toMatch(/^[A-Za-z0-9_-]{43}$/);
  });

  it("uses an installed launcher and keeps the Chromium sandbox enabled", () => {
    const directory = mkdtempSync(join(tmpdir(), "factory-browser-launcher-"));
    temporaryDirectories.push(directory);
    const launcher = join(directory, "factory-browser-sandbox");
    closeSync(openSync(launcher, "w"));

    expect(serverBrowserLaunchOptions(launcher)).toEqual({
      executablePath: launcher,
      chromiumSandbox: true,
    });
  });

  it("leaves ordinary development and CI Playwright discovery unchanged", () => {
    expect(serverBrowserLaunchOptions("/missing/factory-browser-sandbox")).toBeUndefined();
  });
});

describe("browser fixture server address", () => {
  it("uses an explicit valid port for every Playwright consumer", async () => {
    const config = await createPlaywrightConfig("24567", "24568");
    const reloadedConfig = await createPlaywrightConfig(
      process.env.FACTORY_E2E_PORT,
      process.env.FACTORY_INTAKE_E2E_PORT,
    );

    expect(config.use?.baseURL).toBe("http://127.0.0.1:24567");
    expect(reloadedConfig.use?.baseURL).toBe(config.use?.baseURL);
    expect(process.env.FACTORY_INTAKE_E2E_ORIGIN).toBe("http://127.0.0.1:24568");
    expect(config.webServer).toEqual(expect.arrayContaining([
      expect.objectContaining({
        command: "node e2e/server.mjs",
        url: "http://127.0.0.1:24567/healthz",
        env: { FACTORY_E2E_PORT: "24567" },
      }),
      expect.objectContaining({
        command: expect.stringContaining("intake-fixture.py"),
        url: "http://127.0.0.1:24568/healthz",
        env: { FACTORY_INTAKE_E2E_PORT: "24568" },
      }),
    ]));
  });

  it.each(["", "0", "65536", "12.5", "not-a-port"]) (
    "rejects invalid FACTORY_E2E_PORT value %j",
    async (value) => {
      await expect(createE2EServerAddress(value)).rejects.toThrow(
        "FACTORY_E2E_PORT must be an integer from 1 to 65535",
      );
    },
  );

  it("allocates distinct usable loopback ports for independent runs", async () => {
    const [first, second] = await Promise.all([
      createE2EServerAddress(),
      createE2EServerAddress(),
    ]);

    expect(first.port).toBeGreaterThan(0);
    expect(first.port).toBeLessThanOrEqual(65_535);
    expect(second.port).not.toBe(first.port);
    expect(first.origin).toBe(`http://127.0.0.1:${first.port}`);
    expect(second.origin).toBe(`http://127.0.0.1:${second.port}`);
  });
});
