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
HELPER=$LIBEXEC/factory-browser-isolated
CONFIG=$LIBEXEC/factory-browser.conf
STATE=$LIBEXEC/factory-browser-install.state
SUDOERS=${FACTORY_BROWSER_SUDOERS:-/etc/sudoers.d/factory-browser}
APPARMOR=${FACTORY_BROWSER_APPARMOR:-/etc/apparmor.d/factory-browser}
backup=
changed=0

sha256() { sha256sum "$1" | awk '{print $1}'; }
state_value() {
  [ -f "$STATE" ] || return 0
  sed -n "s/^$1=//p" "$STATE" | head -n 1
}

step() { printf '== %s\n' "$*"; }

rollback() {
  status=$?
  if [ "$changed" = 1 ]; then
    # The replacement profile may already be active when the live smoke fails.
    # Remove it before restoring the previous on-disk profile.
    apparmor_parser -R "$APPARMOR" >/dev/null 2>&1 || true
    for target in "$LAUNCHER" "$HELPER" "$CONFIG" "$SUDOERS" "$APPARMOR"; do
      name=$(printf '%s' "$target" | sha256sum | cut -d' ' -f1)
      rm -f -- "$target"
      rm -f -- "$target.new"
      [ ! -e "$backup/$name" ] && [ ! -L "$backup/$name" ] || cp -a -- "$backup/$name" "$target"
    done
    if [ -f "$APPARMOR" ]; then
      apparmor_parser -r "$APPARMOR" >/dev/null 2>&1 \
        || echo "warning: previous Factory browser AppArmor profile was not reloaded" >&2
    fi
  fi
  [ -z "$backup" ] || rm -rf -- "$backup"
  exit "$status"
}
trap rollback ERR

if [ "$(id -u)" -ne 0 ]; then
  echo "run this installer as root" >&2
  exit 1
fi
id "$FACTORY_USER" >/dev/null
[[ "$FACTORY_USER" =~ ^[a-z_][a-z0-9_-]*[$]?$ ]] \
  || { echo "unsafe Factory account name" >&2; exit 1; }
FACTORY_HOME=$(getent passwd "$FACTORY_USER" | cut -d: -f6)
[ -n "$FACTORY_HOME" ]

[ -f "$PAYLOAD/web/package.json" ]
[ -f "$PAYLOAD/web/package-lock.json" ]
[ -x "$PAYLOAD/ops/factory-browser-sandbox" ]
[ -x "$PAYLOAD/ops/factory-browser-isolated" ]
[ -x "$PAYLOAD/ops/test-browser-sandbox.sh" ]
[ -x "$PAYLOAD/ops/test-systemd-browser-firewall.sh" ]
command -v apparmor_parser >/dev/null \
  || { echo "apparmor_parser is required for the Chromium user namespace sandbox" >&2; exit 1; }

# Do not install a launcher unless the live kernel demonstrably enforces the
# same deny-by-default primitive used for every browser process.
step "проверяю сетевую изоляцию browser scope"
"$PAYLOAD/ops/test-systemd-browser-firewall.sh"

cd "$PAYLOAD/web"
step "проверяю закреплённую поставку Chromium"
npm ci --no-audit --no-fund --silent
lock_sha=$(sha256 package-lock.json)
deps_plan=$(DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=l \
  npx playwright install-deps chromium --dry-run)
deps_sha=$(printf '%s' "$deps_plan" | sha256sum | awk '{print $1}')

