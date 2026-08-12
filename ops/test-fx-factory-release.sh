#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
RELEASE="$SCRIPT_DIR/fx-factory-release"
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
assert_file() { grep -F -- "$2" "$1" >/dev/null || fail "$1 does not contain: $2"; }
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
  mkdir -p "$case_dir/bin" "$case_dir/trusted" "$case_dir/install" "$case_dir/releases" "$case_dir/repo/web" \
    "$case_dir/live/pilot" "$case_dir/live/intake" "$case_dir/database"
  cat >"$case_dir/install/factory-server" <<'EOF'
#!/bin/bash
# old-server
case " $* " in
  *' version '*) echo 'factory-server test old-release-sha' ;;
  *' -backup '*)
    if [ "${TEST_MODE:-}" = snapshot-schema-newer ]; then
      echo 'factory-server: validate live Factory database: backup schema is newer than this Factory binary supports' >&2
      exit 1
    fi
    echo backup-snapshot >>"$TEST_EVENTS"
    while [ "$#" -gt 0 ]; do case "$1" in -database) db=$2; shift 2;; -backup) out=$2; shift 2;; *) shift;; esac; done
    case "$out" in */releases/.generation-*) exit 91;; esac
    python3 - "$db" "$out" <<'PY'
import sqlite3,sys
source=sqlite3.connect(sys.argv[1]); target=sqlite3.connect(sys.argv[2]); source.backup(target); target.close(); source.close()
open(sys.argv[2]+'.v2-control-plane','w').write('factory-control-plane-v2\n')
PY
    ;;
esac
EOF
  cat >"$case_dir/install/factory-worker" <<'EOF'
#!/bin/bash
# old-worker
[ "${1:-}" = version ] && echo 'factory-worker test old-release-sha'
EOF
  printf '#!/bin/bash\nexit 0\n' >"$case_dir/install/factory-release-broker"
  /bin/cp "$SCRIPT_DIR/systemd/factory-release-broker.service" "$case_dir/install/factory-release-broker.service"
  printf '[Service]\nSupplementaryGroups=factory-release\n' >"$case_dir/install/50-project-release-broker.conf"
  printf '#!/bin/bash\nexit 0\n' >"$case_dir/install/fx"
  /bin/cp "$RELEASE" "$case_dir/install/fx-factory-release"
  printf 'old pilot\n' >"$case_dir/live/pilot/pilot.py"
  printf 'old context\n' >"$case_dir/live/pilot/context.md"
  printf 'old intake app\n' >"$case_dir/live/intake/app.py"
  printf 'old intake plan\n' >"$case_dir/live/intake/plan.py"
  python3 - "$case_dir/database/factory.sqlite3" <<'PY'
import sqlite3,sys
d=sqlite3.connect(sys.argv[1]); d.execute('create table schema_migrations(version integer primary key, applied_at integer not null)'); d.execute('insert into schema_migrations values(1,0)'); d.commit(); d.close()
open(sys.argv[1]+'.v2-control-plane','w').write('factory-control-plane-v2\n')
PY
  printf '{"name":"old","sha":"old-release-sha"}\n' >"$case_dir/current.json"
  # The real release gate runs this test under umask 077.  Set the fixture
  # modes explicitly so the rollback preflight verifies production-like
  # artifacts instead of inheriting the caller's umask.
  chmod 755 "$case_dir/install/factory-server" "$case_dir/install/factory-worker" \
    "$case_dir/install/factory-release-broker" "$case_dir/install/fx" "$case_dir/install/fx-factory-release"
  chmod 644 "$case_dir/install/factory-release-broker.service" \
    "$case_dir/install/50-project-release-broker.conf" \
    "$case_dir/live/pilot/pilot.py" "$case_dir/live/pilot/context.md" \
    "$case_dir/live/intake/app.py" "$case_dir/live/intake/plan.py"
  : >"$case_dir/events"
  : >"$case_dir/worker.toml"

  cat >"$case_dir/bin/git" <<'EOF'
