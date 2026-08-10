#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
BOOTSTRAP="$SCRIPT_DIR/bootstrap-factory-release.sh"
EXPECTED_SHA=1234567890abcdef1234567890abcdef12345678
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
assert_line() { grep -Fx "$2" "$1" >/dev/null || fail "$1 does not contain $2"; }

make_case() {
  local case_dir=$1 mode=$2
  mkdir -p "$case_dir/source/ops" "$case_dir/source/web" \
    "$case_dir/system/browser/ops" "$case_dir/system/browser/web" "$case_dir/system/libexec"
  printf 'old-fx\n' >"$case_dir/system/fx"
  printf 'old-helper\n' >"$case_dir/system/helper"
  printf 'old-bootstrap\n' >"$case_dir/system/bootstrap"
  printf 'old-brain\n' >"$case_dir/system/brain-installer"
  printf 'old-payload\n' >"$case_dir/system/browser/old-payload"
  printf 'old-launcher\n' >"$case_dir/system/libexec/factory-browser-sandbox"
  printf 'old-check\n' >"$case_dir/system/libexec/factory-browser-sandbox-check"
  : >"$case_dir/events"

  cat >"$case_dir/source/ops/fx" <<'FX'
#!/bin/bash
printf 'exec=%s args=%s\n' "$0" "$*" >>"$TEST_BOOTSTRAP_EVENTS"
case "$*" in
  *'browser-sandbox install'*)
    printf 'new-launcher\n' >"$FACTORY_BROWSER_LIBEXEC/factory-browser-sandbox"
    printf 'new-check\n' >"$FACTORY_BROWSER_LIBEXEC/factory-browser-sandbox-check"
    if [ "$TEST_BOOTSTRAP_MODE" = signal ]; then kill -TERM "$PPID"; exit 143; fi
    [ "$TEST_BOOTSTRAP_MODE" != install-fail ]
    ;;
  *'browser-sandbox check'*) [ "$TEST_BOOTSTRAP_MODE" != check-fail ] ;;
esac
FX
  printf '#!/bin/bash\nexit 0\n' >"$case_dir/source/ops/fx-factory-release"
  cp "$BOOTSTRAP" "$case_dir/source/ops/bootstrap-factory-release.sh"
  printf '#!/bin/bash\nexit 0\n' >"$case_dir/source/ops/install-brain.sh"
  for script in install-server-browser.sh factory-browser-sandbox test-browser-sandbox.sh; do
    printf '#!/bin/bash\nexit 0\n' >"$case_dir/source/ops/$script"
  done
  printf '{"name":"browser-test"}\n' >"$case_dir/source/web/package.json"
  printf '{"lockfileVersion":3}\n' >"$case_dir/source/web/package-lock.json"
  chmod 755 "$case_dir/source/ops/"*
}

run_case() {
  local case_dir=$1 mode=$2 actual_sha=${3:-$EXPECTED_SHA} hook=${4:-}
  TEST_BOOTSTRAP_MODE="$mode" TEST_BOOTSTRAP_EVENTS="$case_dir/events" \
    FACTORY_RELEASE_BOOTSTRAP_TEST=1 \
    FACTORY_RELEASE_BOOTSTRAP_SOURCE="$case_dir/source" \
    FACTORY_RELEASE_BOOTSTRAP_ACTUAL_SHA="$actual_sha" \
    FACTORY_RELEASE_BOOTSTRAP_AFTER_MATERIALIZE="$hook" \
    FACTORY_RELEASE_AS='' FACTORY_FX_BIN="$case_dir/system/fx" \
    FACTORY_RELEASE_HELPER="$case_dir/system/helper" \
    FACTORY_RELEASE_BOOTSTRAP_HELPER="$case_dir/system/bootstrap" \
    FACTORY_BRAIN_INSTALLER="$case_dir/system/brain-installer" \
    FACTORY_BROWSER_SHARE="$case_dir/system/browser" \
    FACTORY_BROWSER_LIBEXEC="$case_dir/system/libexec" \
    bash "$BOOTSTRAP" "$EXPECTED_SHA" >"$case_dir/output" 2>&1
}

success="$temporary/success"
make_case "$success" success
run_case "$success" success || fail "successful bootstrap failed"
assert_line "$success/events" "exec=$success/system/fx args=factory browser-sandbox install"
assert_line "$success/events" "exec=$success/system/fx args=factory browser-sandbox check"
cmp -s "$success/source/ops/fx" "$success/system/fx" || fail "fx was not installed"
cmp -s "$success/source/ops/fx-factory-release" "$success/system/helper" \
  || fail "candidate helper was not installed"
cmp -s "$success/source/ops/bootstrap-factory-release.sh" "$success/system/bootstrap" \
  || fail "root-owned bootstrap was not installed"
cmp -s "$success/source/ops/install-brain.sh" "$success/system/brain-installer" \
  || fail "root-owned brain installer was not installed"
assert_line "$success/system/libexec/factory-browser-sandbox" new-launcher

materialized="$temporary/materialized"
make_case "$materialized" success
cp "$materialized/source/ops/fx" "$materialized/expected-fx"
cat >"$materialized/mutate-source" <<'SH'
#!/bin/bash
printf '#!/bin/bash\nexit 99\n' >"$1/ops/fx"
chmod 755 "$1/ops/fx"
SH
chmod 755 "$materialized/mutate-source"
run_case "$materialized" success "$EXPECTED_SHA" "$materialized/mutate-source" \
  || fail "bootstrap used the mutable source after materialization"
cmp -s "$materialized/expected-fx" "$materialized/system/fx" \
  || fail "fx was installed from the user-writable checkout"

assert_rolled_back() {
  local case_dir=$1
  assert_line "$case_dir/system/fx" old-fx
  assert_line "$case_dir/system/helper" old-helper
  assert_line "$case_dir/system/bootstrap" old-bootstrap
  assert_line "$case_dir/system/brain-installer" old-brain
  assert_line "$case_dir/system/browser/old-payload" old-payload
  assert_line "$case_dir/system/libexec/factory-browser-sandbox" old-launcher
  assert_line "$case_dir/system/libexec/factory-browser-sandbox-check" old-check
}

for mode in install-fail check-fail signal; do
  failed="$temporary/$mode"
  make_case "$failed" "$mode"
  if run_case "$failed" "$mode"; then fail "$mode unexpectedly succeeded"; fi
  assert_rolled_back "$failed"
done

empty="$temporary/empty"
make_case "$empty" check-fail
rm -rf "$empty/system/fx" "$empty/system/helper" "$empty/system/bootstrap" \
  "$empty/system/brain-installer" "$empty/system/browser" "$empty/system/libexec"
if run_case "$empty" check-fail; then fail "empty check-fail unexpectedly succeeded"; fi
for path in fx helper bootstrap brain-installer browser libexec/factory-browser-sandbox libexec/factory-browser-sandbox-check; do
  [ ! -e "$empty/system/$path" ] || fail "$path was left after rollback"
done

invalid="$temporary/invalid"
make_case "$invalid" success
printf '#!/bin/bash\nif broken\n' >"$invalid/source/ops/fx-factory-release"
if run_case "$invalid" success; then fail "invalid origin/main helper unexpectedly succeeded"; fi
assert_rolled_back "$invalid"
[ ! -s "$invalid/events" ] || fail "invalid origin/main started browser installation"

moved="$temporary/main-moved"
make_case "$moved" success
if run_case "$moved" success aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa; then
  fail "transition accepted a different origin/main commit"
fi
assert_rolled_back "$moved"

echo "PASS: точный origin/main ставится только из закрытого staging и полностью откатывает сбои"
