#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
RELEASE="$SCRIPT_DIR/fx-factory-release"
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
assert_file() { grep -Fx "$2" "$1" >/dev/null || fail "$1 does not contain: $2"; }

make_fixture() {
  case_dir=$1 mode=$2
  mkdir -p "$case_dir/bin" "$case_dir/install" "$case_dir/releases" "$case_dir/repo/web" "$case_dir/system"
  printf 'old-server\n' >"$case_dir/install/factory-server"
  printf 'old-worker\n' >"$case_dir/install/factory-worker"
  chmod +x "$case_dir/install/factory-server" "$case_dir/install/factory-worker"
  : >"$case_dir/events"
  : >"$case_dir/worker.toml"

  cat >"$case_dir/bin/git" <<'EOF'
#!/bin/bash
case "$*" in
  *'clone --quiet'*)
    destination=${@: -1}
    mkdir -p "$destination/web" "$destination/ops"
    printf '{}\n' >"$destination/web/package.json"
    printf '{}\n' >"$destination/web/package-lock.json"
    for file in fx fx-factory-release install-server-browser.sh factory-browser-sandbox test-browser-sandbox.sh; do
      printf '#!/bin/sh\nprintf "system %%s\\n" "$*" >>"$TEST_SYSTEM_EVENTS"\n' >"$destination/ops/$file"
      chmod 755 "$destination/ops/$file"
    done
    ;;
  *'rev-parse HEAD'*) echo 1234567890abcdef ;;
  *'log -1'*) echo 'Проверочный релиз' ;;
esac
EOF
  cat >"$case_dir/bin/npm" <<'EOF'
#!/bin/bash
echo "npm $*" >>"$TEST_GATES"
[ "$TEST_MODE" != ui-test-fail ] || [ "${1:-}" != test ] || exit 1
exit 0
EOF
  cat >"$case_dir/bin/npx" <<'EOF'
#!/bin/bash
echo "npx $*" >>"$TEST_GATES"
exit 0
EOF
  cat >"$case_dir/bin/go" <<'EOF'
#!/bin/bash
echo "go $*" >>"$TEST_GATES"
[ "${1:-}" != test ] || { [ "$TEST_MODE" != go-test-fail ]; exit; }
output=
while [ "$#" -gt 0 ]; do
  if [ "$1" = -o ]; then output=$2; shift 2; else shift; fi
done
case "$output" in
  *factory-worker)
    [ "$TEST_MODE" != worker-build-fail ] || exit 1
    cat >"$output" <<'WORKER'
#!/bin/bash
[ "${1:-}" = identity ] && { echo worker-release-test; exit 0; }
WORKER
    ;;
  *) printf '#!/bin/bash\nexit 0\n' >"$output" ;;
esac
chmod +x "$output"
EOF
  cat >"$case_dir/bin/bash" <<'EOF'
#!/bin/bash
if [ "${1:-}" = ops/test-fx-factory-release.sh ]; then
  echo "bash $1" >>"$TEST_GATES"
  [ "$TEST_MODE" != release-test-fail ]
  exit
fi
exec /bin/bash "$@"
EOF
  cat >"$case_dir/bin/systemctl" <<'EOF'
#!/bin/bash
echo "$1 $2" >>"$TEST_EVENTS"
exit 0
EOF
  cat >"$case_dir/bin/mv" <<'EOF'
#!/bin/bash
/bin/mv "$@" || exit
target=${@: -1}
if [ "$TEST_MODE" = interrupt-between-install ] \
  && [ "$target" = "$TEST_SERVER_BIN" ] && [ ! -e "$TEST_INTERRUPT_MARK" ]; then
  : >"$TEST_INTERRUPT_MARK"
  kill -TERM "$PPID"
fi
EOF
  cat >"$case_dir/bin/sleep" <<'EOF'
#!/bin/bash
exit 0
EOF
  cat >"$case_dir/bin/chmod" <<'EOF'
#!/bin/bash
if [ "$TEST_MODE" = worker-install-fail ] && [[ "${*: -1}" = *factory-worker.new ]]; then
  exit 1
fi
exec /bin/chmod "$@"
EOF
  cat >"$case_dir/bin/curl" <<'EOF'
#!/bin/bash
case "$*" in
  *'/api/v1/dashboard'*)
    if [ "$TEST_MODE" = server-fail ]; then printf 503; else printf 200; fi ;;
  *'/api/v1/workers/worker-release-test'*)
    if [ "$TEST_MODE" = worker-fail ]; then
      printf '{"id":"worker-release-test","health":"unhealthy","online":false,"last_heartbeat":"2026-08-09T12:00:00Z"}'
    elif [ "$TEST_MODE" = stale-healthy-worker ]; then
      printf '{"id":"worker-release-test","health":"healthy","online":true,"last_heartbeat":"2026-08-09T12:00:00Z"}'
    elif [ "$TEST_MODE" = heartbeat-during-stop ] \
      && grep -F 'stop factory-worker.service' "$TEST_EVENTS" >/dev/null; then
      printf '{"id":"worker-release-test","health":"healthy","online":true,"last_heartbeat":"2026-08-09T12:00:01Z"}'
    elif grep -F 'start factory-worker.service' "$TEST_EVENTS" >/dev/null; then
      printf '{"id":"worker-release-test","health":"healthy","online":true,"last_heartbeat":"2026-08-09T12:00:02Z"}'
    elif grep -F 'stop factory-worker.service' "$TEST_EVENTS" >/dev/null; then
      printf '{"id":"worker-release-test","health":"healthy","online":true,"last_heartbeat":"2026-08-09T12:00:01Z"}'
    else
      printf '{"id":"worker-release-test","health":"healthy","online":true,"last_heartbeat":"2026-08-09T12:00:00Z"}'
    fi ;;
