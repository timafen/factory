#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
RELEASE="$SCRIPT_DIR/fx-factory-release"
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
assert_file() { grep -Fx -- "$2" "$1" >/dev/null || fail "$1 does not contain: $2"; }
wait_for_file() {
  local file=$1 i
  for ((i = 0; i < 500; i++)); do
    [ -e "$file" ] && return 0
    /bin/sleep 0.01
  done
  fail "timed out waiting for $file"
}
wait_for_release_exit() {
  local pid=$1 watchdog marker=$2
  (
    /bin/sleep 5
    if kill -0 "$pid" 2>/dev/null; then
      : >"$marker"
      kill -KILL "$pid" 2>/dev/null || true
    fi
  ) &
  watchdog=$!
  set +e
  wait "$pid"
  RELEASE_STATUS=$?
  set -e
  kill "$watchdog" 2>/dev/null || true
  wait "$watchdog" 2>/dev/null || true
  [ ! -e "$marker" ] || fail "release supervisor did not stop within five seconds"
}
line_of() { grep -nF "$2" "$1" | head -n 1 | cut -d: -f1; }
assert_before() {
  local first second
  first=$(line_of "$1" "$2") || fail "$1 is missing: $2"
  second=$(line_of "$1" "$3") || fail "$1 is missing: $3"
  [ "$first" -lt "$second" ] || fail "$2 did not run before $3"
}
assert_no_fixture_processes() {
  local case_dir=$1 pid args by_cmdline='' by_cwd
  while read -r pid args; do
    [[ "$args" == *"$case_dir"* ]] || continue
    by_cmdline+="${pid} ${args}"$'\n'
  done < <(ps -eo pid=,args=)
  by_cwd=$(find /proc/[0-9]*/cwd -maxdepth 0 -lname "$case_dir*" -printf '%h\n' 2>/dev/null || true)
  if [ -n "$by_cmdline$by_cwd" ]; then
    [ -z "$by_cmdline" ] || echo "leaked fixture cmdline: $by_cmdline" >&2
    [ -z "$by_cwd" ] || echo "leaked fixture cwd: $by_cwd" >&2
    fail "processes survived fixture $case_dir"
  fi
}

make_fixture() {
  case_dir=$1 mode=$2
  mkdir -p "$case_dir/bin" "$case_dir/install" "$case_dir/releases" "$case_dir/repo/web"
  printf 'old-server\n' >"$case_dir/install/factory-server"
  printf 'old-worker\n' >"$case_dir/install/factory-worker"
  chmod +x "$case_dir/install/factory-server" "$case_dir/install/factory-worker"
  : >"$case_dir/events"
  : >"$case_dir/gates"
  : >"$case_dir/worker.toml"

  cat >"$case_dir/bin/git" <<'EOF'
#!/bin/bash
case "$*" in
  *'clone --quiet'*)
    destination=${@: -1}
    mkdir -p "$destination/web" "$destination/ops/systemd"
    /bin/cp "$TEST_RELEASE_SOURCE/ops/install-project-release-broker.sh" \
      "$destination/ops/install-project-release-broker.sh"
    /bin/cp "$TEST_RELEASE_SOURCE/ops/systemd/factory-release-broker.service" \
      "$destination/ops/systemd/factory-release-broker.service"
    cat >"$destination/ops/install-brain.sh" <<'BRAIN'
