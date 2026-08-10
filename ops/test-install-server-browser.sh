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
cp "$SCRIPT_DIR/factory-browser-sandbox" "$share/ops/factory-browser-sandbox"
cp "$SCRIPT_DIR/factory-browser-isolated" "$share/ops/factory-browser-isolated"
cp "$SCRIPT_DIR/test-browser-sandbox.sh" "$share/ops/test-browser-sandbox.sh"
cat >"$share/ops/test-systemd-browser-firewall.sh" <<'SH'
#!/bin/bash
printf 'bpf-probe=pass\n' >>"$TEST_BROWSER_EVENTS"
[ "${TEST_PROBE_FAIL:-0}" != 1 ]
SH
printf '{"name":"factory-browser-install-test"}\n' >"$share/web/package.json"
printf '{"lockfileVersion":3}\n' >"$share/web/package-lock.json"
mkdir -p "$share/web/node_modules/playwright" "$factory_home/.cache/ms-playwright/chromium"
cat >"$share/web/node_modules/playwright/index.js" <<'JS'
const fs = require("node:fs");
const { spawnSync } = require("node:child_process");

exports.chromium = {
  async launch(options) {
    fs.appendFileSync(process.env.TEST_BROWSER_EVENTS,
      `playwright-launcher=${options.executablePath} sandbox=${options.chromiumSandbox}\n`);
    const launched = spawnSync(options.executablePath, ["--from-playwright"], {
      env: process.env,
      stdio: "inherit",
    });
    if (launched.status !== 0) throw new Error(`launcher exited ${launched.status}`);
    return {
      async newPage() {
        return {
          async goto(url) {
            fs.appendFileSync(process.env.TEST_BROWSER_EVENTS, `goto=${url}\n`);
            if (url.includes("automation.tarser.net") && !url.includes("staging-")) throw new Error("blocked");
            if (url.includes("example.com")) throw new Error("blocked");
          },
          async screenshot(options) {
            fs.writeFileSync(options.path, "screenshot");
          },
        };
      },
      async close() {},
    };
  },
};
JS
cat >"$factory_home/.cache/ms-playwright/chromium/chrome" <<'SH'
#!/bin/bash
printf 'chromium-args=%s\n' "$*" >>"$TEST_BROWSER_EVENTS"
SH
chmod 755 "$share/ops/"*
chmod 755 "$factory_home/.cache/ms-playwright/chromium/chrome"
: >"$temporary/events"

cat >"$test_bin/id" <<'SH'
#!/bin/bash
case "${1:-}" in
  -u) if [ "${TEST_BROWSER_AS_USER:-0}" = 1 ]; then echo 1000; else echo 0; fi ;;
  -un) echo "${FACTORY_USER:-factory}" ;;
  -gn) echo "${FACTORY_USER:-factory}" ;;
esac
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
printf 'sudo-args=%s\n' "$*" >>"$TEST_BROWSER_EVENTS"
run_user=
while [ "$#" -gt 0 ]; do
  case "$1" in
    -H|-n) shift ;;
    -C) shift 2 ;;
    -u) run_user=$2; shift 2 ;;
    *)
      if [ -n "$run_user" ]; then
        TEST_BROWSER_AS_USER=1 HOME="$TEST_BROWSER_HOME" exec env "$@"
      fi
      SUDO_USER="$(id -un)" TEST_BROWSER_AS_USER=0 exec "$@"
      ;;
  esac
done
exit 0
SH
cat >"$test_bin/stat" <<'SH'
#!/bin/bash
[ "${1:-}" != -c ] || { echo 0:600; exit 0; }
exec /usr/bin/stat "$@"
SH
cat >"$test_bin/getent" <<'SH'
#!/bin/bash
if [ "${1:-}" = passwd ]; then
  printf 'factory:x:1000:1000:Factory:%s:/bin/bash\n' "$TEST_BROWSER_HOME"
elif [ "${1:-}" = ahosts ]; then
  case "$2" in factory.timafen.com) echo '192.0.2.10 STREAM test';; *) echo '192.0.2.20 STREAM test';; esac
fi
SH
cat >"$test_bin/systemd-run" <<'SH'
#!/bin/bash
printf 'systemd-run=%s\n' "$*" >>"$TEST_BROWSER_EVENTS"
while [ "$#" -gt 0 ]; do
  case "$1" in --scope|--quiet|--collect) shift;; -p) shift 2;; *) exec "$@";; esac
done
SH
cat >"$test_bin/setpriv" <<'SH'
#!/bin/bash
while [ "$#" -gt 0 ]; do [ "$1" != -- ] || { shift; exec "$@"; }; shift; done
SH
cat >"$test_bin/visudo" <<'SH'
#!/bin/bash
exit 0
SH
cat >"$test_bin/chown" <<'SH'
#!/bin/bash
exit 0
SH
chmod 755 "$test_bin/"*

