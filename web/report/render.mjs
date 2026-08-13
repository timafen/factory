import { chromium } from "playwright";
import { readFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";

export async function renderReport(html, outputPath) {
  const browser = await chromium.launch({ headless: true });
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
  const html = await readFile(0, "utf8");
  await renderReport(html, outputPath);
}