#!/bin/bash
echo "brain defer=${FACTORY_BRAIN_DEFER_PILOT_RESTART:-} marker=${FACTORY_BRAIN_RESTART_MARKER:-}" >>"$TEST_GATES"
[ "$TEST_MODE" != brain-install-fail ] || exit 7
[ "${FACTORY_BRAIN_DEFER_PILOT_RESTART:-}" = 1 ] || exit 9
: >"$FACTORY_BRAIN_RESTART_MARKER"
BRAIN
    touch "$destination/ops/install-server-browser.sh"
    chmod +x "$destination/ops/install-brain.sh"
    chmod +x "$destination/ops/install-project-release-broker.sh"
    chmod +x "$destination/ops/install-server-browser.sh"
    ;;
  *'rev-parse HEAD'*) echo 1234567890abcdef ;;
  *'log -1 --pretty=%s'*) echo 'Merge pull request #123 from factory/readable-release' ;;
  *'log -1 --pretty=%B'*) printf 'Merge pull request #123 from factory/readable-release\n\nПроверочный релиз (#123)\n' ;;
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
wait_for_file() {
  local file=$1 i
  for ((i = 0; i < 500; i++)); do
    [ -e "$file" ] && return 0
    /bin/sleep 0.01
  done
  exit 9
}
case "$TEST_MODE:${1:-}" in
  parallel-success:tsc)
    : >"$TEST_UI_STARTED"
    wait_for_file "$TEST_GO_STARTED"
    ;;
  ui-test-fail:tsc)
    : >"$TEST_UI_STARTED"
    wait_for_file "$TEST_GO_RUNNING"
    ;;
  signal-gates:tsc)
    : >"$TEST_UI_RUNNING"
    trap 'echo ui-stopped >>"$TEST_GATE_CHILDREN"; exit 143' HUP INT TERM
    while :; do /bin/sleep 0.01; done
    ;;
  signal-gates-term-ignoring-child:tsc)
    (
      trap 'echo ui-term-ignored >>"$TEST_GATE_CHILDREN"' TERM
      : >"$TEST_UI_TERM_CHILD"
      while :; do /bin/sleep 0.01; done
    ) &
    wait_for_file "$TEST_UI_TERM_CHILD"
    : >"$TEST_UI_RUNNING"
    trap 'echo ui-stopped >>"$TEST_GATE_CHILDREN"; exit 143' HUP INT TERM
    while :; do /bin/sleep 0.01; done
    ;;
  signal-before-pgid-go:tsc)
    : >"$TEST_UI_RUNNING"
    trap 'echo ui-stopped >>"$TEST_GATE_CHILDREN"; exit 143' HUP INT TERM
    while :; do /bin/sleep 0.01; done
    ;;
esac
exit 0
EOF
  cat >"$case_dir/bin/go" <<'EOF'
#!/bin/bash
echo "go $*" >>"$TEST_GATES"
if [ "${1:-}" = test ]; then
  wait_for_file() {
    local file=$1 i
    for ((i = 0; i < 500; i++)); do
      [ -e "$file" ] && return 0
      /bin/sleep 0.01
    done
    exit 9
  }
  case "$TEST_MODE" in
    parallel-success)
      : >"$TEST_GO_STARTED"
      wait_for_file "$TEST_UI_STARTED"
      ;;
    ui-test-fail)
      : >"$TEST_GO_STARTED"
      wait_for_file "$TEST_UI_STARTED"
      : >"$TEST_GO_RUNNING"
      trap 'echo go-stopped >>"$TEST_GATE_CHILDREN"; exit 143' HUP INT TERM
      while :; do /bin/sleep 0.01; done
      ;;
    signal-gates)
      : >"$TEST_GO_RUNNING"
      trap 'echo go-stopped >>"$TEST_GATE_CHILDREN"; exit 143' HUP INT TERM
      while :; do /bin/sleep 0.01; done
      ;;
    signal-gates-term-ignoring-child)
      (
        trap 'echo go-term-ignored >>"$TEST_GATE_CHILDREN"' TERM
        : >"$TEST_GO_TERM_CHILD"
        while :; do /bin/sleep 0.01; done
      ) &
      wait_for_file "$TEST_GO_TERM_CHILD"
      : >"$TEST_GO_RUNNING"
      trap 'echo go-stopped >>"$TEST_GATE_CHILDREN"; exit 143' HUP INT TERM
      while :; do /bin/sleep 0.01; done
      ;;
    go-test-fail) exit 1 ;;
  esac
  exit 0
