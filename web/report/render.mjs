import { chromium } from "playwright";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

export async function renderReport(html, outputPath, launcher = process.env.FACTORY_BROWSER_LAUNCHER) {
  if (!launcher || !path.isAbsolute(launcher)) throw new Error("absolute FACTORY_BROWSER_LAUNCHER is required");
  const browser = await chromium.launch({ headless: true, executablePath: launcher, chromiumSandbox: true });
  try {
    const page = await browser.newPage();
    await page.route("**/*", route => route.abort("blockedbyclient"));
    await page.setContent(html, { waitUntil: "domcontentloaded" });
    await page.pdf({ path: outputPath, format: "A4", printBackground: true });
  } finally { await browser.close(); }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const outputPath = process.argv[2];
  if (!outputPath) throw new Error("output PDF path is required");
  const html = await readFile("/dev/stdin", "utf8");
  await renderReport(html, outputPath);
}
