import { pathToFileURL } from "node:url";
import { createRequire } from "node:module";
import path from "node:path";

function loadChromium(runtimeRoot = process.env.FACTORY_BROWSER_RUNTIME ?? path.dirname(path.dirname(new URL(import.meta.url).pathname))) {
  if (!path.isAbsolute(runtimeRoot)) throw new Error("absolute FACTORY_BROWSER_RUNTIME is required");
  return createRequire(path.join(runtimeRoot, "package.json"))("playwright").chromium;
}

export async function renderReport(html, outputPath, launcher = process.env.FACTORY_BROWSER_LAUNCHER, runtimeRoot) {
  if (!launcher || !path.isAbsolute(launcher)) throw new Error("absolute FACTORY_BROWSER_LAUNCHER is required");
  const browser = await loadChromium(runtimeRoot).launch({ headless: true, executablePath: launcher, chromiumSandbox: true });
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
  process.stdin.setEncoding("utf8");
  let html = "";
  for await (const chunk of process.stdin) html += chunk;
  await renderReport(html, outputPath);
}
