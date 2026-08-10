#!/bin/bash
# Installs the Chromium revision pinned by web/package-lock.json for Factory's
# server-side browser. Run as root on the Ubuntu Factory host.
set -euo pipefail

PAYLOAD_ROOT=${FACTORY_BROWSER_PAYLOAD_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}
FACTORY_USER=${FACTORY_USER:-factory}
LIBEXEC=${FACTORY_BROWSER_LIBEXEC:-/usr/local/libexec}
SHARE=${FACTORY_BROWSER_SHARE:-/usr/local/share/factory/browser-sandbox}

install_payload() {
  local mode=$1 source=$2 target=$3
  if [ "$(readlink -m -- "$source")" = "$(readlink -m -- "$target")" ]; then
    return 0
  fi
  install -o root -g root -m "$mode" "$source" "$target"
}

if [ "$(id -u)" -ne 0 ]; then
  echo "run this installer as root" >&2
  exit 1
fi
id "$FACTORY_USER" >/dev/null
FACTORY_HOME=$(getent passwd "$FACTORY_USER" | cut -d: -f6)
[ -n "$FACTORY_HOME" ]

install -d -m 755 "$LIBEXEC" "$SHARE/ops" "$SHARE/web"
install_payload 755 "$PAYLOAD_ROOT/ops/factory-browser-sandbox" "$LIBEXEC/factory-browser-sandbox"
install_payload 755 "$PAYLOAD_ROOT/ops/test-browser-sandbox.sh" "$LIBEXEC/factory-browser-sandbox-check"
install_payload 755 "$PAYLOAD_ROOT/ops/install-server-browser.sh" "$SHARE/ops/install-server-browser.sh"
install_payload 644 "$PAYLOAD_ROOT/web/package.json" "$SHARE/web/package.json"
install_payload 644 "$PAYLOAD_ROOT/web/package-lock.json" "$SHARE/web/package-lock.json"

cd "$SHARE/web"
npm ci --no-audit --no-fund --silent
npx playwright install-deps chromium
for command in ip iptables ip6tables setsid; do
  command -v "$command" >/dev/null || { echo "required network sandbox tool is missing: $command" >&2; exit 1; }
done
sudo -H -u "$FACTORY_USER" bash -c "cd '$SHARE/web' && npx playwright install chromium"

browser=$(sudo -H -u "$FACTORY_USER" find "$FACTORY_HOME/.cache/ms-playwright" -type f \
  \( -name chrome -o -name chrome-headless-shell \) -perm /111 -print -quit)
if [ -z "$browser" ]; then
  echo "Playwright Chromium was not installed" >&2
  exit 1
fi
printf 'Factory server browser installed: %s\n' "$browser"
FACTORY_BROWSER_LAUNCHER="$LIBEXEC/factory-browser-sandbox" \
  FACTORY_BROWSER_USER="$FACTORY_USER" "$LIBEXEC/factory-browser-sandbox-check"
