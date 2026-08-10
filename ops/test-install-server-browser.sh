#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
INSTALLER="$SCRIPT_DIR/install-server-browser.sh"
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }

share="$temporary/share"
libexec="$temporary/libexec"
test_bin="$temporary/bin"
factory_home="$temporary/factory-home"
mkdir -p "$share/ops" "$share/web" "$test_bin" "$factory_home"
cp "$INSTALLER" "$share/ops/install-server-browser.sh"
cat >"$share/ops/factory-browser-sandbox" <<'SH'
#!/bin/bash
exit 0
SH
cat >"$share/ops/test-browser-sandbox.sh" <<'SH'
#!/bin/bash
echo checked >>"$TEST_BROWSER_EVENTS"
SH
printf '{"name":"factory-browser-install-test"}\n' >"$share/web/package.json"
printf '{"lockfileVersion":3}\n' >"$share/web/package-lock.json"
chmod 755 "$share/ops/"*
: >"$temporary/events"

cat >"$test_bin/id" <<'SH'
#!/bin/bash
if [ "${1:-}" = -u ]; then echo 0; fi
exit 0
SH
cat >"$test_bin/getent" <<'SH'
#!/bin/bash
printf 'factory:x:1000:1000:Factory:%s:/bin/bash\n' "$TEST_BROWSER_HOME"
SH
cat >"$test_bin/install" <<'SH'
#!/bin/bash
args=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o|-g) shift 2 ;;
    *) args+=("$1"); shift ;;
  esac
done
exec /usr/bin/install "${args[@]}"
SH
cat >"$test_bin/npm" <<'SH'
#!/bin/bash
printf 'npm-cwd=%s args=%s\n' "$PWD" "$*" >>"$TEST_BROWSER_EVENTS"
SH
cat >"$test_bin/npx" <<'SH'
#!/bin/bash
printf 'npx-cwd=%s args=%s\n' "$PWD" "$*" >>"$TEST_BROWSER_EVENTS"
SH
cat >"$test_bin/sudo" <<'SH'
#!/bin/bash
for argument in "$@"; do
  if [ "$argument" = find ]; then
    printf '%s/.cache/ms-playwright/chromium/chrome\n' "$TEST_BROWSER_HOME"
    exit 0
  fi
done
exit 0
SH
for command in ip iptables ip6tables setsid; do
  printf '#!/bin/bash\nexit 0\n' >"$test_bin/$command"
done
chmod 755 "$test_bin/"*

linked_installer="$temporary/linked-install-server-browser.sh"
ln -s "$share/ops/install-server-browser.sh" "$linked_installer"
TEST_BROWSER_EVENTS="$temporary/events" TEST_BROWSER_HOME="$factory_home" \
  PATH="$test_bin:$PATH" FACTORY_USER="$(id -un)" \
  FACTORY_BROWSER_SHARE="$share" FACTORY_BROWSER_LIBEXEC="$libexec" \
  bash "$linked_installer" >"$temporary/output" 2>&1 \
  || fail "установленная копия install-server-browser.sh завершилась ошибкой"

grep -Fx "npm-cwd=$share/web args=ci --no-audit --no-fund --silent" "$temporary/events" >/dev/null \
  || fail "npm ci запущен не из установленного browser payload"
grep -Fx checked "$temporary/events" >/dev/null \
  || fail "установленный browser checker не был запущен"
cmp -s "$share/ops/factory-browser-sandbox" "$libexec/factory-browser-sandbox" \
  || fail "browser launcher не установлен"
grep -F 'Factory server browser installed:' "$temporary/output" >/dev/null \
  || fail "installer не подтвердил установку Chromium"

rollback="$temporary/rollback"
mkdir -p "$rollback/libexec" "$rollback/release"
printf 'previous launcher\n' >"$rollback/release/factory-browser-sandbox"
ln -s "$rollback/release/factory-browser-sandbox" "$rollback/libexec/factory-browser-sandbox"
cat >"$share/ops/test-browser-sandbox.sh" <<'SH'
#!/bin/bash
exit 1
SH
chmod 755 "$share/ops/test-browser-sandbox.sh"
status=0
TEST_BROWSER_EVENTS="$temporary/events" TEST_BROWSER_HOME="$factory_home" \
  PATH="$test_bin:$PATH" FACTORY_USER="$(id -un)" \
  FACTORY_BROWSER_SHARE="$share" FACTORY_BROWSER_LIBEXEC="$rollback/libexec" \
  bash "$linked_installer" >"$rollback/output" 2>&1 || status=$?
[ "$status" -ne 0 ] || fail "ошибка browser checker не прервала установку"
[ -L "$rollback/libexec/factory-browser-sandbox" ] \
  || fail "безопасный откат не вернул предыдущий symlink launcher"
grep -Fx 'previous launcher' "$rollback/libexec/factory-browser-sandbox" >/dev/null \
  || fail "безопасный откат не сохранил прежний launcher"

echo "PASS: installer находит payload через symlink и безопасно откатывает launcher"
