#!/bin/bash
# One-time root bootstrap for hosts whose installed release helper predates the
# candidate-dispatch path. Installs the complete system release unit and rolls
# every target back if browser installation or its live check fails.
set -Euo pipefail

SRC=$(cd "${1:?путь к проверенному checkout кандидата}" && pwd)
FX_BIN="${FACTORY_FX_BIN:-/usr/local/bin/fx}"
RELEASE_HELPER="${FACTORY_RELEASE_HELPER:-/usr/local/lib/fx-factory-release}"
BOOTSTRAP_HELPER="${FACTORY_RELEASE_BOOTSTRAP_HELPER:-/usr/local/lib/fx-factory-release-bootstrap}"
BROWSER_SHARE="${FACTORY_BROWSER_SHARE:-/usr/local/share/factory/browser-sandbox}"
BROWSER_LIBEXEC="${FACTORY_BROWSER_LIBEXEC:-/usr/local/libexec}"

step() { echo "== $*"; }
fail() { echo "!! $*" >&2; }

if [ "$(id -u)" -ne 0 ] && [ "${FACTORY_RELEASE_BOOTSTRAP_TEST:-0}" != 1 ]; then
  fail "bootstrap должен запускаться от root"
  exit 4
fi

validate_target() {
  case "$1" in
    /*) [ "$1" != / ] ;;
    *) return 1 ;;
  esac
}
for target in "$FX_BIN" "$RELEASE_HELPER" "$BOOTSTRAP_HELPER" "$BROWSER_SHARE" "$BROWSER_LIBEXEC"; do
  validate_target "$target" || { fail "небезопасный путь установки: $target"; exit 4; }
done

required=(
  ops/fx
  ops/fx-factory-release
  ops/bootstrap-factory-release.sh
  ops/install-server-browser.sh
  ops/factory-browser-sandbox
  ops/test-browser-sandbox.sh
  web/package.json
  web/package-lock.json
)
for relative in "${required[@]}"; do
  [ -f "$SRC/$relative" ] || { fail "в кандидате нет $relative"; exit 4; }
done
for script in "${required[@]:0:6}"; do
  bash -n "$SRC/$script" || { fail "$script не прошёл проверку синтаксиса"; exit 5; }
done

transaction=$(mktemp -d "${TMPDIR:-/tmp}/factory-release-bootstrap-XXXXXX") \
  || { fail "не смог создать временную папку"; exit 4; }
mkdir -p "$transaction/previous"

backup_path() {
  local target=$1 name=$2
  if [ -e "$target" ] || [ -L "$target" ]; then
    cp -a -- "$target" "$transaction/previous/$name" || return
    : >"$transaction/previous/$name.present"
  fi
}

restore_path() {
  local target=$1 name=$2
  rm -rf -- "$target" || return
  if [ -e "$transaction/previous/$name.present" ]; then
    mkdir -p "$(dirname "$target")" \
      && cp -a -- "$transaction/previous/$name" "$target"
  fi
}

rollback_armed=0
rollback() {
  local status=${1:-4}
  trap - ERR EXIT HUP INT TERM
  fail "bootstrap не завершён — возвращаю прежний системный комплект"
  restore_path "$FX_BIN" fx || fail "не смог вернуть fx"
  restore_path "$RELEASE_HELPER" release-helper || fail "не смог вернуть release-helper"
  restore_path "$BOOTSTRAP_HELPER" release-bootstrap || fail "не смог вернуть bootstrap"
  restore_path "$BROWSER_SHARE" browser-share || fail "не смог вернуть browser payload"
  restore_path "$BROWSER_LIBEXEC/factory-browser-sandbox" browser-launcher \
    || fail "не смог вернуть browser launcher"
  restore_path "$BROWSER_LIBEXEC/factory-browser-sandbox-check" browser-check \
    || fail "не смог вернуть browser check"
  rm -rf -- "$transaction"
  exit "$status"
}
on_error() { local status=$?; [ "$rollback_armed" = 0 ] || rollback "$status"; exit "$status"; }
trap on_error ERR EXIT
trap 'rollback 130' HUP INT TERM

step "сохраняю системный комплект до bootstrap"
backup_path "$FX_BIN" fx \
  && backup_path "$RELEASE_HELPER" release-helper \
  && backup_path "$BOOTSTRAP_HELPER" release-bootstrap \
  && backup_path "$BROWSER_SHARE" browser-share \
  && backup_path "$BROWSER_LIBEXEC/factory-browser-sandbox" browser-launcher \
  && backup_path "$BROWSER_LIBEXEC/factory-browser-sandbox-check" browser-check \
  || { fail "не смог сохранить системный комплект"; rm -rf -- "$transaction"; exit 4; }
rollback_armed=1

step "ставлю root-owned bootstrap, fx и release-helper кандидата"
install -d -m 755 "$(dirname "$FX_BIN")" "$(dirname "$RELEASE_HELPER")" \
  "$(dirname "$BOOTSTRAP_HELPER")" "$BROWSER_SHARE/ops" "$BROWSER_SHARE/web" "$BROWSER_LIBEXEC"
install -m 755 "$SRC/ops/fx" "$FX_BIN"
install -m 755 "$SRC/ops/fx-factory-release" "$RELEASE_HELPER"
install -m 755 "$SRC/ops/bootstrap-factory-release.sh" "$BOOTSTRAP_HELPER"
install -m 755 "$SRC/ops/install-server-browser.sh" "$SRC/ops/factory-browser-sandbox" \
  "$SRC/ops/test-browser-sandbox.sh" "$BROWSER_SHARE/ops/"
install -m 644 "$SRC/web/package.json" "$SRC/web/package-lock.json" "$BROWSER_SHARE/web/"

step "устанавливаю и проверяю browser-sandbox"
FACTORY_BROWSER_SHARE="$BROWSER_SHARE" FACTORY_BROWSER_LIBEXEC="$BROWSER_LIBEXEC" \
  "$FX_BIN" factory browser-sandbox install
FACTORY_BROWSER_SHARE="$BROWSER_SHARE" FACTORY_BROWSER_LIBEXEC="$BROWSER_LIBEXEC" \
  "$FX_BIN" factory browser-sandbox check

rollback_armed=0
trap - ERR EXIT HUP INT TERM
rm -rf -- "$transaction"
echo "PASS: системный bootstrap и browser-sandbox установлены и проверены"
