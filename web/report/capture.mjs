import { mkdir, rename, rm } from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";

function loadChromium(runtimeRoot = process.env.FACTORY_BROWSER_RUNTIME ?? path.dirname(path.dirname(new URL(import.meta.url).pathname))) {
	if (!path.isAbsolute(runtimeRoot)) throw new Error("absolute FACTORY_BROWSER_RUNTIME is required");
	return createRequire(path.join(runtimeRoot, "package.json"))("playwright").chromium;
}

export async function captureVisual(target, outputPath, launcher = process.env.FACTORY_BROWSER_LAUNCHER, runtimeRoot) {
	if (!target?.url || !target?.state_text) throw new Error("URL and exact visible state text are required");
	if (!launcher || !path.isAbsolute(launcher)) throw new Error("absolute FACTORY_BROWSER_LAUNCHER is required");
	const host = new URL(target.url).hostname.toLowerCase();
	const allowedHosts = new Set(["factory.timafen.com", "staging-automation.tarser.net", "localhost", "127.0.0.1", "::1"]);
	if (!allowedHosts.has(host)) throw new Error(`visual target host is not allowed: ${host}`);
	const username = process.env.FACTORY_BROWSER_BASIC_AUTH_USERNAME;
	const password = process.env.FACTORY_BROWSER_BASIC_AUTH_PASSWORD;
	if ((username === undefined) !== (password === undefined)) throw new Error("both Factory Basic Auth variables must be set together");
	const browser = await loadChromium(runtimeRoot).launch({ headless: true, executablePath: launcher, chromiumSandbox: true });
  const temporary = `${outputPath}.tmp-${process.pid}`;
  try {
    const context = await browser.newContext({ viewport: { width: target.viewport_width, height: target.viewport_height }, ...(host === "factory.timafen.com" && username !== undefined ? { httpCredentials: { username, password } } : {}) });
    const page = await context.newPage();
    await page.goto(target.url, { waitUntil: "networkidle" });
    if (/\/login(?:[/?#]|$)/i.test(new URL(page.url()).pathname)) throw new Error("страница перенаправила на вход");
    await page.getByText(target.state_text, { exact: true }).waitFor({ state: "visible" });
    await mkdir(path.dirname(outputPath), { recursive: true, mode: 0o700 });
    await page.screenshot({ path: temporary, type: "png", fullPage: false });
    await rename(temporary, outputPath);
		await context.close();
  } finally { await rm(temporary, { force: true }); await browser.close(); }
}