fi
output=
while [ "$#" -gt 0 ]; do
  if [ "$1" = -o ]; then output=$2; shift 2; else shift; fi
done
case "$output" in
  *factory-worker)
    [ "$TEST_MODE" != worker-build-fail ] || exit 1
    cat >"$output" <<'WORKER'
#!/bin/bash
[ "${1:-}" = identity ] && {
  grep -F 'stop factory-worker.service' "$TEST_EVENTS" >/dev/null || exit 9
  if [ "$TEST_MODE" = identity-transient ] && [ ! -e "$TEST_IDENTITY_MARK" ]; then
    : >"$TEST_IDENTITY_MARK"
    echo 'data directory is still releasing its lock' >&2
    exit 9
  fi
  echo worker-release-test
  exit 0
}
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
if [[ "${1:-}" = */ops/install-factory-control.sh ]]; then
  echo "bash ops/install-factory-control.sh" >>"$TEST_GATES"
  [ "$TEST_MODE" != control-install-fail ]
  exit
fi
if [[ "${1:-}" = */ops/install-server-browser.sh ]]; then
  echo "bash ops/install-server-browser.sh" >>"$TEST_GATES"
  [ "$TEST_MODE" != browser-install-fail ]
  exit
fi
if [[ "${1:-}" = */ops/provision-codex-auth.sh ]]; then
  echo "bash ops/provision-codex-auth.sh" >>"$TEST_GATES"
  [ "$TEST_MODE" != auth-provision-fail ]
  exit
fi
exec /bin/bash "$@"
EOF
  cat >"$case_dir/bin/setsid" <<'EOF'
#!/bin/bash
# The UI launcher has not entered setsid yet; its direct launcher PID must be
# stopped after the supervisor's bounded readiness wait.
case "${TEST_MODE}:${5:-}" in
  signal-before-pgid-ui:*ui-checks.pid)
    : >"$TEST_UI_SETSID_PENDING"
    delay_pid=''
    stop_delay() {
      [ -z "$delay_pid" ] || kill -TERM "$delay_pid" 2>/dev/null || true
      [ -z "$delay_pid" ] || wait "$delay_pid" 2>/dev/null || true
      exit 143
    }
    trap stop_delay HUP INT TERM
    /bin/sleep 2 &
    delay_pid=$!
    wait "$delay_pid"
    exec /usr/bin/setsid "$@"
    ;;
  # Here setsid already made a session, but the gate's pid file is delayed.
  # The supervisor must discover and stop this group before the readiness file.
  signal-before-pgid-go:*go-checks.pid)
    exec /usr/bin/setsid /bin/bash -c '
      : >"$1"
      shift
      /bin/sleep 2
      exec "$@"
    ' bash "$TEST_GO_SETSID_PENDING" "$@"
    ;;
esac
exec /usr/bin/setsid "$@"
EOF
  cat >"$case_dir/bin/systemctl" <<'EOF'
#!/bin/bash
echo "$1 $2" >>"$TEST_EVENTS"
exit 0
EOF
  cat >"$case_dir/bin/broker-systemctl" <<'EOF'
#!/bin/bash
echo "$*" >>"$TEST_BROKER_EVENTS"
[ "${1:-}" != is-active ]
EOF
  cat >"$case_dir/bin/getent" <<'EOF'
#!/bin/bash
exit 1
EOF
  cat >"$case_dir/bin/groupadd" <<'EOF'
#!/bin/bash
echo "$*" >>"$TEST_BROKER_EVENTS"
EOF
  cat >"$case_dir/bin/systemd-run" <<'EOF'
#!/bin/bash
[ -r "$FACTORY_RELEASE_INFO" ] || exit 9
echo 'release-info ready' >>"$TEST_EVENTS"
echo "systemd-run $*" >>"$TEST_EVENTS"
[ "$TEST_MODE" != systemd-run-fail ] || exit 1
capture=0
for arg in "$@"; do
  [ "$arg" != /usr/bin/flock ] || capture=1
  [ "$capture" = 0 ] || printf '%q ' "$arg"
