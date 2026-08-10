#!/bin/bash
# Release-time smoke: Playwright must start Chromium through the installed
# launcher without disabling Chromium's Linux sandbox.
set -euo pipefail

launcher=${FACTORY_BROWSER_LAUNCHER:-/usr/local/libexec/factory/factory-browser-sandbox}
web=${FACTORY_BROWSER_WEB:-}
[ -x "$launcher" ]
if grep -Eq -- '--no-sandbox|--disable-setuid-sandbox' "$launcher"; then
  echo "Factory browser launcher disables Chromium sandbox" >&2
  exit 1
fi
[ -n "$web" ] && [ -f "$web/package.json" ]

cd "$web"
node - "$launcher" <<'NODE'
const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch({
    executablePath: process.argv[2],
    chromiumSandbox: true,
    headless: true,
  });
  await browser.close();
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
NODE
