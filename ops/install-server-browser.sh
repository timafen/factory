#!/bin/bash
# Installs the Chromium revision pinned by web/package-lock.json for Factory's
# server-side browser. Run as root on the Ubuntu Factory host.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
FACTORY_USER=${FACTORY_USER:-factory}

if [ "$(id -u)" -ne 0 ]; then
  echo "run this installer as root" >&2
  exit 1
fi
id "$FACTORY_USER" >/dev/null
FACTORY_HOME=$(getent passwd "$FACTORY_USER" | cut -d: -f6)
[ -n "$FACTORY_HOME" ]

cd "$ROOT/web"
npm ci --no-audit --no-fund --silent
npx playwright install-deps chromium
sudo -H -u "$FACTORY_USER" bash -c "cd '$ROOT/web' && npx playwright install chromium"

browser=$(sudo -H -u "$FACTORY_USER" find "$FACTORY_HOME/.cache/ms-playwright" -type f \
  \( -name chrome -o -name chrome-headless-shell \) -perm /111 -print -quit)
if [ -z "$browser" ]; then
  echo "Playwright Chromium was not installed" >&2
  exit 1
fi
printf 'Factory server browser installed: %s\n' "$browser"
