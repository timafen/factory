import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { renderReport } from "./render.mjs";

test("capture requires the isolated launcher, Chromium sandbox, and an allowed host", async () => {
  const source = await readFile(new URL("./capture.mjs", import.meta.url), "utf8");
  assert.match(source, /executablePath:\s*launcher/);
  assert.match(source, /chromiumSandbox:\s*true/);
  assert.match(source, /FACTORY_BROWSER_LAUNCHER/);
  assert.match(source, /allowedHosts\.has\(host\)/);
});

test("renderer produces a PDF with an inline screenshot without fetching external resources", async () => {
  const dir = await mkdtemp(path.join(tmpdir(), "factory-report-"));
  const output = path.join(dir, "daily.pdf");
  await renderReport("<h1>Ежедневный отчёт</h1><img alt='Снимок до' src='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/wHwAF/gL+V9ZqAAAAAElFTkSuQmCC'><img src='https://invalid.example/nope.png'>", output, chromium.executablePath());
  const bytes = await readFile(output);
  assert.equal(bytes.subarray(0, 5).toString(), "%PDF-");
});

test("renderer refuses an unavailable isolated launcher", async () => {
  const dir = await mkdtemp(path.join(tmpdir(), "factory-report-"));
  await assert.rejects(
    renderReport("<h1>Ежедневный отчёт</h1>", path.join(dir, "daily.pdf"), path.join(dir, "missing-browser")),
    /executable doesn't exist|Failed to launch|browserType\.launch/
  );
});

test("production renderer refuses to run without the isolated launcher", async () => {
  const dir = await mkdtemp(path.join(tmpdir(), "factory-report-"));
  const script = fileURLToPath(new URL("../../internal/controlplane/report_scripts/render.mjs", import.meta.url));
  const source = await readFile(script, "utf8");
  assert.match(source, /FACTORY_BROWSER_PAYLOAD/);
  assert.match(source, /browser-runtime\/current/);
  const result = spawnSync(process.execPath, [script, path.join(dir, "daily.pdf")], {
    cwd: fileURLToPath(new URL("../../", import.meta.url)),
    input: "<h1>Ежедневный отчёт</h1>",
    encoding: "utf8",
    env: { ...process.env, FACTORY_BROWSER_LAUNCHER: "" },
  });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /absolute FACTORY_BROWSER_LAUNCHER is required/);
});