done >"$TEST_DEFERRED_COMMAND"
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
    TEST_RELEASE_SOURCE="$SCRIPT_DIR/.." TEST_BROKER_EVENTS="$case_dir/broker-events" \
    TEST_SERVER_BIN="$case_dir/install/factory-server" \
    TEST_INTERRUPT_MARK="$case_dir/interrupted" PATH="$case_dir/bin:$PATH" \
    TEST_UI_STARTED="$case_dir/ui-started" TEST_GO_STARTED="$case_dir/go-started" \
    TEST_GO_RUNNING="$case_dir/go-running" TEST_UI_RUNNING="$case_dir/ui-running" \
    TEST_UI_TERM_CHILD="$case_dir/ui-term-child" TEST_GO_TERM_CHILD="$case_dir/go-term-child" \
    TEST_UI_SETSID_PENDING="$case_dir/ui-setsid-pending" \
    TEST_GO_SETSID_PENDING="$case_dir/go-setsid-pending" \
    TEST_IDENTITY_MARK="$case_dir/identity-retried" \
    TEST_DEFERRED_COMMAND="$case_dir/deferred-pilot-restart" \
    TEST_GATE_CHILDREN="$case_dir/gate-children" \
    FACTORY_RELEASE_REPO="$case_dir/repo" \
    FACTORY_SERVER_BIN="$case_dir/install/factory-server" \
    FACTORY_WORKER_BIN="$case_dir/install/factory-worker" \
    FACTORY_RELEASE_DIR="$case_dir/releases" \
    FACTORY_RELEASE_INFO="$case_dir/current.json" \
    FACTORY_RELEASE_LOCK="$case_dir/release.lock" \
    FACTORY_RELEASE_AS='' FACTORY_RELEASE_OWNER='' \
    FACTORY_RELEASE_BROKER_BIN="$case_dir/install/factory-release-broker" \
    FACTORY_RELEASE_BROKER_UNIT="$case_dir/install/factory-release-broker.service" \
    FACTORY_RELEASE_BROKER_SERVER_DROPIN="$case_dir/install/50-project-release-broker.conf" \
    FACTORY_RELEASE_BROKER_OWNER='' \
    FACTORY_RELEASE_BROKER_SYSTEMCTL="$case_dir/bin/broker-systemctl" \
    FACTORY_RELEASE_BROKER_GETENT="$case_dir/bin/getent" \
    FACTORY_RELEASE_BROKER_GROUPADD="$case_dir/bin/groupadd" \
    FACTORY_WORKER_CONFIG="$case_dir/worker.toml" \
    FACTORY_WORKER_SERVICES="factory-worker.service factory-worker-2.service" \
    FACTORY_API_URL=http://test FACTORY_REGISTER_ATTEMPTS=2 FACTORY_REGISTER_DELAY=0 \
    /bin/bash "$RELEASE" main >"$case_dir/output" 2>&1
}

