import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";

let chromium;
try {
  ({ chromium } = await import("playwright"));
} catch {
  ({ chromium } = createRequire(path.join(process.cwd(), "web", "package.json"))("playwright"));
}

const outputPath = process.argv[2];
if (!outputPath) throw new Error("output PDF path is required");
const html = await readFile(0, "utf8");
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  await page.route(/^https?:/, route => route.abort("blockedbyclient"));
  await page.setContent(html, { waitUntil: "domcontentloaded" });
  await page.pdf({ path: outputPath, format: "A4", printBackground: true });
} finally {
  await browser.close();
}