#!/bin/bash
case "$*" in
  *'clone --quiet'*)
    printf 'checkout-umask=%s\n' "$(umask)" >>"$TEST_GATES"
    destination=${@: -1}
    mkdir -p "$destination/web" "$destination/ops/systemd"
    /bin/cp "$TEST_RELEASE_SOURCE/ops/install-project-release-broker.sh" \
      "$destination/ops/install-project-release-broker.sh"
    /bin/cp "$TEST_RELEASE_SOURCE/ops/systemd/factory-release-broker.service" \
      "$destination/ops/systemd/factory-release-broker.service"
    mkdir -p "$destination/pilot" "$destination/intake"
    /bin/cp "$TEST_RELEASE_SOURCE/ops/fx" "$destination/ops/fx"
    /bin/cp "$TEST_RELEASE_SOURCE/ops/fx-factory-release" "$destination/ops/fx-factory-release"
    cat >"$destination/ops/test-fx-factory-release.sh" <<'SELF_TEST'
#!/bin/bash
echo "bash ops/test-fx-factory-release.sh" >>"$TEST_GATES"
[ "$TEST_MODE" != release-test-fail ]
SELF_TEST
    chmod 755 "$destination/ops/test-fx-factory-release.sh"
    /bin/cp "$TEST_RELEASE_SOURCE/pilot/pilot.py" "$destination/pilot/pilot.py"
    /bin/cp "$TEST_RELEASE_SOURCE/pilot/context.md" "$destination/pilot/context.md"
    /bin/cp "$TEST_RELEASE_SOURCE/intake/app.py" "$destination/intake/app.py"
    /bin/cp "$TEST_RELEASE_SOURCE/intake/plan.py" "$destination/intake/plan.py"
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
    go-test-fail) exit 1 ;;
  esac
  exit 0
fi
output=
while [ "$#" -gt 0 ]; do
  if [ "$1" = -o ]; then output=$2; shift 2; else shift; fi
done
case "$output" in
  *factory-server)
    cat >"$output" <<'SERVER'
#!/bin/bash
case " $* " in
  *' version '*) echo 'factory-server test 1234567890abcdef' ;;
  *' -backup '*)
    echo candidate-backup-snapshot >>"$TEST_EVENTS"
    while [ "$#" -gt 0 ]; do case "$1" in -database) db=$2; shift 2;; -backup) out=$2; shift 2;; *) shift;; esac; done
    python3 - "$db" "$out" <<'PY'
import sqlite3,sys
source=sqlite3.connect(sys.argv[1]); target=sqlite3.connect(sys.argv[2]); source.backup(target); target.close(); source.close()
open(sys.argv[2]+'.v2-control-plane','w').write('factory-control-plane-v2\n')
PY
    ;;
  *' -restore '*)
    while [ "$#" -gt 0 ]; do case "$1" in -database) db=$2; shift 2;; -restore) source=$2; shift 2;; *) shift;; esac; done
    python3 - "$source" "$db" <<'PY'
import sqlite3,sys
s=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close(); s.close()
open(sys.argv[2]+'.v2-control-plane','w').write('factory-control-plane-v2\n')
PY
    ;;
esac
SERVER
    ;;
  *factory-worker)
    [ "$TEST_MODE" != worker-build-fail ] || exit 1
    cat >"$output" <<'WORKER'
#!/bin/bash
[ "${1:-}" = version ] && { echo 'factory-worker test 1234567890abcdef'; exit 0; }
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
  cat >"$case_dir/bin/systemctl" <<'EOF'
#!/bin/bash
case "$*" in
  '-q is-active '*|'-q is-enabled '*) exit 1 ;;
  'show '*) exit 1 ;;
esac
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
  cat >"$case_dir/bin/df" <<'EOF'
#!/bin/bash
if [ "$TEST_MODE" = disk-full ]; then
  printf 'Filesystem 1024-blocks Used Available Capacity Mounted\nfixture 10 9 1 90%% /\n'
else
  exec /bin/df "$@"
