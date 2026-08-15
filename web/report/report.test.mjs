import test from "node:test";
import assert from "node:assert/strict";
import { chmod, mkdir, readFile, writeFile } from "node:fs/promises";
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
  const result = spawnSync(process.execPath, [script, path.join(dir, "daily.pdf")], {
    cwd: fileURLToPath(new URL("../../", import.meta.url)),
    input: "<h1>Ежедневный отчёт</h1>",
    encoding: "utf8",
    env: { ...process.env, FACTORY_BROWSER_LAUNCHER: "" },
  });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /absolute FACTORY_BROWSER_LAUNCHER is required/);
});

test("production renderer loads Playwright only from the durable browser payload", async () => {
  const dir = await mkdtemp(path.join(tmpdir(), "factory-browser-payload-"));
  const payload = path.join(dir, "payload");
  const unrelatedCwd = path.join(dir, "checkout-was-removed");
  const output = path.join(dir, "daily.pdf");
  const launcher = path.join(dir, "factory-browser-sandbox");
  await mkdir(path.join(payload, "web", "node_modules", "playwright"), { recursive: true });
  await mkdir(unrelatedCwd);
  await writeFile(path.join(payload, "web", "package.json"), '{"type":"module"}\n');
  await writeFile(path.join(payload, "web", "node_modules", "playwright", "package.json"),
    '{"name":"playwright","main":"index.cjs"}\n');
  await writeFile(path.join(payload, "web", "node_modules", "playwright", "index.cjs"), `
const fs = require("node:fs");
exports.chromium = { launch: async options => {
  if (!options.chromiumSandbox || options.executablePath !== process.env.FACTORY_BROWSER_LAUNCHER) throw new Error("unsafe launch");
  return { newPage: async () => ({ route: async () => {}, setContent: async () => {}, pdf: async ({path}) => fs.writeFileSync(path, "%PDF-fixture") }), close: async () => {} };
} };
`);
  await writeFile(launcher, "#!/bin/sh\nexit 0\n");
  await chmod(launcher, 0o755);
  const script = fileURLToPath(new URL("../../internal/controlplane/report_scripts/render.mjs", import.meta.url));
  const result = spawnSync(process.execPath, [script, output], {
    cwd: unrelatedCwd,
    input: "<h1>Ежедневный отчёт</h1>",
    encoding: "utf8",
    env: { ...process.env, FACTORY_BROWSER_PAYLOAD: payload, FACTORY_BROWSER_LAUNCHER: launcher },
  });
  assert.equal(result.status, 0, result.stderr);
  assert.equal((await readFile(output)).subarray(0, 5).toString(), "%PDF-");
});
