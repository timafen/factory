import { chromium } from "playwright";

export async function renderReport(html, outputPath) {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    await page.route("**/*", route => route.abort("blockedbyclient"));
    await page.setContent(html, { waitUntil: "domcontentloaded" });
    await page.pdf({ path: outputPath, format: "A4", printBackground: true });
  } finally { await browser.close(); }
}