fi
EOF
  cat >"$case_dir/bin/chmod" <<'EOF'
#!/bin/bash
if [ "$TEST_MODE" = worker-install-fail ] && [[ "${*: -1}" = *factory-worker.new ]]; then
  exit 1
fi
exec /bin/chmod "$@"
EOF
  cat >"$case_dir/cgroup-helper" <<'EOF'
#!/bin/bash
set -euo pipefail
name=$2
state="$TEST_CGROUP_DIR/$name.pids"
descendants() {
  local parent=$1 child
  printf '%s\n' "$parent"
  while read -r child; do
    [ -z "$child" ] || descendants "$child"
  done < <(/usr/bin/ps -eo pid=,ppid= | /usr/bin/awk -v p="$parent" '$2 == p {print $1}')
}
members() {
  [ -r "$state" ] && while read -r root; do descendants "$root"; done <"$state"
}
printf 'cgroup %s %s\n' "$1" "$name" >>"$TEST_GATES"
case "$1" in
  create) : >"$state" ;;
  attach) printf '%s\n' "$3" >>"$state" ;;
  empty)
    while read -r pid; do
      [ -r "/proc/$pid/stat" ] || continue
      process_stat=$(<"/proc/$pid/stat")
      process_rest=${process_stat##*) }
      read -r process_state _ <<<"$process_rest"
      [ "$process_state" = Z ] || exit 1
    done < <(members)
    ;;
  signal) while read -r pid; do kill -"$3" "$pid" 2>/dev/null || true; done < <(members) ;;
  remove) /bin/rm -f -- "$state" ;;
  *) exit 2 ;;
esac
EOF
  chmod 755 "$case_dir/cgroup-helper"
  printf 'completed\n' >"$case_dir/cgroup-bootstrap.done"
  chmod 600 "$case_dir/cgroup-bootstrap.done"
  helper_hash=$(/usr/bin/sha256sum "$case_dir/cgroup-helper" | /usr/bin/awk '{print $1}')
  helper_uid=$(/usr/bin/id -u)
  /usr/bin/sed \
    -e "s|^TRUSTED_GATE_CGROUP=.*$|TRUSTED_GATE_CGROUP=$case_dir/cgroup-helper|" \
    -e "s|^TRUSTED_GATE_CGROUP_SHA256=.*$|TRUSTED_GATE_CGROUP_SHA256=$helper_hash|" \
    -e "s|^TRUSTED_CGROUP_BOOTSTRAP_MARKER=.*$|TRUSTED_CGROUP_BOOTSTRAP_MARKER=$case_dir/cgroup-bootstrap.done|" \
    -e "s|^TRUSTED_CGROUP_OWNER_UID=.*$|TRUSTED_CGROUP_OWNER_UID=$helper_uid|" \
    "$RELEASE" >"$case_dir/release-under-test"
  chmod 755 "$case_dir/release-under-test"
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
  /bin/cp "$case_dir/bin/npx" "$case_dir/trusted/npx"
  /bin/cp "$case_dir/bin/npm" "$case_dir/trusted/npm"
  /bin/cp "$case_dir/bin/go" "$case_dir/trusted/go"
  cat >"$case_dir/bin/setsid" <<'EOF'
#!/bin/bash
printf 'path-setsid-invoked\n' >>"$TEST_SPOOF_EVENTS"
exit 0
EOF
  cat >"$case_dir/bin/node" <<'EOF'
#!/bin/bash
printf 'path-node-invoked\n' >>"$TEST_SPOOF_EVENTS"
exit 0
EOF
  cat >"$case_dir/trusted/setsid" <<'EOF'
#!/bin/bash
exec /usr/bin/setsid --fork --wait "$@"
EOF
  cat >"$case_dir/trusted/node" <<'EOF'
