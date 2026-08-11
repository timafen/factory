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
  : >"$case_dir/worker.toml"
  : >"$case_dir/gate-children"
  : >"$case_dir/handshake-events"

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
assert_gate_handshake() {
  local name=$1 state='' sid_field pgid_field ready_field extra sid pgid actual_sid actual_pgid
  state=$(find "$TEST_RELEASE_DIR" -name "$name" -type f -print -quit)
  [ -n "$state" ] || exit 18
  IFS=' ' read -r sid_field pgid_field ready_field extra <"$state" || exit 18
  case "$sid_field:$pgid_field:$ready_field:$extra" in
    sid=*:pgid=*:ready=1:) ;;
    *) exit 18 ;;
  esac
  sid=${sid_field#sid=}
  pgid=${pgid_field#pgid=}
  case "$sid:$pgid" in
    *[!0-9:]*|:*|*:) exit 18 ;;
  esac
  read -r actual_sid actual_pgid < <(ps -o sid= -o pgid= -p "$$") || exit 18
  [ "$sid" = "$actual_sid" ] && [ "$pgid" = "$actual_pgid" ] || exit 18
  printf 'ui-after-handshake\n' >>"$TEST_HANDSHAKE_EVENTS"
}
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
  signal-forked-gates:tsc)
    assert_gate_handshake ui-checks.session
    (
      trap 'echo ui-term-ignored >>"$TEST_GATE_CHILDREN"' TERM
      trap '' HUP INT
      while :; do /bin/sleep 1; done
    ) &
    : >"$TEST_UI_RUNNING"
    wait "$!"
    ;;
  signal-gates:tsc)
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
assert_gate_handshake() {
  local name=$1 state='' sid_field pgid_field ready_field extra sid pgid actual_sid actual_pgid
  state=$(find "$TEST_RELEASE_DIR" -name "$name" -type f -print -quit)
  [ -n "$state" ] || exit 18
  IFS=' ' read -r sid_field pgid_field ready_field extra <"$state" || exit 18
  case "$sid_field:$pgid_field:$ready_field:$extra" in
    sid=*:pgid=*:ready=1:) ;;
    *) exit 18 ;;
  esac
  sid=${sid_field#sid=}
  pgid=${pgid_field#pgid=}
  case "$sid:$pgid" in
    *[!0-9:]*|:*|*:) exit 18 ;;
  esac
  read -r actual_sid actual_pgid < <(ps -o sid= -o pgid= -p "$$") || exit 18
  [ "$sid" = "$actual_sid" ] && [ "$pgid" = "$actual_pgid" ] || exit 18
  printf 'go-after-handshake\n' >>"$TEST_HANDSHAKE_EVENTS"
}
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
    signal-forked-gates)
      assert_gate_handshake go-checks.session
      (
        trap 'echo go-term-ignored >>"$TEST_GATE_CHILDREN"' TERM
        trap '' HUP INT
        while :; do /bin/sleep 1; done
      ) &
      : >"$TEST_GO_RUNNING"
      wait "$!"
      ;;
    signal-gates)
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
  [ "$TEST_MODE" != release-test-fail ] && [ "$TEST_MODE" != forked-gate-fail ]
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
[ "${1:-}" != --wait ] || shift
case "$TEST_MODE" in
  forked-gates-success|forked-gate-fail|forked-gate-no-result|signal-forked-gates)
    printf 'setsid-forked\n' >>"$TEST_HANDSHAKE_EVENTS"
    /usr/bin/setsid --fork --wait "$@" &
    wait "$!"
    ;;
  signal-before-ready)
    printf 'setsid-before-ready\n' >>"$TEST_HANDSHAKE_EVENTS"
    /usr/bin/setsid --fork --wait /bin/bash -c '
      cd "$1"
      : >"$2"
      trap "" HUP INT TERM
      exec /bin/sleep 30
    ' bash "$TEST_STUCK_CWD" "$TEST_SETSID_STARTED" &
    : >"$TEST_SETSID_STARTED"
    wait "$!"
    ;;
  *) exec /usr/bin/setsid --wait "$@" ;;
