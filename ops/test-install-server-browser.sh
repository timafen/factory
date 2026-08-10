#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
INSTALLER="$SCRIPT_DIR/install-server-browser.sh"
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }

"$SCRIPT_DIR/test-systemd-browser-firewall.sh" --check-properties \
  || fail "systemd-run не принимает свойства browser scope"

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
mkdir -p "$share/web/node_modules/playwright" \
  "$factory_home/.cache/ms-playwright/chromium-1234/chrome-linux64"
cat >"$share/web/node_modules/playwright/index.js" <<'JS'
const fs = require("node:fs");
const { spawnSync } = require("node:child_process");

exports.chromium = {
  executablePath() {
    return `${process.env.TEST_BROWSER_HOME}/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome`;
  },
  async launch(options) {
    fs.appendFileSync(process.env.TEST_BROWSER_EVENTS,
      `playwright-launcher=${options.executablePath} sandbox=${options.chromiumSandbox}\n`);
    const launched = spawnSync(options.executablePath, ["--from-playwright"], {
      env: process.env,
      stdio: "inherit",
    });
    if (launched.status !== 0) throw new Error(`launcher exited ${launched.status}`);
    let nextPageId = 0;
    let authErrorPageId = null;
    return {
      async newPage(options) {
        const pageId = ++nextPageId;
        fs.appendFileSync(process.env.TEST_BROWSER_EVENTS,
          `page-new=${pageId} auth=${options && options.httpCredentials ? "yes" : "no"}\n`);
        return {
          async goto(url) {
            fs.appendFileSync(process.env.TEST_BROWSER_EVENTS, `goto-page=${pageId} url=${url}\n`);
            if (authErrorPageId === pageId && url.includes("staging-automation.tarser.net")) {
              throw new Error("page.goto: Navigation to staging is interrupted by another navigation to chrome-error://chromewebdata/");
            }
            if (url.includes("factory.timafen.com")) {
              const code = process.env.TEST_FACTORY_GOTO_ERROR || "ERR_INVALID_AUTH_CREDENTIALS";
              if (code !== "success") {
                authErrorPageId = pageId;
                throw new Error(`page.goto: net::${code} at ${url}`);
              }
            }
            if (url.includes("automation.tarser.net") && !url.includes("staging-")) throw new Error("blocked");
            if (url.includes("example.com")) throw new Error("blocked");
            const status = Number(url.includes("127.0.0.1")
              ? process.env.TEST_LOOPBACK_STATUS || "200"
              : url.includes("staging-automation.tarser.net")
                ? process.env.TEST_STAGING_STATUS || "200"
                : process.env.TEST_FACTORY_STATUS || "200");
            return {
              ok() { return status >= 200 && status < 300; },
              status() { return status; },
            };
          },
          locator(selector) {
            return {
              async waitFor(options) {
                fs.appendFileSync(process.env.TEST_BROWSER_EVENTS,
                  `dom=${selector} state=${options.state}\n`);
              },
            };
          },
          async title() {
            return urlTitle(pageId);
          },
          async screenshot(options) {
            fs.writeFileSync(options.path, "screenshot");
          },
          async close() {
            fs.appendFileSync(process.env.TEST_BROWSER_EVENTS, `page-close=${pageId}\n`);
          },
        };
      },
      async close() {},
    };
  },
};

function urlTitle() {
  return process.env.TEST_FACTORY_TITLE || "Factory";
}
JS
cat >"$factory_home/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome" <<'SH'
#!/bin/bash
if [ "${TEST_CHROMIUM_NO_USABLE_SANDBOX:-0}" = 1 ]; then
  echo '[ERROR:sandbox_linux.cc(377)] No usable sandbox!' >&2
  exit 1