#!/bin/bash
script=$1
shift
exec /bin/bash "$script" "$@"
EOF
  chmod +x "$case_dir/trusted/"* "$case_dir/bin/setsid"

  # The production paths must be root-owned. The isolated fixture substitutes
  # only its local test tools and still keeps every gate executable absolute.
  fixture_uid=$(id -u)
  /bin/sed \
    -e "s|^TRUSTED_OWNER_UID=0$|TRUSTED_OWNER_UID=$fixture_uid|" \
    -e 's|\[ "$owner" = "$TRUSTED_OWNER_UID" \]|[[ "$owner" = 0 \|\| "$owner" = "$TRUSTED_OWNER_UID" ]]|' \
    -e "s|^TRUSTED_SETSID=.*$|TRUSTED_SETSID=$case_dir/trusted/setsid|" \
    -e "s|^TRUSTED_NODE=.*$|TRUSTED_NODE=$case_dir/trusted/node|" \
    -e "s|^TRUSTED_NPX=.*$|TRUSTED_NPX=$case_dir/trusted/npx|" \
    -e "s|^TRUSTED_NPM=.*$|TRUSTED_NPM=$case_dir/trusted/npm|" \
    -e "s|^TRUSTED_GO=.*$|TRUSTED_GO=$case_dir/trusted/go|" \
    "$RELEASE" >"$case_dir/fx-factory-release-under-test"
}

run_release() {
  case_dir=$1 mode=$2
  TEST_EVENTS="$case_dir/events" TEST_GATES="$case_dir/gates" TEST_MODE="$mode" \
    TEST_RELEASE_SOURCE="$SCRIPT_DIR/.." TEST_BROKER_EVENTS="$case_dir/broker-events" \
    TEST_SERVER_BIN="$case_dir/install/factory-server" \
    TEST_INTERRUPT_MARK="$case_dir/interrupted" PATH="$case_dir/bin:$PATH" \
    TEST_UI_STARTED="$case_dir/ui-started" TEST_GO_STARTED="$case_dir/go-started" \
    TEST_GO_RUNNING="$case_dir/go-running" TEST_UI_RUNNING="$case_dir/ui-running" \
    TEST_IDENTITY_MARK="$case_dir/identity-retried" \
    TEST_DEFERRED_COMMAND="$case_dir/deferred-pilot-restart" \
    TEST_GATE_CHILDREN="$case_dir/gate-children" TEST_SPOOF_EVENTS="$case_dir/spoof-events" \
    FACTORY_RELEASE_REPO="$case_dir/repo" \
    FACTORY_SERVER_BIN="$case_dir/install/factory-server" \
    FACTORY_WORKER_BIN="$case_dir/install/factory-worker" \
    FACTORY_FX_BIN="$case_dir/install/fx" \
    FACTORY_RELEASE_DRIVER="$case_dir/install/fx-factory-release" \
    FACTORY_BRAIN_LIVE="$case_dir/live" \
    FACTORY_DATABASE="$case_dir/database/factory.sqlite3" \
    FACTORY_RELEASE_DIR="$case_dir/releases" \
    FACTORY_RELEASE_INFO="$case_dir/current.json" \
    FACTORY_RELEASE_LOCK="$case_dir/release.lock" \
    FACTORY_RELEASE_AS='' FACTORY_RELEASE_OWNER='' FACTORY_CONTROL_OWNER='' FACTORY_BRAIN_OWNER='' \
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
    /bin/bash "$case_dir/fx-factory-release-under-test" main >"$case_dir/output" 2>&1
}

