#!/bin/bash
# Trusted one-time transition used only by the root-owned fx broker. It accepts
# the exact current origin/main commit, installs release helpers as root-owned
# files, then executes only those installed copies.
set -Euo pipefail

EXPECTED_SHA=${1:?укажите полный commit текущего origin/main}
REPO="${FACTORY_RELEASE_REPO:-https://github.com/timafen/factory.git}"
FX_BIN="${FACTORY_FX_BIN:-/usr/local/bin/fx}"
RELEASE_HELPER="${FACTORY_RELEASE_HELPER:-/usr/local/lib/fx-factory-release}"
BOOTSTRAP_HELPER="${FACTORY_RELEASE_BOOTSTRAP_HELPER:-/usr/local/lib/fx-factory-release-bootstrap}"
BRAIN_INSTALLER="${FACTORY_BRAIN_INSTALLER:-/usr/local/lib/fx-factory-install-brain}"
BROWSER_SHARE="${FACTORY_BROWSER_SHARE:-/usr/local/share/factory/browser-sandbox}"
BROWSER_LIBEXEC="${FACTORY_BROWSER_LIBEXEC:-/usr/local/libexec}"

step() { echo "== $*"; }
fail() { echo "!! $*" >&2; }

case "$EXPECTED_SHA" in
  *[!0-9a-f]*|'') fail "нужен полный 40-значный commit origin/main"; exit 4 ;;
esac
[ "${#EXPECTED_SHA}" -eq 40 ] \
  || { fail "нужен полный 40-значный commit origin/main"; exit 4; }
test_mode=${FACTORY_RELEASE_BOOTSTRAP_TEST:-0}
if [ "$test_mode" = 1 ] && [ "$(id -u)" -eq 0 ]; then
  fail "тестовый режим доверенного перехода запрещён для root"
  exit 4
fi
if [ "$(id -u)" -ne 0 ] && [ "$test_mode" != 1 ]; then
  fail "доверенный переход должен запускаться от root через fx"
  exit 4
fi
install_owner=root
install_group=root
if [ "$test_mode" = 1 ]; then
  install_owner=$(id -un)
  install_group=$(id -gn)
fi

