import { createRequire } from "node:module";
import path from "node:path";

const outputPath = process.argv[2];
if (!outputPath) throw new Error("output PDF path is required");
const launcher = process.env.FACTORY_BROWSER_LAUNCHER;
if (!launcher || !path.isAbsolute(launcher)) throw new Error("absolute FACTORY_BROWSER_LAUNCHER is required");
const browserPayload = process.env.FACTORY_BROWSER_PAYLOAD
  ?? "/opt/factory-data/releases/factory/browser-current";
if (!path.isAbsolute(browserPayload)) throw new Error("absolute FACTORY_BROWSER_PAYLOAD is required");
const { chromium } = createRequire(path.join(browserPayload, "web", "package.json"))("playwright");
process.stdin.setEncoding("utf8");
let html = "";
for await (const chunk of process.stdin) html += chunk;
const browser = await chromium.launch({ headless: true, executablePath: launcher, chromiumSandbox: true });
try {
  const page = await browser.newPage();
  await page.route(/^https?:/, route => route.abort("blockedbyclient"));
  await page.setContent(html, { waitUntil: "domcontentloaded" });
  await page.pdf({ path: outputPath, format: "A4", printBackground: true });
} finally {
  await browser.close();
}