run_driver() {
  case_dir=$1; shift
  TEST_EVENTS="$case_dir/events" TEST_GATES="$case_dir/gates" TEST_MODE=control \
    PATH="$case_dir/bin:$PATH" FACTORY_SERVER_BIN="$case_dir/install/factory-server" \
    FACTORY_WORKER_BIN="$case_dir/install/factory-worker" FACTORY_FX_BIN="$case_dir/install/fx" \
    FACTORY_RELEASE_DRIVER="$case_dir/install/fx-factory-release" FACTORY_BRAIN_LIVE="$case_dir/live" \
    FACTORY_DATABASE="$case_dir/database/factory.sqlite3" FACTORY_RELEASE_DIR="$case_dir/releases" \
    FACTORY_RELEASE_INFO="$case_dir/current.json" FACTORY_RELEASE_LOCK="$case_dir/release.lock" \
    FACTORY_RELEASE_AS='' FACTORY_RELEASE_OWNER='' FACTORY_CONTROL_OWNER='' FACTORY_BRAIN_OWNER='' FACTORY_RELEASE_BROKER_OWNER='' \
    FACTORY_RELEASE_BROKER_BIN="$case_dir/install/factory-release-broker" \
    FACTORY_RELEASE_BROKER_UNIT="$case_dir/install/factory-release-broker.service" \
    FACTORY_RELEASE_BROKER_SERVER_DROPIN="$case_dir/install/50-project-release-broker.conf" \
    FACTORY_WORKER_SERVICES="factory-worker.service factory-worker-2.service" FACTORY_API_URL=http://test \
    /bin/bash "$case_dir/release-under-test" "$@"
}