esac
EOF
  chmod +x "$case_dir/bin/"*
}

run_release() {
  case_dir=$1 mode=$2
  TEST_EVENTS="$case_dir/events" TEST_GATES="$case_dir/gates" TEST_MODE="$mode" \
    TEST_SYSTEM_EVENTS="$case_dir/system-events" \
    TEST_SERVER_BIN="$case_dir/install/factory-server" \
    TEST_INTERRUPT_MARK="$case_dir/interrupted" PATH="$case_dir/bin:$PATH" \
    FACTORY_RELEASE_REPO="$case_dir/repo" \
    FACTORY_SERVER_BIN="$case_dir/install/factory-server" \
    FACTORY_WORKER_BIN="$case_dir/install/factory-worker" \
    FACTORY_RELEASE_DIR="$case_dir/releases" \
    FACTORY_RELEASE_INFO="$case_dir/current.json" \
    FACTORY_RELEASE_SYSTEM_INSTALL=1 FACTORY_FX_BIN="$case_dir/system/fx" \
    FACTORY_RELEASE_HELPER="$case_dir/system/fx-factory-release" \
    FACTORY_BROWSER_SHARE="$case_dir/system/browser-sandbox" \
    FACTORY_RELEASE_AS='' FACTORY_RELEASE_OWNER='' \
    FACTORY_WORKER_CONFIG="$case_dir/worker.toml" \
    FACTORY_API_URL=http://test FACTORY_REGISTER_ATTEMPTS=2 FACTORY_REGISTER_DELAY=0 \
    /bin/bash "$RELEASE" main >"$case_dir/output" 2>&1
}

success="$temporary/success"
make_fixture "$success" success
run_release "$success" success || fail "successful release failed"
diff -u <(printf '%s\n' \
  'npm ci --no-audit --no-fund --silent' \
  'npx tsc -p tsconfig.app.json --noEmit' \
  'npm test' \
  'go test ./...' \
  'bash ops/test-fx-factory-release.sh' \
  'npx vite build' \
  'go build -o PLACEHOLDER ./cmd/factory-server' \
  'go build -o PLACEHOLDER ./cmd/factory-worker') \
  <(sed -e 's|-o [^ ]*/factory-server|-o PLACEHOLDER|' \
    -e 's|-o [^ ]*/factory-worker|-o PLACEHOLDER|' "$success/gates") >/dev/null \
  || fail "release gates ran in the wrong order"
assert_file "$success/install/factory-server" '#!/bin/bash'
assert_file "$success/install/factory-worker" '#!/bin/bash'
[ "$(sed -n '1p' "$success/events")" = 'restart factory-server.service' ] \
  || fail "server was not restarted first"
[ "$(sed -n '2p' "$success/events")" = 'stop factory-worker.service' ] \
  || fail "worker was not stopped before taking the heartbeat baseline"
[ "$(sed -n '3p' "$success/events")" = 'start factory-worker.service' ] \
  || fail "worker was not started after taking the heartbeat baseline"
grep -F 'выкачено:' "$success/output" >/dev/null || fail "release did not report success"
[ -x "$success/system/fx" ] || fail "system fx was not installed"
[ -x "$success/system/fx-factory-release" ] || fail "release helper was not installed"
diff -u <(printf '%s\n' \
  'system factory browser-sandbox install' \
  'system factory browser-sandbox check') "$success/system-events" >/dev/null \
  || fail "browser sandbox was not installed and checked during release"

for mode in server-fail worker-fail stale-healthy-worker heartbeat-during-stop worker-install-fail interrupt-between-install; do
  failed="$temporary/$mode"
  make_fixture "$failed" "$mode"
  if run_release "$failed" "$mode"; then fail "$mode unexpectedly succeeded"; fi
  assert_file "$failed/install/factory-server" old-server
  assert_file "$failed/install/factory-worker" old-worker
  tail -n 2 "$failed/events" | diff -u - <(printf '%s\n' \
    'restart factory-server.service' 'restart factory-worker.service') >/dev/null \
    || fail "$mode rollback restart order is wrong"
done

build_failed="$temporary/worker-build-fail"
make_fixture "$build_failed" worker-build-fail
if run_release "$build_failed" worker-build-fail; then fail "worker build unexpectedly succeeded"; fi
assert_file "$build_failed/install/factory-server" old-server
assert_file "$build_failed/install/factory-worker" old-worker
[ ! -s "$build_failed/events" ] || fail "services restarted after a build failure"

for mode in ui-test-fail go-test-fail release-test-fail; do
  gate_failed="$temporary/$mode"
  make_fixture "$gate_failed" "$mode"
  set +e
  run_release "$gate_failed" "$mode"
  status=$?
  set -e
  [ "$status" -eq 5 ] || fail "$mode returned $status instead of build error 5"
  assert_file "$gate_failed/install/factory-server" old-server
  assert_file "$gate_failed/install/factory-worker" old-worker
  [ ! -s "$gate_failed/events" ] || fail "services restarted after $mode"
  ! grep -F 'go build ' "$gate_failed/gates" >/dev/null \
    || fail "binaries were built after $mode"
done

echo "PASS: ворота тестов, единая установка, регистрация и общий откат проверены"
