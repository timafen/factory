import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";

const launcher = process.env.FACTORY_BROWSER_LAUNCHER;
if (!launcher || !path.isAbsolute(launcher)) throw new Error("absolute FACTORY_BROWSER_LAUNCHER is required");
let chromium;
try {
  ({ chromium } = await import("playwright"));
} catch {
  const payload = process.env.FACTORY_BROWSER_PAYLOAD || "/opt/factory-data/releases/factory/browser-runtime/current";
  ({ chromium } = createRequire(path.join(payload, "web", "package.json"))("playwright"));
}

const outputPath = process.argv[2];
if (!outputPath) throw new Error("output PDF path is required");
const html = await readFile("/dev/stdin", "utf8");
const browser = await chromium.launch({ headless: true, executablePath: launcher, chromiumSandbox: true });
try {
  const page = await browser.newPage();
  await page.route(/^https?:/, route => route.abort("blockedbyclient"));
  await page.setContent(html, { waitUntil: "domcontentloaded" });
  await page.pdf({ path: outputPath, format: "A4", printBackground: true });
} finally {
  await browser.close();
}