browser=$(sudo -H -u "$FACTORY_USER" bash -c \
  'cd "$1" && node -e '\''process.stdout.write(require("playwright").chromium.executablePath())'\''' \
  bash "$PAYLOAD/web")
if [ -z "$browser" ]; then
  echo "Playwright full Chromium was not installed" >&2
  exit 1
fi
case "$browser" in
  /*) ;;
  *) echo "Playwright returned a non-absolute Chromium path" >&2; exit 1 ;;
esac
[[ "$browser" =~ ^/[A-Za-z0-9._/-]+$ ]] \
  || { echo "Chromium path cannot be represented safely in AppArmor" >&2; exit 1; }

browser_sha=''
if [ -x "$browser" ]; then browser_sha=$(sha256 "$browser"); fi
cached_lock=$(state_value lock_sha)
cached_deps=$(state_value deps_sha)
cached_browser=$(state_value browser)
cached_browser_sha=$(state_value browser_sha)
install_browser=0
if [ "$cached_lock" != "$lock_sha" ] || [ "$cached_deps" != "$deps_sha" ] \
  || [ "$cached_browser" != "$browser" ] || [ -z "$browser_sha" ] \
  || [ "$cached_browser_sha" != "$browser_sha" ]; then
  install_browser=1
fi

if [ "$install_browser" = 1 ]; then
  step "ставлю системные зависимости Chromium без перезапуска служб"
  DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=l \
    npx playwright install-deps chromium
  step "ставлю закреплённую версию Chromium для пользователя Factory"
  sudo -H -u "$FACTORY_USER" bash -c 'cd "$1" && npx playwright install --force chromium' bash "$PAYLOAD/web"
  [ -x "$browser" ] || { echo "Playwright Chromium was not installed" >&2; exit 1; }
  browser_sha=$(sha256 "$browser")
else
  step "Chromium не изменился — переустановку пропускаю"
fi

install -d -o root -g root -m 755 "$LIBEXEC"
install -d -o root -g root -m 755 "$(dirname "$SUDOERS")"
install -d -o root -g root -m 755 "$(dirname "$APPARMOR")"
backup=$(mktemp -d "$LIBEXEC/.factory-browser-backup.XXXXXX")
for target in "$LAUNCHER" "$HELPER" "$CONFIG" "$STATE" "$SUDOERS" "$APPARMOR"; do
  if [ -e "$target" ] || [ -L "$target" ]; then
    name=$(printf '%s' "$target" | sha256sum | cut -d' ' -f1)
    cp -a -- "$target" "$backup/$name"
  fi
done
changed=1

install -o root -g root -m 755 "$PAYLOAD/ops/factory-browser-sandbox" "$LAUNCHER.new"
install -o root -g root -m 755 "$PAYLOAD/ops/factory-browser-isolated" "$HELPER.new"
{
  printf 'FACTORY_BROWSER_EXECUTABLE=%q\n' "$browser"
  printf 'FACTORY_BROWSER_USER=%q\n' "$FACTORY_USER"
  printf 'FACTORY_BROWSER_GROUP=%q\n' "$(id -gn "$FACTORY_USER")"
  printf 'FACTORY_BROWSER_HOME=%q\n' "$FACTORY_HOME"
} >"$CONFIG.new"
chown root:root "$CONFIG.new"
chmod 600 "$CONFIG.new"
{
  printf 'Defaults!%s closefrom_override\n' "$HELPER"
  printf '%s ALL=(root) NOPASSWD: %s *\n' "$FACTORY_USER" "$HELPER"
} >"$SUDOERS.new"
chmod 440 "$SUDOERS.new"
visudo -cf "$SUDOERS.new" >/dev/null
{
  echo '# Generated by install-server-browser.sh. Chromium remains otherwise unconfined;'
  echo '# this named profile only permits the user namespace used by its Linux sandbox.'
  echo 'abi <abi/4.0>,'
  echo 'include <tunables/global>'
  echo
  printf 'profile factory-browser-chromium "%s" flags=(unconfined) {\n' "$browser"
  echo '  userns,'
  echo '}'
} >"$APPARMOR.new"
chown root:root "$APPARMOR.new"
chmod 644 "$APPARMOR.new"
apparmor_parser -Q "$APPARMOR.new" >/dev/null
mv -f -- "$LAUNCHER.new" "$LAUNCHER"
mv -f -- "$HELPER.new" "$HELPER"
mv -f -- "$CONFIG.new" "$CONFIG"
mv -f -- "$SUDOERS.new" "$SUDOERS"
mv -f -- "$APPARMOR.new" "$APPARMOR"
step "разрешаю user namespace только установленному Chromium"
apparmor_parser -r "$APPARMOR" >/dev/null

step "запускаю живую проверку Chromium sandbox и сетевого allowlist"
smoke_output=$backup/browser-smoke.log
smoke_environment=(
  "FACTORY_BROWSER_LAUNCHER=$LAUNCHER"
  "FACTORY_BROWSER_WEB=$PAYLOAD/web"
  "FACTORY_BROWSER_SCREENSHOT=${FACTORY_BROWSER_SCREENSHOT:-/tmp/factory-browser-smoke.png}"
)
smoke_preserve_environment=()
if [ "${FACTORY_BROWSER_BASIC_AUTH_USERNAME+x}" = x ] \
  || [ "${FACTORY_BROWSER_BASIC_AUTH_PASSWORD+x}" = x ]; then
  smoke_preserve_environment=(--preserve-env=FACTORY_BROWSER_BASIC_AUTH_USERNAME,FACTORY_BROWSER_BASIC_AUTH_PASSWORD)
fi
if sudo -H -u "$FACTORY_USER" "${smoke_preserve_environment[@]}" env \
    "${smoke_environment[@]}" \
    "$PAYLOAD/ops/test-browser-sandbox.sh" >"$smoke_output" 2>&1
then
  cat "$smoke_output"
  rm -f -- "$smoke_output"
else
  # A transient Factory outage must not discard a known-good browser cache.
  # Retry the same smoke once; only its explicit sandbox diagnosis means that
  # Chromium itself failed to start rather than an endpoint being unavailable.
  if [ "$install_browser" = 0 ]; then
    step "повторяю smoke и отдельно проверяю доступность Factory"
    sudo -H -u "$FACTORY_USER" "${smoke_preserve_environment[@]}" env \
      "${smoke_environment[@]}" \
      "$PAYLOAD/ops/test-browser-sandbox.sh" >"$smoke_output.retry" 2>&1 || true
    curl -fsS --max-time 10 "${FACTORY_BROWSER_FACTORY_CHECK_URL:-http://127.0.0.1:7337/api/v1/dashboard}" \
      >/dev/null 2>&1 || true
    rm -f -- "$smoke_output.retry"
  fi
  if grep -Fq -- 'No usable sandbox' "$smoke_output"; then
    echo "Chromium sandbox smoke failed: No usable sandbox" >&2
  else
    echo "Chromium sandbox smoke failed" >&2
  fi
  false
fi
{
  printf 'lock_sha=%s\n' "$lock_sha"
  printf 'deps_sha=%s\n' "$deps_sha"
  printf 'browser=%s\n' "$browser"
  printf 'browser_sha=%s\n' "$browser_sha"
} >"$STATE.new"
chown root:root "$STATE.new"
chmod 600 "$STATE.new"
mv -f -- "$STATE.new" "$STATE"
changed=0
rm -rf -- "$backup"
backup=
trap - ERR

printf 'Factory server browser installed: %s\n' "$browser"