start_release() {
  case_dir=$1 mode=$2
  TEST_EVENTS="$case_dir/events" TEST_GATES="$case_dir/gates" TEST_MODE="$mode" \
    TEST_RELEASE_SOURCE="$SCRIPT_DIR/.." TEST_BROKER_EVENTS="$case_dir/broker-events" \
    TEST_SERVER_BIN="$case_dir/install/factory-server" \
    TEST_INTERRUPT_MARK="$case_dir/interrupted" PATH="$case_dir/bin:$PATH" \
    TEST_UI_STARTED="$case_dir/ui-started" TEST_GO_STARTED="$case_dir/go-started" \
    TEST_GO_RUNNING="$case_dir/go-running" TEST_UI_RUNNING="$case_dir/ui-running" \
    TEST_UI_TERM_CHILD="$case_dir/ui-term-child" TEST_GO_TERM_CHILD="$case_dir/go-term-child" \
    TEST_UI_SETSID_PENDING="$case_dir/ui-setsid-pending" \
    TEST_GO_SETSID_PENDING="$case_dir/go-setsid-pending" \
    TEST_IDENTITY_MARK="$case_dir/identity-retried" \
    TEST_DEFERRED_COMMAND="$case_dir/deferred-pilot-restart" \
    TEST_GATE_CHILDREN="$case_dir/gate-children" \
    FACTORY_RELEASE_REPO="$case_dir/repo" \
    FACTORY_SERVER_BIN="$case_dir/install/factory-server" \
    FACTORY_WORKER_BIN="$case_dir/install/factory-worker" \
    FACTORY_RELEASE_DIR="$case_dir/releases" \
    FACTORY_RELEASE_INFO="$case_dir/current.json" \
    FACTORY_RELEASE_LOCK="$case_dir/release.lock" \
    FACTORY_RELEASE_AS='' FACTORY_RELEASE_OWNER='' \
    FACTORY_RELEASE_BROKER_BIN="$case_dir/install/factory-release-broker" \
    FACTORY_RELEASE_BROKER_UNIT="$case_dir/install/factory-release-broker.service" \
    FACTORY_RELEASE_BROKER_SERVER_DROPIN="$case_dir/install/50-project-release-broker.conf" \
    FACTORY_RELEASE_BROKER_OWNER='' \
    FACTORY_RELEASE_BROKER_SYSTEMCTL="$case_dir/bin/broker-systemctl" \
    FACTORY_RELEASE_BROKER_GETENT="$case_dir/bin/getent" \
    FACTORY_RELEASE_BROKER_GROUPADD="$case_dir/bin/groupadd" \
    FACTORY_WORKER_CONFIG="$case_dir/worker.toml" \
    FACTORY_API_URL=http://test FACTORY_REGISTER_ATTEMPTS=2 FACTORY_REGISTER_DELAY=0 \
    /bin/bash "$RELEASE" main >"$case_dir/output" 2>&1 &
  release_pid=$!
}

success="$temporary/success"
make_fixture "$success" parallel-success
run_release "$success" parallel-success \
  || { cat "$success/output" >&2; fail "successful release failed"; }
wait_for_file "$success/ui-started"
wait_for_file "$success/go-started"
for gate in 'npx tsc -p tsconfig.app.json --noEmit' 'npm test' \
  'go test ./...' 'bash ops/test-fx-factory-release.sh'; do
  assert_before "$success/gates" "$gate" 'npx vite build'
done
assert_before "$success/gates" 'npx vite build' 'go build -o '
grep -F 'полный вывод: UI-проверки' "$success/output" >/dev/null \
  || fail "UI output was not kept separate"
grep -F 'полный вывод: Go-проверки и сценарий выката' "$success/output" >/dev/null \
  || fail "Go output was not kept separate"
assert_file "$success/install/factory-server" '#!/bin/bash'
assert_file "$success/install/factory-worker" '#!/bin/bash'
assert_file "$success/install/factory-release-broker" '#!/bin/bash'
assert_file "$success/install/factory-release-broker.service" 'Group=factory-release'
assert_file "$success/install/50-project-release-broker.conf" 'SupplementaryGroups=factory-release'
assert_file "$success/broker-events" '--system factory-release'
assert_file "$success/broker-events" 'enable --now factory-release-broker.service'
[ "$(sed -n '1p' "$success/events")" = 'restart factory-server.service' ] \
  || fail "server was not restarted first"
[ "$(sed -n '2p' "$success/events")" = 'stop factory-worker.service' ] \
  || fail "worker was not stopped before taking the heartbeat baseline"
[ "$(sed -n '3p' "$success/events")" = 'stop factory-worker-2.service' ] \
  || fail "second worker was not stopped before the heartbeat baseline"
[ "$(sed -n '4p' "$success/events")" = 'start factory-worker.service' ] \
  || fail "worker was not started after taking the heartbeat baseline"
[ "$(sed -n '5p' "$success/events")" = 'start factory-worker-2.service' ] \
  || fail "second worker was not started after taking the heartbeat baseline"