validate_target() {
  case "$1" in /*) [ "$1" != / ] ;; *) return 1 ;; esac
}
for target in "$FX_BIN" "$RELEASE_HELPER" "$BOOTSTRAP_HELPER" "$BRAIN_INSTALLER" \
  "$BROWSER_SHARE" "$BROWSER_LIBEXEC"; do
  validate_target "$target" || { fail "небезопасный путь установки: $target"; exit 4; }
done

checkout=$(mktemp -d /tmp/factory-release-main-XXXXXX) \
  || { fail "не смог создать root-owned staging для доверенного перехода"; exit 4; }
chmod 700 "$checkout" \
  || { fail "не смог закрыть staging от пользователя factory"; rm -rf -- "$checkout"; exit 4; }
if [ "$test_mode" = 1 ] && [ -n "${FACTORY_RELEASE_BOOTSTRAP_SOURCE:-}" ]; then
  source_checkout=$(cd "$FACTORY_RELEASE_BOOTSTRAP_SOURCE" && pwd)
  cp -a -- "$source_checkout/." "$checkout/" \
    || { fail "не смог материализовать тестовый commit"; rm -rf -- "$checkout"; exit 4; }
  chmod -R go-rwx "$checkout"
  actual_sha=${FACTORY_RELEASE_BOOTSTRAP_ACTUAL_SHA:-$EXPECTED_SHA}
  if [ -n "${FACTORY_RELEASE_BOOTSTRAP_AFTER_MATERIALIZE:-}" ]; then
    "$FACTORY_RELEASE_BOOTSTRAP_AFTER_MATERIALIZE" "$source_checkout"
  fi
else
  git clone --quiet --no-checkout "$REPO" "$checkout" \
    && git -C "$checkout" checkout --quiet --detach origin/main \
    || { fail "не смог материализовать origin/main в root-owned staging"; rm -rf -- "$checkout"; exit 4; }
  actual_sha=$(git -C "$checkout" rev-parse HEAD) \
    || { fail "не смог определить commit origin/main"; rm -rf -- "$checkout"; exit 4; }
fi
[ "$actual_sha" = "$EXPECTED_SHA" ] || {
  fail "origin/main изменился: запрошен $EXPECTED_SHA, сейчас $actual_sha"
  rm -rf -- "$checkout"
  exit 4
}

required=(
  ops/fx
  ops/fx-factory-release
  ops/bootstrap-factory-release.sh
  ops/install-brain.sh
  ops/install-server-browser.sh
  ops/factory-browser-sandbox
  ops/test-browser-sandbox.sh
  web/package.json
  web/package-lock.json
)
for relative in "${required[@]}"; do
  [ -f "$checkout/$relative" ] && [ ! -L "$checkout/$relative" ] \
    || { fail "в origin/main нет обычного файла $relative"; rm -rf -- "$checkout"; exit 4; }
done
for script in "${required[@]:0:7}"; do
  bash -n "$checkout/$script" \
    || { fail "$script не прошёл проверку синтаксиса"; rm -rf -- "$checkout"; exit 5; }
done

transaction=$(mktemp -d /tmp/factory-release-bootstrap-XXXXXX) \
  || { fail "не смог создать временную папку"; rm -rf -- "$checkout"; exit 4; }
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

cleanup_checkout() {
  rm -rf -- "$checkout"
}

rollback_armed=0
rollback() {
  local status=${1:-4}
  trap - ERR EXIT HUP INT TERM
  fail "доверенный переход не завершён — возвращаю прежний системный комплект"
  restore_path "$FX_BIN" fx || fail "не смог вернуть fx"
  restore_path "$RELEASE_HELPER" release-helper || fail "не смог вернуть release-helper"
  restore_path "$BOOTSTRAP_HELPER" release-bootstrap || fail "не смог вернуть bootstrap"
  restore_path "$BRAIN_INSTALLER" brain-installer || fail "не смог вернуть brain-installer"
  restore_path "$BROWSER_SHARE" browser-share || fail "не смог вернуть browser payload"
  restore_path "$BROWSER_LIBEXEC/factory-browser-sandbox" browser-launcher \
    || fail "не смог вернуть browser launcher"
  restore_path "$BROWSER_LIBEXEC/factory-browser-sandbox-check" browser-check \
    || fail "не смог вернуть browser check"
  cleanup_checkout
  rm -rf -- "$transaction"
  exit "$status"
}
on_error() { local status=$?; [ "$rollback_armed" = 0 ] || rollback "$status"; exit "$status"; }
trap on_error ERR EXIT
trap 'rollback 130' HUP INT TERM

step "сохраняю доверенный системный комплект"
backup_path "$FX_BIN" fx \
  && backup_path "$RELEASE_HELPER" release-helper \
  && backup_path "$BOOTSTRAP_HELPER" release-bootstrap \
  && backup_path "$BRAIN_INSTALLER" brain-installer \
  && backup_path "$BROWSER_SHARE" browser-share \
  && backup_path "$BROWSER_LIBEXEC/factory-browser-sandbox" browser-launcher \
  && backup_path "$BROWSER_LIBEXEC/factory-browser-sandbox-check" browser-check \
  || { fail "не смог сохранить системный комплект"; rm -rf -- "$transaction"; exit 4; }
rollback_armed=1

step "ставлю root-owned helpers из точной вершины origin/main ${actual_sha:0:7}"
install -d -m 755 "$(dirname "$FX_BIN")" "$(dirname "$RELEASE_HELPER")" \
  "$(dirname "$BOOTSTRAP_HELPER")" "$(dirname "$BRAIN_INSTALLER")" \
  "$BROWSER_SHARE/ops" "$BROWSER_SHARE/web" "$BROWSER_LIBEXEC"
install -o "$install_owner" -g "$install_group" -m 755 "$checkout/ops/fx" "$FX_BIN"
install -o "$install_owner" -g "$install_group" -m 755 "$checkout/ops/fx-factory-release" "$RELEASE_HELPER"
install -o "$install_owner" -g "$install_group" -m 755 "$checkout/ops/bootstrap-factory-release.sh" "$BOOTSTRAP_HELPER"
install -o "$install_owner" -g "$install_group" -m 755 "$checkout/ops/install-brain.sh" "$BRAIN_INSTALLER"
install -o "$install_owner" -g "$install_group" -m 755 "$checkout/ops/install-server-browser.sh" \
  "$checkout/ops/factory-browser-sandbox" "$checkout/ops/test-browser-sandbox.sh" \
  "$BROWSER_SHARE/ops/"
install -o "$install_owner" -g "$install_group" -m 644 "$checkout/web/package.json" \
  "$checkout/web/package-lock.json" "$BROWSER_SHARE/web/"

step "устанавливаю и проверяю browser-sandbox только установленными helpers"
FACTORY_BROWSER_SHARE="$BROWSER_SHARE" FACTORY_BROWSER_LIBEXEC="$BROWSER_LIBEXEC" \
  "$FX_BIN" factory browser-sandbox install
FACTORY_BROWSER_SHARE="$BROWSER_SHARE" FACTORY_BROWSER_LIBEXEC="$BROWSER_LIBEXEC" \
  "$FX_BIN" factory browser-sandbox check

rollback_armed=0
trap - ERR EXIT HUP INT TERM
cleanup_checkout
rm -rf -- "$transaction"
echo "PASS: доверенный переход origin/main установил root-owned helpers и browser-sandbox"
