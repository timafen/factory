import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
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
  await renderReport("<h1>Ежедневный отчёт</h1><img alt='Снимок до' src='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/wHwAF/gL+V9ZqAAAAAElFTkSuQmCC'><img src='https://invalid.example/nope.png'>", output);
  const bytes = await readFile(output);
  assert.equal(bytes.subarray(0, 5).toString(), "%PDF-");
});
