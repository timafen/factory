import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { createServer } from "node:http";
import { once } from "node:events";
import { captureVisual } from "./capture.mjs";
import { renderReport } from "./render.mjs";

test("capture requires the isolated launcher, Chromium sandbox, and an allowed host", async () => {
  const source = await readFile(new URL("./capture.mjs", import.meta.url), "utf8");
  assert.match(source, /executablePath:\s*launcher/);
  assert.match(source, /chromiumSandbox:\s*true/);
  assert.match(source, /FACTORY_BROWSER_LAUNCHER/);
  assert.match(source, /allowedHosts\.has\(host\)/);
  assert.match(source, /FACTORY_BROWSER_RUNTIME/);
});

test("renderer uses the same installed launcher, sandbox, and runtime", async () => {
  const source = await readFile(new URL("./render.mjs", import.meta.url), "utf8");
  assert.match(source, /executablePath:\s*launcher/);
  assert.match(source, /chromiumSandbox:\s*true/);
  assert.match(source, /FACTORY_BROWSER_RUNTIME/);
  assert.match(source, /route\("\*\*\/\*"/);
});

test("renderer produces a PDF with an inline screenshot without fetching external resources", async (context) => {
  const dir = await mkdtemp(path.join(tmpdir(), "factory-report-"));
  const output = path.join(dir, "daily.pdf");
  const launcher = process.env.FACTORY_BROWSER_LAUNCHER;
  if (!launcher) return context.skip("installed Chromium launcher is unavailable");
  await renderReport("<h1>Ежедневный отчёт</h1><img alt='Снимок до' src='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/wHwAF/gL+V9ZqAAAAAElFTkSuQmCC'><img src='https://invalid.example/nope.png'>", output, launcher);
  const bytes = await readFile(output);
  assert.equal(bytes.subarray(0, 5).toString(), "%PDF-");
});

test("capture uses the installed Chromium runtime for a late after screenshot", async (context) => {
  const launcher = process.env.FACTORY_BROWSER_LAUNCHER;
  if (!launcher) return context.skip("installed Chromium launcher is unavailable");
  const server = createServer((_request, response) => {
    response.setHeader("content-type", "text/html; charset=utf-8");
    response.end("<!doctype html><title>Factory</title><main>После готово</main>");
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  try {
    const address = server.address();
    const output = path.join(await mkdtemp(path.join(tmpdir(), "factory-capture-")), "after.png");
    await captureVisual({
      url: `http://127.0.0.1:${address.port}/reports`,
      state_text: "После готово",
      viewport_width: 800,
      viewport_height: 600,
    }, output, launcher);
    const bytes = await readFile(output);
    assert.equal(bytes.subarray(1, 4).toString(), "PNG");
  } finally {
    server.close();
    await once(server, "close");
  }
});