assert_before "$success/events" 'release-info ready' 'systemd-run '
grep -E "^systemd-run .*--on-active=30s /usr/bin/flock -n $success/release.lock /bin/systemctl restart factory-pilot.service$" \
  "$success/events" >/dev/null \
  || fail "Pilot restart did not use the release lock after release metadata"
exec 8>"$success/release.lock"
flock -n 8 || fail "could not acquire successful fixture release lock"
deferred_command=$(sed "s|/bin/systemctl|$success/bin/systemctl|" "$success/deferred-pilot-restart")
if TEST_EVENTS="$success/events" /bin/bash -c "$deferred_command"; then
  fail "outdated Pilot restart ran while a newer release held the lock"
fi
! grep -Fx 'restart factory-pilot.service' "$success/events" >/dev/null \
  || fail "outdated Pilot restart reached systemctl while the lock was held"
flock -u 8
TEST_EVENTS="$success/events" /bin/bash -c "$deferred_command" \
  || fail "current Pilot restart did not run after the release lock was freed"
[ "$(grep -Fxc 'restart factory-pilot.service' "$success/events")" -eq 1 ] \
  || fail "Pilot restart did not run exactly once after the release lock was freed"
grep -F 'выкачено:' "$success/output" >/dev/null || fail "release did not report success"
grep -F 'Проверочный релиз' "$success/output" >/dev/null \
  || fail "release did not explain the deployed change"
! grep -F 'Merge pull request' "$success/output" >/dev/null \
  || fail "release exposed GitHub merge plumbing instead of a human title"
! grep -F '#123' "$success/output" >/dev/null \
  || fail "release exposed a pull request number in owner-facing output"
! grep -F '1234567890abcdef' "$success/output" >/dev/null \
  || fail "release exposed a bare technical version in owner-facing output"

identity_retry="$temporary/identity-transient"
make_fixture "$identity_retry" identity-transient
run_release "$identity_retry" identity-transient \
  || { cat "$identity_retry/output" >&2; fail "transient identity lock was not retried"; }
[ -e "$identity_retry/identity-retried" ] || fail "identity retry scenario did not exercise the transient failure"

for mode in server-fail worker-fail stale-healthy-worker heartbeat-during-stop worker-install-fail interrupt-between-install control-install-fail browser-install-fail; do
  failed="$temporary/$mode"
  make_fixture "$failed" "$mode"
  set +e
  run_release "$failed" "$mode"
  status=$?
  set -e
  [ "$status" -ne 0 ] || fail "$mode unexpectedly succeeded"
  if [ "$mode" = browser-install-fail ]; then
    [ "$status" -eq 7 ] || fail "browser-install-fail returned $status instead of release error 7"
  fi
  assert_file "$failed/install/factory-server" old-server
  assert_file "$failed/install/factory-worker" old-worker
  tail -n 3 "$failed/events" | diff -u - <(printf '%s\n' \
    'restart factory-server.service' 'restart factory-worker.service' 'restart factory-worker-2.service') >/dev/null \
    || fail "$mode rollback restart order is wrong"
  assert_no_fixture_processes "$failed"
done

brain_failed="$temporary/brain-install-fail"
make_fixture "$brain_failed" brain-install-fail
if run_release "$brain_failed" brain-install-fail; then fail "brain-install-fail unexpectedly succeeded"; fi
assert_file "$brain_failed/install/factory-server" old-server
assert_file "$brain_failed/install/factory-worker" old-worker
tail -n 3 "$brain_failed/events" | diff -u - <(printf '%s\n' \
  'restart factory-server.service' 'restart factory-worker.service' 'restart factory-worker-2.service') >/dev/null \
  || fail "brain-install-fail did not roll back the binary pair"
! grep -F 'systemd-run ' "$brain_failed/events" >/dev/null \
  || fail "failed brain install scheduled a Pilot restart"
assert_no_fixture_processes "$brain_failed"

