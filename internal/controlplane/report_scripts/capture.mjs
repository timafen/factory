import { mkdir, rename, rm } from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";

const launcher = process.env.FACTORY_BROWSER_LAUNCHER;
if (!launcher || !path.isAbsolute(launcher)) throw new Error("absolute FACTORY_BROWSER_LAUNCHER is required");
let chromium;
try {
  ({ chromium } = await import("playwright"));
} catch {
  const payload = process.env.FACTORY_BROWSER_PAYLOAD || "/opt/factory-data/releases/factory/browser-runtime/current";
  ({ chromium } = createRequire(path.join(payload, "web", "package.json"))("playwright"));
}

const target = JSON.parse(process.argv[2] ?? "null");
const outputPath = process.argv[3];
if (!target || !outputPath) throw new Error("capture target and output path are required");
const host = new URL(target.url).hostname.toLowerCase();
const allowedHosts = new Set(["factory.timafen.com", "staging-automation.tarser.net", "localhost", "127.0.0.1", "::1"]);
if (!allowedHosts.has(host)) throw new Error(`visual target host is not allowed: ${host}`);
const browser = await chromium.launch({ headless: true, executablePath: launcher, chromiumSandbox: true });
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