start_release() {
  case_dir=$1 mode=$2
  TEST_EVENTS="$case_dir/events" TEST_GATES="$case_dir/gates" TEST_MODE="$mode" \
    TEST_RELEASE_SOURCE="$SCRIPT_DIR/.." TEST_BROKER_EVENTS="$case_dir/broker-events" \
    TEST_SERVER_BIN="$case_dir/install/factory-server" \
    TEST_INTERRUPT_MARK="$case_dir/interrupted" PATH="$case_dir/bin:$PATH" \
    TEST_UI_STARTED="$case_dir/ui-started" TEST_GO_STARTED="$case_dir/go-started" \
    TEST_GO_RUNNING="$case_dir/go-running" TEST_UI_RUNNING="$case_dir/ui-running" \
    TEST_IDENTITY_MARK="$case_dir/identity-retried" \
    TEST_DEFERRED_COMMAND="$case_dir/deferred-pilot-restart" \
    TEST_GATE_CHILDREN="$case_dir/gate-children" TEST_SPOOF_EVENTS="$case_dir/spoof-events" \
    FACTORY_RELEASE_REPO="$case_dir/repo" \
    FACTORY_SERVER_BIN="$case_dir/install/factory-server" \
    FACTORY_WORKER_BIN="$case_dir/install/factory-worker" \
    FACTORY_FX_BIN="$case_dir/install/fx" \
    FACTORY_RELEASE_DRIVER="$case_dir/install/fx-factory-release" \
    FACTORY_BRAIN_LIVE="$case_dir/live" \
    FACTORY_DATABASE="$case_dir/database/factory.sqlite3" \
    FACTORY_RELEASE_DIR="$case_dir/releases" \
    FACTORY_RELEASE_INFO="$case_dir/current.json" \
    FACTORY_RELEASE_LOCK="$case_dir/release.lock" \
    FACTORY_RELEASE_AS='' FACTORY_RELEASE_OWNER='' FACTORY_CONTROL_OWNER='' FACTORY_BRAIN_OWNER='' \
    FACTORY_RELEASE_BROKER_BIN="$case_dir/install/factory-release-broker" \
    FACTORY_RELEASE_BROKER_UNIT="$case_dir/install/factory-release-broker.service" \
    FACTORY_RELEASE_BROKER_SERVER_DROPIN="$case_dir/install/50-project-release-broker.conf" \
    FACTORY_RELEASE_BROKER_OWNER='' \
    FACTORY_RELEASE_BROKER_SYSTEMCTL="$case_dir/bin/broker-systemctl" \
    FACTORY_RELEASE_BROKER_GETENT="$case_dir/bin/getent" \
    FACTORY_RELEASE_BROKER_GROUPADD="$case_dir/bin/groupadd" \
    FACTORY_WORKER_CONFIG="$case_dir/worker.toml" \
    FACTORY_API_URL=http://test FACTORY_REGISTER_ATTEMPTS=2 FACTORY_REGISTER_DELAY=0 \
    /bin/bash "$case_dir/fx-factory-release-under-test" main >"$case_dir/output" 2>&1 &
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
assert_before "$success/gates" 'cgroup attach factory-release-gate-' 'npx tsc -p tsconfig.app.json --noEmit'
grep -F 'cgroup remove factory-release-gate-' "$success/gates" >/dev/null \
  || fail "successful Gate did not remove its cgroup"
assert_before "$success/gates" 'npx vite build' 'go build -ldflags '
grep -F 'полный вывод: UI-проверки' "$success/output" >/dev/null \
  || fail "UI output was not kept separate"
grep -F 'полный вывод: Go-проверки и сценарий выката' "$success/output" >/dev/null \
  || fail "Go output was not kept separate"
assert_file "$success/install/factory-server" '#!/bin/bash'
assert_file "$success/install/factory-worker" '#!/bin/bash'
assert_file "$success/install/factory-release-broker" '#!/bin/bash'
current_generation=$(readlink -f "$success/releases/current")
previous_generation=$(readlink -f "$success/releases/previous")
[ -f "$current_generation/manifest.json" ] && [ -f "$current_generation/manifest.sha256" ] \
  || fail "committed generation has no immutable manifest"
[ -f "$current_generation/database.sqlite3" ] && [ -d "$previous_generation" ] \
  || fail "release did not retain snapshot and previous complete generation"
python3 - "$current_generation" <<'PY' || fail "manifest does not cover the complete release"
import hashlib,json,sys
r=sys.argv[1]; raw=open(r+'/manifest.json','rb').read(); d=json.loads(raw)
assert hashlib.sha256(raw).hexdigest()==open(r+'/manifest.sha256').read().strip()
names={x['source'] for x in d['artifacts']}
assert {'payload/factory-server','payload/factory-worker','payload/factory-release-broker','payload/fx','payload/fx-factory-release','payload/pilot.py','payload/context.md','payload/intake-app.py','payload/intake-plan.py','release-info.json'} <= names
assert d['database']['sha256']==hashlib.sha256(open(r+'/database.sqlite3','rb').read()).hexdigest()
PY
assert_before "$success/events" 'stop factory-worker.service' 'stop factory-server.service'
assert_before "$success/events" 'backup-snapshot' 'stop factory-worker.service'
assert_file "$success/gates" 'checkout-umask=0077'
grep -F 'snapshot' "$success/output" >/dev/null || fail "release did not report snapshot creation"
assert_before "$success/events" 'stop factory-server.service' 'start factory-server.service'
assert_before "$success/events" 'start factory-server.service' 'start factory-worker.service'
grep -F 'выкачено:' "$success/output" >/dev/null || fail "release did not report success"
grep -F 'Проверочный релиз' "$success/output" >/dev/null \
  || fail "release did not explain the deployed change"
! grep -F 'Merge pull request' "$success/output" >/dev/null \
  || fail "release exposed GitHub merge plumbing instead of a human title"
! grep -F '#123' "$success/output" >/dev/null \
  || fail "release exposed a pull request number in owner-facing output"

# Живая база бывает новее установленного server: неудачный кандидат успел
# поднять схему, а откат вернул только бинарь. Старый server такой снимок
# честно не делает — выпуск обязан снять базу свежесобранным кандидатом,
# иначе обновления заперты навсегда.
schema_newer="$temporary/snapshot-schema-newer"
make_fixture "$schema_newer" snapshot-schema-newer
run_release "$schema_newer" snapshot-schema-newer \
  || { cat "$schema_newer/output" >&2; fail "schema-newer release failed"; }
grep -F 'снимок делает свежесобранный кандидат' "$schema_newer/output" >/dev/null \
  || fail "schema-newer fallback was not reported"
grep -Fx 'candidate-backup-snapshot' "$schema_newer/events" >/dev/null \
  || fail "candidate did not create the snapshot"
grep -F 'выкачено:' "$schema_newer/output" >/dev/null \
  || fail "schema-newer release did not complete"
assert_no_fixture_processes "$schema_newer"

# A caller-controlled PATH can offer a plausible but fake setsid. The gate
# must still run from its verified absolute path and complete normally.
path_shadow="$temporary/path-shadow-chain"
make_fixture "$path_shadow" parallel-success
run_release "$path_shadow" parallel-success \
  || { cat "$path_shadow/output" >&2; fail "PATH-shadowed gate did not complete"; }
! grep -Fx 'path-setsid-invoked' "$path_shadow/spoof-events" >/dev/null 2>&1 \
  || fail "PATH shadow entered the trusted gate chain"
! grep -Fx 'path-node-invoked' "$path_shadow/spoof-events" >/dev/null 2>&1 \
  || fail "PATH node entered the trusted gate chain"
assert_file "$path_shadow/install/factory-server" '#!/bin/bash'
assert_file "$path_shadow/install/factory-worker" '#!/bin/bash'

identity_retry="$temporary/identity-transient"
make_fixture "$identity_retry" identity-transient
run_release "$identity_retry" identity-transient \
  || { cat "$identity_retry/output" >&2; fail "transient identity lock was not retried"; }
[ -e "$identity_retry/identity-retried" ] || fail "identity retry scenario did not exercise the transient failure"

for mode in server-fail worker-fail stale-healthy-worker worker-install-fail interrupt-between-install; do
  failed="$temporary/$mode"
  make_fixture "$failed" "$mode"
  set +e
  run_release "$failed" "$mode"
  status=$?
  set -e
  [ "$status" -ne 0 ] || fail "$mode unexpectedly succeeded"
  assert_file "$failed/install/factory-server" old-server
  assert_file "$failed/install/factory-worker" old-worker
  assert_file "$failed/install/fx" 'exit 0'
  assert_file "$failed/live/pilot/pilot.py" 'old pilot'
  if [ "$mode" = worker-install-fail ]; then
    assert_file "$failed/releases/transaction" 'phase=old-stopped'
  else
    [ ! -e "$failed/releases/transaction" ] || fail "$mode left a false successful journal"
  fi
  assert_no_fixture_processes "$failed"
done

for crash_phase in prepared old-stopped pair-installed services-started; do
  crashed="$temporary/crash-$crash_phase"
  make_fixture "$crashed" parallel-success
  set +e
  FACTORY_RELEASE_CRASH_AFTER_PHASE="$crash_phase" run_release "$crashed" parallel-success
  status=$?
  set -e
  [ "$status" -ne 0 ] || fail "crash hook $crash_phase unexpectedly committed"
  assert_file "$crashed/releases/transaction" "phase=$crash_phase"
  : >"$crashed/events"
  run_release "$crashed" parallel-success \
    || { cat "$crashed/output" >&2; fail "restart did not recover phase $crash_phase"; }
  [ ! -e "$crashed/releases/transaction" ] || fail "recovery left journal for $crash_phase"
  current_after_recovery=$(readlink -f "$crashed/releases/current")
  [ -f "$current_after_recovery/manifest.json" ] || fail "recovery did not reach a committed generation"
done

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

for signal in HUP TERM; do
  for attempt in 1 2 3 4 5; do
    signaled="$temporary/signal-$signal-$attempt"
    make_fixture "$signaled" signal-gates
    start_release "$signaled" signal-gates
    wait_for_file "$signaled/ui-running"
    wait_for_file "$signaled/go-running"
    kill -"$signal" "$release_pid"
    set +e
    wait "$release_pid"
    status=$?
    set -e
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

missing="$temporary/missing-artifact"
make_fixture "$missing" missing-artifact
rm "$missing/install/factory-release-broker"
set +e
run_release "$missing" missing-artifact
status=$?
set -e
[ "$status" -eq 4 ] || fail "missing rollback artifact was not rejected"
[ ! -s "$missing/events" ] || fail "missing artifact caused a service mutation"
grep -F 'нет полного rollback artifact' "$missing/output" >/dev/null \
  || fail "missing artifact refusal was not human-readable"

wrong_mode="$temporary/wrong-mode"
make_fixture "$wrong_mode" wrong-mode
chmod 700 "$wrong_mode/install/factory-worker"
set +e
run_release "$wrong_mode" wrong-mode
status=$?
set -e
[ "$status" -eq 4 ] || fail "wrong artifact mode was not rejected"
[ ! -s "$wrong_mode/events" ] || fail "wrong mode caused a service mutation"

disk_full="$temporary/disk-full"
make_fixture "$disk_full" disk-full
set +e
run_release "$disk_full" disk-full
status=$?
set -e
[ "$status" -eq 4 ] || fail "insufficient disk was not rejected"
[ ! -s "$disk_full/events" ] || fail "insufficient disk caused a service mutation"
grep -F 'недостаточно свободного места или inode' "$disk_full/output" >/dev/null \
  || fail "disk refusal was not human-readable"

rollback_case="$temporary/full-rollback"
make_fixture "$rollback_case" parallel-success
run_release "$rollback_case" parallel-success || fail "rollback fixture release failed"
candidate=$(readlink -f "$rollback_case/releases/current")
snapshot="$candidate/database.sqlite3"
manifest=$(<"$candidate/manifest.sha256")
before_db=$(sha256sum "$rollback_case/database/factory.sqlite3" | awk '{print $1}')
python3 - "$rollback_case/database/factory.sqlite3" <<'PY'
import sqlite3,sys
d=sqlite3.connect(sys.argv[1]); d.execute('insert into schema_migrations values(2,0)'); d.commit(); d.close()
PY
migrated_db=$(sha256sum "$rollback_case/database/factory.sqlite3" | awk '{print $1}')
set +e
run_driver "$rollback_case" --rollback >"$rollback_case/rollback-output" 2>&1
status=$?
set -e
[ "$status" -eq 9 ] || fail "incompatible ledger rollback did not require explicit DB restore"
[ "$(sha256sum "$rollback_case/database/factory.sqlite3" | awk '{print $1}')" = "$migrated_db" ] \
  || fail "ordinary rollback changed the database"
assert_file "$rollback_case/install/factory-server" old-server
assert_file "$rollback_case/install/factory-worker" old-worker
assert_file "$rollback_case/install/fx" 'exit 0'
assert_file "$rollback_case/live/pilot/pilot.py" 'old pilot'
assert_file "$rollback_case/releases/transaction" 'phase=db_restore_required'
run_driver "$rollback_case" --restore-db "$snapshot" "$manifest" RESTORE-FACTORY-DATABASE \
  >"$rollback_case/restore-output" 2>&1 || { cat "$rollback_case/restore-output" >&2; fail "explicit DB restore failed"; }
[ "$(python3 - "$rollback_case/database/factory.sqlite3" <<'PY'
import sqlite3,sys
print(sqlite3.connect(sys.argv[1]).execute('select max(version) from schema_migrations').fetchone()[0])
PY
)" = 1 ] || fail "restored DB has the wrong ledger"
compgen -G "$rollback_case/database/factory.sqlite3.failed.*" >/dev/null \
  || fail "explicit restore did not preserve the failed DB"
[ ! -e "$rollback_case/releases/transaction" ] || fail "successful restore left a journal"
[ "$before_db" != "$migrated_db" ] || fail "DB rollback fixture did not actually migrate the live ledger"

tampered="$temporary/tampered-manifest"
make_fixture "$tampered" parallel-success
run_release "$tampered" parallel-success || fail "tamper fixture release failed"
printf 'tampered\n' >>"$(readlink -f "$tampered/releases/previous")/payload/factory-worker"
set +e
run_driver "$tampered" --rollback >"$tampered/tamper-output" 2>&1
status=$?
set -e
[ "$status" -ne 0 ] || fail "rollback accepted a tampered immutable generation"
grep -F 'manifest поколения не прошёл проверку' "$tampered/tamper-output" >/dev/null \
  || fail "tampered manifest refusal was not explicit"

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