brain_failed_with_info="$temporary/brain-install-fail-with-info"
make_fixture "$brain_failed_with_info" brain-install-fail
printf 'previous-release-info\n' >"$brain_failed_with_info/current.json"
if run_release "$brain_failed_with_info" brain-install-fail; then
  fail "brain-install-fail with previous info unexpectedly succeeded"
fi
assert_file "$brain_failed_with_info/current.json" previous-release-info
assert_no_fixture_processes "$brain_failed_with_info"

systemd_failed="$temporary/systemd-run-fail"
make_fixture "$systemd_failed" systemd-run-fail
printf 'previous-release-info\n' >"$systemd_failed/current.json"
if run_release "$systemd_failed" systemd-run-fail; then
  fail "systemd-run-fail unexpectedly succeeded"
fi
assert_file "$systemd_failed/install/factory-server" old-server
assert_file "$systemd_failed/install/factory-worker" old-worker
assert_file "$systemd_failed/current.json" previous-release-info
assert_no_fixture_processes "$systemd_failed"

systemd_failed_without_info="$temporary/systemd-run-fail-without-info"
make_fixture "$systemd_failed_without_info" systemd-run-fail
if run_release "$systemd_failed_without_info" systemd-run-fail; then
  fail "systemd-run-fail without previous info unexpectedly succeeded"
fi
assert_file "$systemd_failed_without_info/install/factory-server" old-server
assert_file "$systemd_failed_without_info/install/factory-worker" old-worker
[ ! -e "$systemd_failed_without_info/current.json" ] \
  || fail "failed systemd-run left newly written release-info"
assert_no_fixture_processes "$systemd_failed_without_info"

build_failed="$temporary/worker-build-fail"
make_fixture "$build_failed" worker-build-fail
if run_release "$build_failed" worker-build-fail; then fail "worker build unexpectedly succeeded"; fi
assert_file "$build_failed/install/factory-server" old-server
assert_file "$build_failed/install/factory-worker" old-worker
[ ! -s "$build_failed/events" ] || fail "services restarted after a build failure"
assert_no_fixture_processes "$build_failed"

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
  assert_no_fixture_processes "$gate_failed"
done
grep -Fx 'go-stopped' "$temporary/ui-test-fail/gate-children" >/dev/null \
  || fail "a failed UI group did not stop and reap the Go group"

for signal in HUP INT TERM; do
  for attempt in 1 2 3 4 5; do
    signaled="$temporary/signal-$signal-$attempt"
    make_fixture "$signaled" signal-gates
    start_release "$signaled" signal-gates
    wait_for_file "$signaled/ui-running"
    wait_for_file "$signaled/go-running"
    kill -"$signal" "$release_pid"
    wait_for_release_exit "$release_pid" "$signaled/supervisor-timeout"
    status=$RELEASE_STATUS
    [ "$status" -eq 130 ] || fail "signal $signal attempt $attempt returned $status instead of 130"
    assert_file "$signaled/install/factory-server" old-server
    assert_file "$signaled/install/factory-worker" old-worker
    [ ! -s "$signaled/events" ] || fail "signal $signal touched services before installation"
    grep -Fx 'ui-stopped' "$signaled/gate-children" >/dev/null \
      || fail "signal $signal left the UI test group running"
    grep -Fx 'go-stopped' "$signaled/gate-children" >/dev/null \
      || fail "signal $signal left the Go test group running"
    assert_no_fixture_processes "$signaled"
  done
done

term_ignoring="$temporary/term-ignoring-children"
make_fixture "$term_ignoring" signal-gates-term-ignoring-child
start_release "$term_ignoring" signal-gates-term-ignoring-child
wait_for_file "$term_ignoring/ui-running"
wait_for_file "$term_ignoring/go-running"
wait_for_file "$term_ignoring/ui-term-child"
wait_for_file "$term_ignoring/go-term-child"
kill -TERM "$release_pid"
wait_for_release_exit "$release_pid" "$term_ignoring/supervisor-timeout"
[ "$RELEASE_STATUS" -eq 130 ] \
  || fail "TERM with ignoring children returned $RELEASE_STATUS instead of 130"
