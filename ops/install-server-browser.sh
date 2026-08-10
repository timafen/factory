#!/bin/bash
# Installs the Chromium revision pinned by web/package-lock.json for Factory's
# server-side browser. Run as root on the Ubuntu Factory host.
set -euo pipefail

resolve_path() {
  local path=$1 directory link
  while [ -L "$path" ]; do
    directory=$(cd -P "$(dirname "$path")" && pwd)
    link=$(readlink "$path")
    case "$link" in
      /*) path=$link ;;
      *) path=$directory/$link ;;
    esac
  done
  directory=$(cd -P "$(dirname "$path")" && pwd)
  printf '%s/%s\n' "$directory" "$(basename "$path")"
}

SCRIPT=$(resolve_path "${BASH_SOURCE[0]}")
ROOT=$(cd "$(dirname "$SCRIPT")/.." && pwd -P)
PAYLOAD=${FACTORY_BROWSER_SHARE:-$ROOT}
LIBEXEC=${FACTORY_BROWSER_LIBEXEC:-/usr/local/libexec/factory}
FACTORY_USER=${FACTORY_USER:-factory}
LAUNCHER=$LIBEXEC/factory-browser-sandbox
previous=
installed=0

rollback() {
  status=$?
  if [ "$installed" = 1 ]; then
    rm -f -- "$LAUNCHER"
    if [ -n "$previous" ]; then mv -- "$previous" "$LAUNCHER"; fi
  fi
  exit "$status"
}
trap rollback ERR

if [ "$(id -u)" -ne 0 ]; then
  echo "run this installer as root" >&2
  exit 1
fi
id "$FACTORY_USER" >/dev/null
FACTORY_HOME=$(getent passwd "$FACTORY_USER" | cut -d: -f6)
[ -n "$FACTORY_HOME" ]

[ -f "$PAYLOAD/web/package.json" ]
[ -f "$PAYLOAD/web/package-lock.json" ]
[ -x "$PAYLOAD/ops/factory-browser-sandbox" ]
[ -x "$PAYLOAD/ops/test-browser-sandbox.sh" ]

cd "$PAYLOAD/web"
npm ci --no-audit --no-fund --silent
npx playwright install-deps chromium
sudo -H -u "$FACTORY_USER" bash -c 'cd "$1" && npx playwright install chromium' bash "$PAYLOAD/web"

browser=$(sudo -H -u "$FACTORY_USER" find "$FACTORY_HOME/.cache/ms-playwright" -type f \
  \( -name chrome -o -name chrome-headless-shell \) -perm /111 -print -quit)
if [ -z "$browser" ]; then
  echo "Playwright Chromium was not installed" >&2
  exit 1
fi

install -d -o "$FACTORY_USER" -g "$FACTORY_USER" -m 755 "$LIBEXEC"
temporary=$(mktemp "$LIBEXEC/.factory-browser-sandbox.XXXXXX")
install -o "$FACTORY_USER" -g "$FACTORY_USER" -m 755 \
  "$PAYLOAD/ops/factory-browser-sandbox" "$temporary"
if [ -e "$LAUNCHER" ] || [ -L "$LAUNCHER" ]; then
  previous=$(mktemp "$LIBEXEC/.factory-browser-sandbox.previous.XXXXXX")
  rm -f -- "$previous"
  mv -- "$LAUNCHER" "$previous"
fi
mv -- "$temporary" "$LAUNCHER"
installed=1

sudo -H -u "$FACTORY_USER" env \
  FACTORY_BROWSER_LAUNCHER="$LAUNCHER" \
  FACTORY_BROWSER_WEB="$PAYLOAD/web" \
  "$PAYLOAD/ops/test-browser-sandbox.sh"
installed=0
rm -f -- "$previous"
trap - ERR

printf 'Factory server browser installed: %s\n' "$browser"