esac
EOF
  cat >"$case_dir/bin/as-fork" <<'EOF'
#!/bin/bash
if [[ "${5:-}" = *.session.result ]]; then
  printf 'as-forked\n' >>"$TEST_HANDSHAKE_EVENTS"
  [ "$TEST_MODE" != forked-gate-no-result ] || exit 0
  "$@" &
  exit 0
fi
exec "$@"
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
case "$TEST_MODE" in
  ui-test-fail|signal-forked-gates|signal-before-ready) exec /bin/sleep "$@" ;;
esac
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

configure_release_mode() {
  case_dir=$1 mode=$2
  fixture_release_as=''
  fixture_gate_ready_attempts=500
  fixture_gate_stop_attempts=100
  case "$mode" in
    ui-test-fail|forked-gates-success|forked-gate-fail|forked-gate-no-result|signal-forked-gates|signal-before-ready)
      fixture_gate_ready_attempts=20
      fixture_gate_stop_attempts=20
      ;;
  esac
  case "$mode" in
    forked-gates-success|forked-gate-fail|forked-gate-no-result|signal-forked-gates)
      fixture_release_as="$case_dir/bin/as-fork"
      ;;
  esac
}

run_release() {
  case_dir=$1 mode=$2
  configure_release_mode "$case_dir" "$mode"
  TEST_EVENTS="$case_dir/events" TEST_GATES="$case_dir/gates" TEST_MODE="$mode" \
    TEST_RELEASE_SOURCE="$SCRIPT_DIR/.." TEST_BROKER_EVENTS="$case_dir/broker-events" \
    TEST_SERVER_BIN="$case_dir/install/factory-server" \
    TEST_INTERRUPT_MARK="$case_dir/interrupted" PATH="$case_dir/bin:$PATH" \
    TEST_UI_STARTED="$case_dir/ui-started" TEST_GO_STARTED="$case_dir/go-started" \
    TEST_GO_RUNNING="$case_dir/go-running" TEST_UI_RUNNING="$case_dir/ui-running" \
    TEST_IDENTITY_MARK="$case_dir/identity-retried" \
    TEST_DEFERRED_COMMAND="$case_dir/deferred-pilot-restart" \
    TEST_GATE_CHILDREN="$case_dir/gate-children" \
    TEST_HANDSHAKE_EVENTS="$case_dir/handshake-events" \
    TEST_RELEASE_DIR="$case_dir/releases" TEST_SETSID_STARTED="$case_dir/setsid-started" \
    TEST_STUCK_CWD="$case_dir" \
    FACTORY_RELEASE_REPO="$case_dir/repo" \
    FACTORY_SERVER_BIN="$case_dir/install/factory-server" \
    FACTORY_WORKER_BIN="$case_dir/install/factory-worker" \
    FACTORY_RELEASE_DIR="$case_dir/releases" \
    FACTORY_RELEASE_INFO="$case_dir/current.json" \
    FACTORY_RELEASE_LOCK="$case_dir/release.lock" \
    FACTORY_RELEASE_AS="$fixture_release_as" FACTORY_RELEASE_OWNER='' \
    FACTORY_RELEASE_GATE_READY_ATTEMPTS="$fixture_gate_ready_attempts" \
    FACTORY_RELEASE_GATE_STOP_ATTEMPTS="$fixture_gate_stop_attempts" \
    FACTORY_RELEASE_GATE_POLL_DELAY=0.01 \
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
  configure_release_mode "$case_dir" "$mode"
  TEST_EVENTS="$case_dir/events" TEST_GATES="$case_dir/gates" TEST_MODE="$mode" \
    TEST_RELEASE_SOURCE="$SCRIPT_DIR/.." TEST_BROKER_EVENTS="$case_dir/broker-events" \
    TEST_SERVER_BIN="$case_dir/install/factory-server" \
    TEST_INTERRUPT_MARK="$case_dir/interrupted" PATH="$case_dir/bin:$PATH" \
    TEST_UI_STARTED="$case_dir/ui-started" TEST_GO_STARTED="$case_dir/go-started" \
    TEST_GO_RUNNING="$case_dir/go-running" TEST_UI_RUNNING="$case_dir/ui-running" \
    TEST_IDENTITY_MARK="$case_dir/identity-retried" \
    TEST_DEFERRED_COMMAND="$case_dir/deferred-pilot-restart" \
    TEST_GATE_CHILDREN="$case_dir/gate-children" \
    TEST_HANDSHAKE_EVENTS="$case_dir/handshake-events" \
    TEST_RELEASE_DIR="$case_dir/releases" TEST_SETSID_STARTED="$case_dir/setsid-started" \
    TEST_STUCK_CWD="$case_dir" \
    FACTORY_RELEASE_REPO="$case_dir/repo" \
    FACTORY_SERVER_BIN="$case_dir/install/factory-server" \
    FACTORY_WORKER_BIN="$case_dir/install/factory-worker" \
    FACTORY_RELEASE_DIR="$case_dir/releases" \
    FACTORY_RELEASE_INFO="$case_dir/current.json" \
    FACTORY_RELEASE_LOCK="$case_dir/release.lock" \
    FACTORY_RELEASE_AS="$fixture_release_as" FACTORY_RELEASE_OWNER='' \
    FACTORY_RELEASE_GATE_READY_ATTEMPTS="$fixture_gate_ready_attempts" \
    FACTORY_RELEASE_GATE_STOP_ATTEMPTS="$fixture_gate_stop_attempts" \
    FACTORY_RELEASE_GATE_POLL_DELAY=0.01 \
    FACTORY_RELEASE_BROKER_BIN="$case_dir/install/factory-release-broker" \
    FACTORY_RELEASE_BROKER_UNIT="$case_dir/install/factory-release-broker.service" \
    FACTORY_RELEASE_BROKER_SERVER_DROPIN="$case_dir/install/50-project-release-broker.conf" \
    FACTORY_RELEASE_BROKER_OWNER='' \
    FACTORY_RELEASE_BROKER_SYSTEMCTL="$case_dir/bin/broker-systemctl" \
    FACTORY_RELEASE_BROKER_GETENT="$case_dir/bin/getent" \
    FACTORY_RELEASE_BROKER_GROUPADD="$case_dir/bin/groupadd" \
    FACTORY_WORKER_CONFIG="$case_dir/worker.toml" \
    FACTORY_API_URL=http://test FACTORY_REGISTER_ATTEMPTS=2 FACTORY_REGISTER_DELAY=0 \
    env --default-signal=INT /bin/bash "$RELEASE" main >"$case_dir/output" 2>&1 &
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

forked_success="$temporary/forked-gates-success"
make_fixture "$forked_success" forked-gates-success
run_release "$forked_success" forked-gates-success \
  || { cat "$forked_success/output" >&2; fail "forked gates lost a successful status"; }
[ "$(grep -Fxc 'as-forked' "$forked_success/handshake-events")" -eq 2 ] \
  || fail "successful fork scenario did not fork both gate launchers"
assert_file "$forked_success/install/factory-server" '#!/bin/bash'
assert_file "$forked_success/install/factory-worker" '#!/bin/bash'
assert_no_fixture_processes "$forked_success"

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

forked_failed="$temporary/forked-gate-fail"
make_fixture "$forked_failed" forked-gate-fail
set +e
run_release "$forked_failed" forked-gate-fail
status=$?
set -e
[ "$status" -eq 5 ] || fail "forked failing gate returned $status instead of build error 5"
[ "$(grep -Fxc 'as-forked' "$forked_failed/handshake-events")" -eq 2 ] \
  || fail "failing fork scenario did not fork both gate launchers"
grep -Fx 'bash ops/test-fx-factory-release.sh' "$forked_failed/gates" >/dev/null \
  || fail "forked failure did not reach the actual release gate"
grep -F 'завершилась с кодом 1' "$forked_failed/output" >/dev/null \
  || fail "release did not preserve the actual forked gate status"
assert_file "$forked_failed/install/factory-server" old-server
assert_file "$forked_failed/install/factory-worker" old-worker
[ ! -s "$forked_failed/events" ] || fail "installation ran after a forked gate failure"
! grep -F 'go build ' "$forked_failed/gates" >/dev/null \
  || fail "binaries were built after a forked gate failure"
assert_no_fixture_processes "$forked_failed"

forked_without_result="$temporary/forked-gate-no-result"
make_fixture "$forked_without_result" forked-gate-no-result
SECONDS=0
set +e
run_release "$forked_without_result" forked-gate-no-result
status=$?
set -e
[ "$status" -eq 5 ] || fail "missing forked result returned $status instead of build error 5"
[ "$SECONDS" -lt 3 ] || fail "missing forked result did not fail in bounded time"
[ ! -s "$forked_without_result/events" ] \
  || fail "installation ran without an authoritative gate result"
assert_no_fixture_processes "$forked_without_result"

for signal in HUP INT TERM; do
  signaled="$temporary/signal-forked-$signal"
  make_fixture "$signaled" signal-forked-gates
  start_release "$signaled" signal-forked-gates
  wait_for_file "$signaled/ui-running"
  wait_for_file "$signaled/go-running"
  SECONDS=0
  kill -"$signal" "$release_pid"
  set +e
  wait "$release_pid"
  status=$?
  set -e
  [ "$status" -eq 130 ] || fail "signal $signal returned $status instead of 130"
  [ "$SECONDS" -lt 3 ] || fail "signal $signal did not stop the forked gates in bounded time"
  assert_file "$signaled/install/factory-server" old-server
  assert_file "$signaled/install/factory-worker" old-worker
  [ ! -s "$signaled/events" ] || fail "signal $signal touched services before installation"
  grep -Fx 'setsid-forked' "$signaled/handshake-events" >/dev/null \
    || fail "signal $signal did not force the GNU setsid fork path"
  grep -Fx 'as-forked' "$signaled/handshake-events" >/dev/null \
    || fail "signal $signal did not run the opaque AS intermediary"
  grep -Fx 'ui-after-handshake' "$signaled/handshake-events" >/dev/null \
    || fail "signal $signal started the UI gate before its handshake"
  grep -Fx 'go-after-handshake' "$signaled/handshake-events" >/dev/null \
    || fail "signal $signal started the Go gate before its handshake"
  grep -Fx 'ui-term-ignored' "$signaled/gate-children" >/dev/null \
    || fail "signal $signal did not TERM the UI group before KILL"
  grep -Fx 'go-term-ignored' "$signaled/gate-children" >/dev/null \
    || fail "signal $signal did not TERM the Go group before KILL"
  assert_no_fixture_processes "$signaled"
done

for signal in HUP INT TERM; do
  before_ready="$temporary/signal-before-ready-$signal"
  make_fixture "$before_ready" signal-before-ready
  start_release "$before_ready" signal-before-ready
  wait_for_file "$before_ready/setsid-started"
  SECONDS=0
  kill -"$signal" "$release_pid"
  set +e
  wait "$release_pid"
  status=$?
  set -e
  [ "$status" -eq 130 ] || fail "pre-ready signal $signal returned $status instead of 130"
  [ "$SECONDS" -lt 3 ] || fail "pre-ready signal $signal did not stop the launcher in bounded time"
  assert_file "$before_ready/install/factory-server" old-server
  assert_file "$before_ready/install/factory-worker" old-worker
  [ ! -s "$before_ready/events" ] || fail "pre-ready signal $signal touched services before installation"
  ! grep -F 'after-handshake' "$before_ready/handshake-events" >/dev/null \
    || fail "pre-ready signal $signal allowed a gate to start"
  assert_no_fixture_processes "$before_ready"
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
