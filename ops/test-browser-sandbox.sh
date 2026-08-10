#!/bin/bash
# Release-time smoke for the isolated Factory browser. Basic Auth credentials
# are optional and are read only from the environment, never from arguments.
set -euo pipefail

launcher=${FACTORY_BROWSER_LAUNCHER:-/usr/local/libexec/factory/factory-browser-sandbox}
web=${FACTORY_BROWSER_WEB:-}
screenshot=${FACTORY_BROWSER_SCREENSHOT:-/tmp/factory-browser-smoke.png}
[ -x "$launcher" ]
if grep -Eq -- '--no-sandbox|--disable-setuid-sandbox' "$launcher"; then
  echo "Factory browser launcher disables Chromium sandbox" >&2
  exit 1
fi
[ -n "$web" ] && [ -f "$web/package.json" ]

cd "$web"
node - "$launcher" "$screenshot" <<'NODE'
const { chromium } = require("playwright");

async function requireHealthyDOM(page, url, requireFactoryTitle = false) {
  const response = await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 });
  if (!response || !response.ok()) {
    const status = response ? response.status() : "no response";
    throw new Error(`unexpected HTTP response for ${url}: ${status}`);
  }
  await page.locator("body").waitFor({ state: "attached", timeout: 5000 });
  if (requireFactoryTitle && !/\bFactory\b/i.test(await page.title())) {
    throw new Error("public Factory response has no recognizable Factory title");
  }
}

async function withPage(browser, options, check) {
  const page = await browser.newPage(options);
  try {
    return await check(page);
  } finally {
    await page.close();
  }
}

(async () => {
  const username = process.env.FACTORY_BROWSER_BASIC_AUTH_USERNAME;
  const password = process.env.FACTORY_BROWSER_BASIC_AUTH_PASSWORD;
  if ((username === undefined) !== (password === undefined)) {
    throw new Error("both Factory Basic Auth variables must be set together");
  }
  const auth = username === undefined ? undefined : { httpCredentials: { username, password } };
  const browser = await chromium.launch({
    executablePath: process.argv[2],
    chromiumSandbox: true,
    headless: true,
  });
  try {
    await withPage(browser, undefined, (page) =>
      requireHealthyDOM(page, "http://127.0.0.1:7337"));
    await withPage(browser, auth, async (page) => {
      if (auth) {
        await requireHealthyDOM(page, "https://factory.timafen.com", true);
      } else {
        try {
          await page.goto("https://factory.timafen.com", {
            waitUntil: "domcontentloaded",
            timeout: 30000,
          });
          throw new Error("public Factory did not return ERR_INVALID_AUTH_CREDENTIALS");
        } catch (error) {
          const code = String(error && error.message).match(/net::(ERR_[A-Z0-9_]+)/)?.[1];
          if (code !== "ERR_INVALID_AUTH_CREDENTIALS") throw error;
        }
      }
    });
    await withPage(browser, undefined, async (page) => {
      await requireHealthyDOM(page, "https://staging-automation.tarser.net");
      await page.screenshot({ path: process.argv[3], fullPage: true });
    });
    for (const url of ["https://automation.tarser.net", "https://example.com"]) {
      await withPage(browser, undefined, async (page) => {
        let blocked = false;
        try {
          await page.goto(url, { waitUntil: "domcontentloaded", timeout: 10000 });
        } catch (_) {
          blocked = true;
        }
        if (!blocked) throw new Error(`network isolation allowed forbidden URL: ${url}`);
      });
    }
  } finally {
    await browser.close();
  }
})().catch((error) => {
  const message = String(error && error.message);
  if (message.includes("No usable sandbox")) console.error("No usable sandbox");
  else console.error("Factory browser smoke failed");
  process.exit(1);
});
NODE
[ -s "$screenshot" ] || { echo "Factory browser smoke screenshot is missing" >&2; exit 1; }
printf 'Factory browser network smoke passed; screenshot: %s\n' "$screenshot"
