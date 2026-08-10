#!/bin/bash
# Release-time smoke: allowed pages render through the isolated launcher while
# production and arbitrary internet destinations remain unreachable.
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

(async () => {
  const browser = await chromium.launch({
    executablePath: process.argv[2],
    chromiumSandbox: true,
    headless: true,
  });
  const page = await browser.newPage();
  for (const url of ["https://factory.timafen.com", "https://staging-automation.tarser.net"]) {
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 });
  }
  await page.screenshot({ path: process.argv[3], fullPage: true });
  for (const url of ["https://automation.tarser.net", "https://example.com"]) {
    let blocked = false;
    try {
      await page.goto(url, { waitUntil: "domcontentloaded", timeout: 10000 });
    } catch (_) {
      blocked = true;
    }
    if (!blocked) throw new Error(`network isolation allowed forbidden URL: ${url}`);
  }
  await browser.close();
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
NODE
[ -s "$screenshot" ] || { echo "Factory browser smoke screenshot is missing" >&2; exit 1; }
printf 'Factory browser network smoke passed; screenshot: %s\n' "$screenshot"