fi
printf 'chromium-args=%s\n' "$*" >>"$TEST_BROWSER_EVENTS"
SH
chmod 755 "$share/ops/"*
chmod 755 "$factory_home/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"
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
printf 'npx-cwd=%s args=%s needrestart=%s frontend=%s\n' \
  "$PWD" "$*" "${NEEDRESTART_MODE:-}" "${DEBIAN_FRONTEND:-}" \
  >>"$TEST_BROWSER_EVENTS"
if [ "$*" = "playwright install-deps chromium" ] && [ "${NEEDRESTART_MODE:-}" != l ]; then
  systemctl restart factory-worker.service
fi
SH
cat >"$test_bin/systemctl" <<'SH'
#!/bin/bash
printf 'systemctl=%s\n' "$*" >>"$TEST_BROWSER_EVENTS"
SH
cat >"$test_bin/sudo" <<'SH'
#!/bin/bash
printf 'sudo-args=%s\n' "$*" >>"$TEST_BROWSER_EVENTS"
run_user=
while [ "$#" -gt 0 ]; do
  case "$1" in
    -H|-n|--preserve-env=*) shift ;;
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
expand_environment=1
has_ip_policy=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --scope|--quiet|--collect|--no-ask-password) shift ;;
    --expand-environment=no) expand_environment=0; shift ;;
    -p)
      case "$2" in
        IPAddressDeny=*|IPAddressAllow=*) has_ip_policy=1 ;;
        *) echo "Unknown assignment: $2" >&2; exit 1 ;;
      esac
      shift 2
      ;;
    *)
      # Emulate the systemd 258 default closely enough to prove that the
      # helper disables expansion before passing untrusted Chromium args.
      if [ "$expand_environment" = 1 ] && [ "${!#}" = '${TERM}' ]; then
        arguments=("$@")
        arguments[$((${#arguments[@]} - 1))]=$TERM
        set -- "${arguments[@]}"
      fi
      # Unit-test the BPF probe without kernel privileges: only its protected
      # Python client gets an unreachable address. The no-property control
      # still reaches the listener and therefore must fail its assertion.
      if [ "$has_ip_policy" = 1 ] && [ "$1" = python3 ] && [[ "$2" = */probe.py ]]; then
        exec "$1" "$2" 192.0.2.1 "$4"
      fi
      exec "$@"
      ;;
  esac
done
SH
cat >"$test_bin/setpriv" <<'SH'
#!/bin/bash
printf 'setpriv=%s\n' "$*" >>"$TEST_BROWSER_EVENTS"
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
cat >"$test_bin/apparmor_parser" <<'SH'
#!/bin/bash
printf 'apparmor-parser=%s\n' "$*" >>"$TEST_BROWSER_EVENTS"
[ "${TEST_APPARMOR_FAIL:-0}" != 1 ]
SH
chmod 755 "$test_bin/"*

cat >"$test_bin/ip" <<'SH'
#!/bin/bash
echo '1: lo inet 127.0.0.2 src 127.0.0.2 uid 0'
SH
chmod 755 "$test_bin/ip"

: >"$temporary/events"
TEST_BROWSER_EVENTS="$temporary/events" PATH="$test_bin:$PATH" \
  FACTORY_BROWSER_SYSTEMD_RUN="$test_bin/systemd-run" \
  "$SCRIPT_DIR/test-systemd-browser-firewall.sh" \
  || fail "BPF-проба не различила изолированный запуск и контроль без свойств"

linked_installer="$temporary/linked-install-server-browser.sh"
ln -s "$share/ops/install-server-browser.sh" "$linked_installer"
set +e
TEST_BROWSER_EVENTS="$temporary/events" TEST_BROWSER_HOME="$factory_home" \
  TEST_PROBE_FAIL=1 PATH="$test_bin:$PATH" FACTORY_USER="$(id -un)" \
  FACTORY_BROWSER_SHARE="$share" FACTORY_BROWSER_LIBEXEC="$libexec" \
  FACTORY_BROWSER_SUDOERS="$temporary/sudoers/factory-browser" \
  FACTORY_BROWSER_APPARMOR="$temporary/apparmor.d/factory-browser" \
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
  FACTORY_BROWSER_APPARMOR="$temporary/apparmor.d/factory-browser" \
  FACTORY_BROWSER_SCREENSHOT="$temporary/screenshot.png" \
  bash "$linked_installer" >"$temporary/output" 2>&1 \
  || { sed -n '1,80p' "$temporary/output" >&2; fail "установленная копия install-server-browser.sh завершилась ошибкой"; }

grep -Fx "npm-cwd=$share/web args=ci --no-audit --no-fund --silent" "$temporary/events" >/dev/null \
  || fail "npm ci запущен не из установленного browser payload"
grep -F "sudo-args=-H -u $(id -un) bash -c " "$temporary/events" >/dev/null \
  || fail "установка Chromium не была запущена через factory user"
grep -Fx "npx-cwd=$share/web args=playwright install-deps chromium needrestart=l frontend=noninteractive" \
  "$temporary/events" >/dev/null \
  || fail "install-deps не зафиксировал needrestart в неинтерактивном list-only режиме"
if grep -F 'systemctl=restart ' "$temporary/events" >/dev/null; then
  fail "install-deps перезапустил службу"
fi
grep -Fx "npx-cwd=$share/web args=playwright install chromium needrestart= frontend=" \
  "$temporary/events" >/dev/null \
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
grep -F -- '--expand-environment=no' "$temporary/events" >/dev/null \
  || fail "systemd-run может подменить проверенные Chromium-аргументы через environment"
grep -F 'IPAddressAllow=192.0.2.10' "$temporary/events" >/dev/null \
  || fail "browser не разрешил только адрес Factory FQDN"
grep -F 'IPAddressAllow=192.0.2.20' "$temporary/events" >/dev/null \
  || fail "browser не разрешил только адрес staging FQDN"
grep -F 'MAP factory.timafen.com 192.0.2.10, MAP staging-automation.tarser.net 192.0.2.20, MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1' \
  "$temporary/events" >/dev/null \
  || fail "Chromium resolver не разрешил literal 127.0.0.1 при запрете остальных FQDN"
grep -F -- '--no-proxy-server' "$temporary/events" >/dev/null \
  || fail "Chromium не запущен с принудительно отключённым proxy"
grep -Fx "apparmor-parser=-Q $temporary/apparmor.d/factory-browser.new" \
  "$temporary/events" >/dev/null \
  || fail "AppArmor profile не прошёл проверку до установки"
grep -Fx "apparmor-parser=-r $temporary/apparmor.d/factory-browser" \
  "$temporary/events" >/dev/null \
  || fail "AppArmor profile не был загружен перед живым smoke"
grep -F "profile factory-browser-chromium \"$factory_home/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome\"" \
  "$temporary/apparmor.d/factory-browser" >/dev/null \
  || fail "AppArmor profile не привязан к установленному full Chromium"
grep -Fx '  userns,' "$temporary/apparmor.d/factory-browser" >/dev/null \
  || fail "AppArmor profile не разрешил Chromium user namespace sandbox"
grep -F 'setpriv=' "$temporary/events" | grep -F -- '--no-new-privs' >/dev/null \
  || fail "Chromium не получил NoNewPrivileges через setpriv"
grep -F 'url=https://factory.timafen.com' "$temporary/events" >/dev/null \
  || fail "smoke не достиг защищённого Factory FQDN"
grep -F 'url=http://127.0.0.1:7337' "$temporary/events" >/dev/null \
  || fail "smoke не открыл локальный Factory"
dom_count=$(grep -Fxc 'dom=body state=attached' "$temporary/events")
[ "$dom_count" -eq 2 ] \
  || fail "smoke не подтвердил DOM локального Factory и staging"
grep -F 'url=https://staging-automation.tarser.net' "$temporary/events" >/dev/null \
  || fail "smoke не открыл разрешённый staging FQDN"
grep -F 'url=https://automation.tarser.net' "$temporary/events" >/dev/null \
  || fail "smoke не проверил блокировку production FQDN"
grep -F 'url=https://example.com' "$temporary/events" >/dev/null \
  || fail "smoke не проверил блокировку внешнего интернета"
page_count=$(grep -Fc 'page-new=' "$temporary/events")
closed_page_count=$(grep -Fc 'page-close=' "$temporary/events")
[ "$page_count" -eq 5 ] && [ "$closed_page_count" -eq 5 ] \
  || fail "smoke не выделил и не закрыл отдельную page для каждой проверки URL"
url_page_count=$(sed -n 's/^goto-page=\([0-9][0-9]*\) url=.*/\1/p' "$temporary/events" \
  | sort -u | wc -l)
[ "$url_page_count" -eq 5 ] \
  || fail "smoke повторно использовал page между независимыми проверками URL"
auth_page=$(sed -n 's/^goto-page=\([0-9][0-9]*\) url=https:\/\/factory\.timafen\.com$/\1/p' "$temporary/events")
staging_page=$(sed -n 's/^goto-page=\([0-9][0-9]*\) url=https:\/\/staging-automation\.tarser\.net$/\1/p' "$temporary/events")
[ -n "$auth_page" ] && [ -n "$staging_page" ] && [ "$auth_page" != "$staging_page" ] \
  || fail "staging повторно использовал page после Basic Auth error"
grep -Fx "page-close=$auth_page" "$temporary/events" >/dev/null \
  || fail "page с Basic Auth error не была закрыта до продолжения smoke"
grep -F 'Factory server browser installed:' "$temporary/output" >/dev/null \
  || fail "installer не подтвердил установку Chromium"

status=0
TEST_BROWSER_EVENTS="$temporary/events" TEST_BROWSER_HOME="$factory_home" PATH="$test_bin:$PATH" \
  "$libexec/factory-browser-sandbox" >"$temporary/root-launcher-output" 2>&1 || status=$?
[ "$status" -ne 0 ] || fail "живой launcher разрешил запуск от root"
grep -Fx 'Factory browser must not run as root' "$temporary/root-launcher-output" >/dev/null \
  || fail "launcher не объяснил отказ запуска от root"

# The installed script is the single live scenario used by the installer and
# by operators. Exercise its standalone entry point with and without secrets.
: >"$temporary/events"
standalone_screenshot="$temporary/standalone.png"
TEST_BROWSER_AS_USER=1 TEST_BROWSER_EVENTS="$temporary/events" TEST_BROWSER_HOME="$factory_home" \
  PATH="$test_bin:$PATH" FACTORY_BROWSER_LAUNCHER="$libexec/factory-browser-sandbox" \
  FACTORY_BROWSER_WEB="$share/web" FACTORY_BROWSER_SCREENSHOT="$standalone_screenshot" \
  "$share/ops/test-browser-sandbox.sh" >"$temporary/standalone-output" 2>&1 \
  || fail "standalone smoke не принял ожидаемый Basic Auth challenge"
[ -s "$standalone_screenshot" ] || fail "standalone smoke не сохранил staging screenshot"
grep -F 'auth=no' "$temporary/events" >/dev/null \
  || fail "standalone smoke неожиданно передал Basic Auth credentials"

: >"$temporary/events"
secret_user='browser-smoke-secret-user'
secret_password='browser-smoke-secret-password'
TEST_BROWSER_AS_USER=1 TEST_BROWSER_EVENTS="$temporary/events" TEST_BROWSER_HOME="$factory_home" \
  TEST_FACTORY_GOTO_ERROR=success PATH="$test_bin:$PATH" \
  FACTORY_BROWSER_BASIC_AUTH_USERNAME="$secret_user" \
  FACTORY_BROWSER_BASIC_AUTH_PASSWORD="$secret_password" \
  FACTORY_BROWSER_LAUNCHER="$libexec/factory-browser-sandbox" FACTORY_BROWSER_WEB="$share/web" \
  FACTORY_BROWSER_SCREENSHOT="$temporary/standalone-auth.png" \
  "$share/ops/test-browser-sandbox.sh" >"$temporary/standalone-auth-output" 2>&1 \
  || fail "standalone smoke не открыл Factory DOM с Basic Auth credentials"
grep -F 'auth=yes' "$temporary/events" >/dev/null \
  || fail "standalone smoke не передал Basic Auth credentials в browser context"
if grep -F "$secret_user" "$temporary/standalone-auth-output" >/dev/null \
  || grep -F "$secret_password" "$temporary/standalone-auth-output" >/dev/null \
  || grep -F "$secret_user" "$temporary/events" >/dev/null \
  || grep -F "$secret_password" "$temporary/events" >/dev/null; then
  fail "standalone smoke напечатал Basic Auth secret"
fi

# Responses with an HTML body are not enough: each allowed endpoint must be a
# successful HTTP response, and an authenticated public response must identify
# itself as Factory. The fake implements Playwright Response.ok/status/title.
expect_standalone_smoke_failure() {
  local name=$1
  shift
  local status=0
  env TEST_BROWSER_AS_USER=1 TEST_BROWSER_EVENTS="$temporary/events" TEST_BROWSER_HOME="$factory_home" \
    PATH="$test_bin:$PATH" FACTORY_BROWSER_LAUNCHER="$libexec/factory-browser-sandbox" \
    FACTORY_BROWSER_WEB="$share/web" FACTORY_BROWSER_SCREENSHOT="$temporary/rejected-$name.png" \
    "$@" "$share/ops/test-browser-sandbox.sh" >"$temporary/rejected-$name-output" 2>&1 \
    || status=$?
  [ "$status" -ne 0 ] || fail "standalone smoke принял $name"
  grep -Fx 'Factory browser smoke failed' "$temporary/rejected-$name-output" >/dev/null \
    || fail "standalone smoke опубликовал небезопасную диагностику: $name"
}

expect_standalone_smoke_failure 'public HTML 401 without credentials' \
  TEST_FACTORY_GOTO_ERROR=success TEST_FACTORY_STATUS=401
for factory_status in 401 403 500; do
  expect_standalone_smoke_failure "public HTML $factory_status with credentials" \
    TEST_FACTORY_GOTO_ERROR=success TEST_FACTORY_STATUS="$factory_status" \
    FACTORY_BROWSER_BASIC_AUTH_USERNAME="$secret_user" \
    FACTORY_BROWSER_BASIC_AUTH_PASSWORD="$secret_password"
done
expect_standalone_smoke_failure 'public non-Factory title with credentials' \
  TEST_FACTORY_GOTO_ERROR=success TEST_FACTORY_STATUS=200 TEST_FACTORY_TITLE='Access denied' \
  FACTORY_BROWSER_BASIC_AUTH_USERNAME="$secret_user" \
  FACTORY_BROWSER_BASIC_AUTH_PASSWORD="$secret_password"
expect_standalone_smoke_failure 'loopback HTML 500' TEST_LOOPBACK_STATUS=500
expect_standalone_smoke_failure 'staging HTML 403' TEST_STAGING_STATUS=403

# The installer invokes the same standalone scenario and passes auth only via
# sudo's preserved environment, never as a value in its logged arguments.
: >"$temporary/events"
installer_auth="$temporary/installer-auth"
TEST_BROWSER_EVENTS="$temporary/events" TEST_BROWSER_HOME="$factory_home" \
  TEST_FACTORY_GOTO_ERROR=success PATH="$test_bin:$PATH" FACTORY_USER="$(id -un)" \
  FACTORY_BROWSER_BASIC_AUTH_USERNAME="$secret_user" \
  FACTORY_BROWSER_BASIC_AUTH_PASSWORD="$secret_password" \
  FACTORY_BROWSER_SHARE="$share" FACTORY_BROWSER_LIBEXEC="$installer_auth/libexec" \
  FACTORY_BROWSER_SUDOERS="$installer_auth/sudoers/factory-browser" \
  FACTORY_BROWSER_APPARMOR="$installer_auth/apparmor.d/factory-browser" \
  FACTORY_BROWSER_SCREENSHOT="$installer_auth/screenshot.png" \
  bash "$linked_installer" >"$installer_auth-output" 2>&1 \
  || fail "installer smoke не открыл Factory с Basic Auth credentials"
grep -F 'auth=yes' "$temporary/events" >/dev/null \
  || fail "installer не передал Basic Auth credentials в browser context"
if grep -F "$secret_user" "$installer_auth-output" >/dev/null \
  || grep -F "$secret_password" "$installer_auth-output" >/dev/null \
  || grep -F "$secret_user" "$temporary/events" >/dev/null \
  || grep -F "$secret_password" "$temporary/events" >/dev/null; then
  fail "installer smoke напечатал Basic Auth secret"
fi

for network_error in ERR_NAME_NOT_RESOLVED ERR_CERT_AUTHORITY_INVALID ERR_CONNECTION_TIMED_OUT; do
  status=0
  TEST_BROWSER_AS_USER=1 TEST_BROWSER_EVENTS="$temporary/events" TEST_BROWSER_HOME="$factory_home" \
    TEST_FACTORY_GOTO_ERROR="$network_error" PATH="$test_bin:$PATH" \
    FACTORY_BROWSER_LAUNCHER="$libexec/factory-browser-sandbox" FACTORY_BROWSER_WEB="$share/web" \
    FACTORY_BROWSER_SCREENSHOT="$temporary/rejected-$network_error.png" \
    "$share/ops/test-browser-sandbox.sh" >"$temporary/rejected-$network_error-output" 2>&1 \
    || status=$?
  [ "$status" -ne 0 ] || fail "standalone smoke принял $network_error как Basic Auth challenge"
  grep -Fx 'Factory browser smoke failed' "$temporary/rejected-$network_error-output" >/dev/null \
    || fail "standalone smoke опубликовал небезопасную сетевую диагностику"
done

auth_failure="$temporary/auth-failure"
status=0
TEST_BROWSER_EVENTS="$temporary/events" TEST_BROWSER_HOME="$factory_home" \
  TEST_FACTORY_GOTO_ERROR=ERR_CONNECTION_REFUSED PATH="$test_bin:$PATH" FACTORY_USER="$(id -un)" \
  FACTORY_BROWSER_SHARE="$share" FACTORY_BROWSER_LIBEXEC="$auth_failure/libexec" \
  FACTORY_BROWSER_SUDOERS="$auth_failure/sudoers/factory-browser" \
  FACTORY_BROWSER_APPARMOR="$auth_failure/apparmor.d/factory-browser" \
  FACTORY_BROWSER_SCREENSHOT="$auth_failure/screenshot.png" \
  bash "$linked_installer" >"$auth_failure-output" 2>&1 || status=$?
[ "$status" -ne 0 ] || fail "smoke принял постороннюю ошибку Factory FQDN"
grep -Fx 'Chromium sandbox smoke failed' "$auth_failure-output" >/dev/null \
  || fail "installer не выдал безопасную диагностику ошибки Factory FQDN"
if grep -F 'ERR_CONNECTION_REFUSED' "$auth_failure-output" >/dev/null; then
  fail "installer опубликовал сырую сетевую диагностику Factory FQDN"
fi
[ ! -e "$auth_failure/libexec/factory-browser-sandbox" ] \
  || fail "ошибка Factory FQDN не откатила launcher"

smoke_failure="$temporary/smoke-failure"
status=0
TEST_BROWSER_EVENTS="$temporary/events" TEST_BROWSER_HOME="$factory_home" \
  TEST_CHROMIUM_NO_USABLE_SANDBOX=1 PATH="$test_bin:$PATH" FACTORY_USER="$(id -un)" \
  FACTORY_BROWSER_SHARE="$share" FACTORY_BROWSER_LIBEXEC="$smoke_failure/libexec" \
  FACTORY_BROWSER_SUDOERS="$smoke_failure/sudoers/factory-browser" \
  FACTORY_BROWSER_APPARMOR="$smoke_failure/apparmor.d/factory-browser" \
  FACTORY_BROWSER_SCREENSHOT="$smoke_failure/screenshot.png" \
  bash "$linked_installer" >"$smoke_failure-output" 2>&1 || status=$?
[ "$status" -ne 0 ] || fail "installer продолжил работу после реального сбоя Chromium smoke"
grep -Fx 'Chromium sandbox smoke failed: No usable sandbox' "$smoke_failure-output" >/dev/null \
  || fail "installer не нормализовал реальный Chromium sandbox failure"
if grep -F '[ERROR:sandbox_linux.cc' "$smoke_failure-output" >/dev/null; then
  fail "installer опубликовал произвольный Chromium stderr вместо безопасной диагностики"
fi
[ ! -e "$smoke_failure/libexec/factory-browser-sandbox" ] \
  || fail "ошибка Chromium smoke оставила launcher"
[ ! -e "$smoke_failure/apparmor.d/factory-browser" ] \
  || fail "ошибка Chromium smoke оставила AppArmor profile"

apparmor_failure="$temporary/apparmor-failure"
status=0
TEST_BROWSER_EVENTS="$temporary/events" TEST_BROWSER_HOME="$factory_home" \
  TEST_APPARMOR_FAIL=1 PATH="$test_bin:$PATH" FACTORY_USER="$(id -un)" \
  FACTORY_BROWSER_SHARE="$share" FACTORY_BROWSER_LIBEXEC="$apparmor_failure/libexec" \
  FACTORY_BROWSER_SUDOERS="$apparmor_failure/sudoers/factory-browser" \
  FACTORY_BROWSER_APPARMOR="$apparmor_failure/apparmor.d/factory-browser" \
  FACTORY_BROWSER_SCREENSHOT="$apparmor_failure/screenshot.png" \
  bash "$linked_installer" >"$apparmor_failure-output" 2>&1 || status=$?
[ "$status" -ne 0 ] || fail "installer продолжил работу без Chromium AppArmor profile"
[ ! -e "$apparmor_failure/libexec/factory-browser-sandbox" ] \
  || fail "ошибка AppArmor оставила launcher"
[ ! -e "$apparmor_failure/sudoers/factory-browser" ] \
  || fail "ошибка AppArmor оставила sudoers"

TERM='--host-resolver-rules=MAP * 127.0.0.1' \
  TEST_BROWSER_EVENTS="$temporary/events" TEST_BROWSER_HOME="$factory_home" \
  PATH="$test_bin:$PATH" FACTORY_USER="$(id -un)" \
  "$libexec/factory-browser-isolated" '${TERM}' \
  >"$temporary/environment-expansion-output" 2>&1 \
  || fail "launcher не сохранил literal Chromium-аргумент при отключённом expansion"
grep -F 'chromium-args=' "$temporary/events" | tail -1 | grep -F -- '${TERM}' >/dev/null \
  || fail "systemd-run раскрыл environment после проверки Chromium-аргументов"

for unsafe_argument in \
  '--host-resolver-rules=MAP * 127.0.0.1' \
  '-host-resolver-rules=MAP * 127.0.0.1' \
  ' --host-resolver-rules=MAP * 127.0.0.1' \
  '--host-rules=MAP * 127.0.0.1' \
  '-host-rules=MAP * 127.0.0.1' \
  $'\t--host-rules=MAP * 127.0.0.1\t' \
  '--proxy-auto-detect' \
  '--proxy-bypass-list=example.com' \
  '--proxy-server=http://127.0.0.1:8080' \
  '--proxy-pac-url=http://127.0.0.1/proxy.pac' \
  '--no-proxy-server'; do
  status=0
  TEST_BROWSER_EVENTS="$temporary/events" TEST_BROWSER_HOME="$factory_home" \
    PATH="$test_bin:$PATH" FACTORY_USER="$(id -un)" \
    "$libexec/factory-browser-isolated" "$unsafe_argument" \
    >"$temporary/network-override-output" 2>&1 || status=$?
  [ "$status" -ne 0 ] || fail "launcher принял network override: $unsafe_argument"
  grep -F 'unsafe Chromium network override rejected:' \
    "$temporary/network-override-output" >/dev/null \
    || fail "launcher не объяснил отказ network override: $unsafe_argument"
done

for unsafe_argument in \
  '--no-sandbox' \
  '-no-sandbox' \
  ' --no-sandbox ' \
  '--disable-sandbox' \
  '--disable-setuid-sandbox' \
  '--disable-seccomp-filter-sandbox' \
  '--disable-namespace-sandbox' \
  '--disable-gpu-sandbox' \
  '--disable-landlock-sandbox' \
  '--disable-webnn-compiler-sandbox' \
  '--no-zygote-sandbox' \
  '--service-sandbox-type=none' \
  '--disable-features=NetworkServiceSandbox'; do
  status=0
  TEST_BROWSER_EVENTS="$temporary/events" TEST_BROWSER_HOME="$factory_home" \
    PATH="$test_bin:$PATH" FACTORY_USER="$(id -un)" \
    "$libexec/factory-browser-isolated" "$unsafe_argument" \
    >"$temporary/sandbox-override-output" 2>&1 || status=$?
  [ "$status" -ne 0 ] || fail "launcher принял отключение Chromium sandbox: $unsafe_argument"
  grep -F 'unsafe Chromium sandbox override rejected:' \
    "$temporary/sandbox-override-output" >/dev/null \
    || fail "launcher не объяснил отказ sandbox override: $unsafe_argument"
done

rollback="$temporary/rollback"
mkdir -p "$rollback/libexec" "$rollback/release"
printf 'previous launcher\n' >"$rollback/release/factory-browser-sandbox"
ln -s "$rollback/release/factory-browser-sandbox" "$rollback/libexec/factory-browser-sandbox"
status=0
TEST_BROWSER_EVENTS="$temporary/events" TEST_BROWSER_HOME="$factory_home" \
  TEST_FACTORY_GOTO_ERROR=ERR_CONNECTION_RESET PATH="$test_bin:$PATH" FACTORY_USER="$(id -un)" \
  FACTORY_BROWSER_SHARE="$share" FACTORY_BROWSER_LIBEXEC="$rollback/libexec" \
  FACTORY_BROWSER_SUDOERS="$rollback/sudoers/factory-browser" \
  FACTORY_BROWSER_APPARMOR="$rollback/apparmor.d/factory-browser" \
  FACTORY_BROWSER_SCREENSHOT="$rollback/screenshot.png" \
  bash "$linked_installer" >"$rollback/output" 2>&1 || status=$?
[ "$status" -ne 0 ] || fail "ошибка browser smoke не прервала установку"
[ -L "$rollback/libexec/factory-browser-sandbox" ] \
  || fail "безопасный откат не вернул предыдущий symlink launcher"
grep -Fx 'previous launcher' "$rollback/libexec/factory-browser-sandbox" >/dev/null \
  || fail "безопасный откат не сохранил прежний launcher"
[ ! -e "$rollback/libexec/factory-browser-isolated" ] \
  || fail "ошибка smoke оставила новый root helper"
[ ! -e "$rollback/libexec/factory-browser.conf" ] \
  || fail "ошибка smoke оставила новую browser config"
[ ! -e "$rollback/sudoers/factory-browser" ] \
  || fail "ошибка smoke оставила новый sudoers"
[ ! -e "$rollback/apparmor.d/factory-browser" ] \
  || fail "ошибка smoke оставила новый AppArmor profile"

echo "PASS: installer не рестартует службы, чинит sandbox, проверяет allowlist и откатывает комплект"