linked_installer="$temporary/linked-install-server-browser.sh"
ln -s "$share/ops/install-server-browser.sh" "$linked_installer"
set +e
TEST_BROWSER_EVENTS="$temporary/events" TEST_BROWSER_HOME="$factory_home" \
  TEST_PROBE_FAIL=1 PATH="$test_bin:$PATH" FACTORY_USER="$(id -un)" \
  FACTORY_BROWSER_SHARE="$share" FACTORY_BROWSER_LIBEXEC="$libexec" \
  FACTORY_BROWSER_SUDOERS="$temporary/sudoers/factory-browser" \
  bash "$linked_installer" >"$temporary/probe-failure-output" 2>&1
probe_status=$?
set -e
[ "$probe_status" -ne 0 ] || fail "installer продолжил работу без systemd BPF firewall"
[ ! -e "$libexec/factory-browser-sandbox" ] \
  || fail "installer изменил launcher после неуспешной BPF-пробы"

: >"$temporary/events"
TEST_BROWSER_EVENTS="$temporary/events" TEST_BROWSER_HOME="$factory_home" \
  PATH="$test_bin:$PATH" FACTORY_USER="$(id -un)" \
  FACTORY_BROWSER_SHARE="$share" FACTORY_BROWSER_LIBEXEC="$libexec" \
  FACTORY_BROWSER_SUDOERS="$temporary/sudoers/factory-browser" \
  FACTORY_BROWSER_SCREENSHOT="$temporary/screenshot.png" \
  bash "$linked_installer" >"$temporary/output" 2>&1 \
  || { sed -n '1,80p' "$temporary/output" >&2; fail "установленная копия install-server-browser.sh завершилась ошибкой"; }

grep -Fx "npm-cwd=$share/web args=ci --no-audit --no-fund --silent" "$temporary/events" >/dev/null \
  || fail "npm ci запущен не из установленного browser payload"
grep -F "sudo-args=-H -u $(id -un) bash -c " "$temporary/events" >/dev/null \
  || fail "установка Chromium не была запущена через factory user"
grep -Fx "npx-cwd=$share/web args=playwright install chromium" "$temporary/events" >/dev/null \
  || fail "installer не выполнил обязательную установку Playwright Chromium"
grep -Fx "playwright-launcher=$libexec/factory-browser-sandbox sandbox=true" \
  "$temporary/events" >/dev/null \
  || fail "Playwright не получил установленный launcher с включённым Chromium sandbox"
grep -Fx 'chromium-args=--from-playwright' "$temporary/events" >/dev/null \
  || grep -F 'chromium-args=--host-resolver-rules=' "$temporary/events" >/dev/null \
  || fail "Playwright не запустил Chromium через изолированный launcher"
cmp -s "$share/ops/factory-browser-sandbox" "$libexec/factory-browser-sandbox" \
  || fail "browser launcher не установлен"
grep -Fx 'bpf-probe=pass' "$temporary/events" >/dev/null \
  || fail "installer не проверил поддержку systemd BPF firewall"
grep -F 'IPAddressDeny=any' "$temporary/events" >/dev/null \
  || fail "browser не получил deny-by-default network policy"
grep -F 'IPAddressAllow=192.0.2.10' "$temporary/events" >/dev/null \
  || fail "browser не разрешил только адрес Factory FQDN"
grep -F 'IPAddressAllow=192.0.2.20' "$temporary/events" >/dev/null \
  || fail "browser не разрешил только адрес staging FQDN"
grep -Fx 'goto=https://factory.timafen.com' "$temporary/events" >/dev/null \
  || fail "smoke не открыл разрешённый Factory FQDN"
grep -Fx 'goto=https://staging-automation.tarser.net' "$temporary/events" >/dev/null \
  || fail "smoke не открыл разрешённый staging FQDN"
grep -Fx 'goto=https://automation.tarser.net' "$temporary/events" >/dev/null \
  || fail "smoke не проверил блокировку production FQDN"
grep -Fx 'goto=https://example.com' "$temporary/events" >/dev/null \
  || fail "smoke не проверил блокировку внешнего интернета"
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
  FACTORY_BROWSER_SUDOERS="$rollback/sudoers/factory-browser" \
  FACTORY_BROWSER_SCREENSHOT="$rollback/screenshot.png" \
  bash "$linked_installer" >"$rollback/output" 2>&1 || status=$?
[ "$status" -ne 0 ] || fail "ошибка browser checker не прервала установку"
[ -L "$rollback/libexec/factory-browser-sandbox" ] \
  || fail "безопасный откат не вернул предыдущий symlink launcher"
grep -Fx 'previous launcher' "$rollback/libexec/factory-browser-sandbox" >/dev/null \
  || fail "безопасный откат не сохранил прежний launcher"

echo "PASS: installer ставит сетевую изоляцию, проверяет allowlist и откатывает комплект"
