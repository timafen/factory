import { mkdir, rename, rm } from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";

let chromium;
try {
  ({ chromium } = await import("playwright"));
} catch {
  ({ chromium } = createRequire(path.join(process.cwd(), "web", "package.json"))("playwright"));
}

const target = JSON.parse(process.argv[2] ?? "null");
const outputPath = process.argv[3];
if (!target || !outputPath) throw new Error("capture target and output path are required");
const browser = await chromium.launch({ headless: true });
const temporary = `${outputPath}.part-${process.pid}`;
try {
  const page = await browser.newPage({ viewport: { width: target.viewport_width, height: target.viewport_height } });
  await page.goto(target.url, { waitUntil: "networkidle", timeout: 60_000 });
  if (/\/login(?:[/?#]|$)/i.test(new URL(page.url()).pathname)) throw new Error("страница перенаправила на вход");
  await page.getByText(target.state_text, { exact: true }).waitFor({ state: "visible", timeout: 30_000 });
  await mkdir(path.dirname(outputPath), { recursive: true, mode: 0o700 });
  await page.screenshot({ path: temporary, type: "png", fullPage: false });
  await rename(temporary, outputPath);
} finally {
  await rm(temporary, { force: true });
  await browser.close();
}