grep -Fx 'ui-term-ignored' "$term_ignoring/gate-children" >/dev/null \
  || fail "TERM did not reach the UI child that ignores it"
grep -Fx 'go-term-ignored' "$term_ignoring/gate-children" >/dev/null \
  || fail "TERM did not reach the Go child that ignores it"
[ "$(grep -Fc 'TERM не остановил process group' "$term_ignoring/output")" -ge 2 ] \
  || fail "TERM did not escalate to KILL for both test groups"
assert_file "$term_ignoring/install/factory-server" old-server
assert_file "$term_ignoring/install/factory-worker" old-worker
[ ! -s "$term_ignoring/events" ] || fail "TERM with ignoring children touched services"
! grep -F 'npx vite build' "$term_ignoring/gates" >/dev/null \
  || fail "TERM with ignoring children reached the UI build"
! grep -F 'go build ' "$term_ignoring/gates" >/dev/null \
  || fail "TERM with ignoring children reached production install"
assert_no_fixture_processes "$term_ignoring"

for signal in HUP INT TERM; do
  for gate in ui go; do
    pending="$temporary/signal-$signal-before-pgid-$gate"
    make_fixture "$pending" "signal-before-pgid-$gate"
    start_release "$pending" "signal-before-pgid-$gate"
    if [ "$gate" = ui ]; then
      wait_for_file "$pending/ui-setsid-pending"
    else
      wait_for_file "$pending/ui-running"
      wait_for_file "$pending/go-setsid-pending"
    fi
    kill -"$signal" "$release_pid"
    wait_for_release_exit "$release_pid" "$pending/supervisor-timeout"
    [ "$RELEASE_STATUS" -eq 130 ] \
      || fail "$signal before $gate PGID readiness returned $RELEASE_STATUS instead of 130"
    assert_file "$pending/install/factory-server" old-server
    assert_file "$pending/install/factory-worker" old-worker
    [ ! -s "$pending/events" ] \
      || fail "$signal before $gate PGID readiness touched services"
    ! grep -F 'npx vite build' "$pending/gates" >/dev/null \
      || fail "$signal before $gate PGID readiness reached the UI build"
    ! grep -F 'go build ' "$pending/gates" >/dev/null \
      || fail "$signal before $gate PGID readiness reached production install"
    assert_no_fixture_processes "$pending"
  done
done

auth_failed="$temporary/auth-provision-fail"
make_fixture "$auth_failed" auth-provision-fail
set +e
run_release "$auth_failed" auth-provision-fail
status=$?
set -e
[ "$status" -eq 5 ] || fail "auth-provision-fail returned $status instead of build error 5"
assert_file "$auth_failed/install/factory-server" old-server
assert_file "$auth_failed/install/factory-worker" old-worker
[ ! -s "$auth_failed/events" ] || fail "services restarted after unsafe Codex auth"
! grep -F 'bash ops/install-factory-control.sh' "$auth_failed/gates" >/dev/null \
  || fail "control installation ran after unsafe Codex auth"
grep -F 'авторизация Codex не прошла безопасную проверку' "$auth_failed/output" >/dev/null \
  || fail "release did not explain the Codex auth failure"
assert_no_fixture_processes "$auth_failed"

locked="$temporary/locked"
make_fixture "$locked" locked
exec 8>"$locked/release.lock"
flock -n 8 || fail "could not acquire fixture release lock"
set +e
run_release "$locked" locked
status=$?
set -e
flock -u 8
[ "$status" -eq 8 ] || fail "concurrent release returned $status instead of lock error 8"
[ ! -s "$locked/gates" ] || fail "concurrent release passed build gates"
[ ! -s "$locked/events" ] || fail "concurrent release touched services"

echo "PASS: ворота тестов, единая установка, регистрация и общий откат проверены"
