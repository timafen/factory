import { closeSync, mkdtempSync, openSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
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
