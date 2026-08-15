#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
RELEASE="$SCRIPT_DIR/fx-factory-release"
# Полигон сцен собирается из полного дерева репозитория (git archive HEAD).
# Рядом с доверенной root-owned копией gate такого дерева нет — тогда берём
# каталог кандидата: драйвер запускает gate с cwd = $work/src.
FIXTURE_TREE="$SCRIPT_DIR/.."
/usr/bin/git -C "$FIXTURE_TREE" rev-parse --git-dir >/dev/null 2>&1 || FIXTURE_TREE=$PWD
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT

# This is invoked only through a separately extracted Git-object copy below.
# It proves that the copied file is this real Gate and that every relative
# resource its fixture needs travelled with it.
if [ "${TEST_MODE:-}" = trusted-gate-real-race ]; then
  for dependency in fx-factory-release install-project-release-broker.sh fx \
    systemd/factory-release-broker.service ../pilot/pilot.py ../pilot/context.md \
    ../intake/app.py ../intake/plan.py; do
    [ -r "$SCRIPT_DIR/$dependency" ] || { echo "missing trusted dependency: $dependency" >&2; exit 41; }
  done
  printf 'real-extracted-gate-after-handshake\n' >>"$TEST_HANDSHAKE_EVENTS"
  exit 0
fi

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

start_gate_directory_attack() {
  local case_dir=$1
  (
    for ((i = 0; i < 500; i++)); do
      for target in "$case_dir/releases"/trusted-gate-*; do
        [ -d "$target" ] || continue
        /bin/rm -rf -- "$target"
        mkdir -p "$target/ops"
        printf '#!/bin/bash\nexit 0\n' >"$target/ops/test-fx-factory-release.sh"
      done
      /bin/sleep 0.005
    done
  ) &
  trusted_gate_attack_pid=$!
  : >"$case_dir/trusted-gate-attack-started"
}

assert_preflight_refusal() {
  local case_dir=$1
  [ ! -s "$case_dir/events" ] || fail "preflight refusal touched services in $case_dir"
  [ ! -s "$case_dir/gates" ] || fail "preflight refusal started build gates in $case_dir"
  [ ! -e "$case_dir/releases/transaction" ] || fail "preflight refusal wrote a journal in $case_dir"
  ! compgen -G "$case_dir/releases/build-*" >/dev/null \
    || fail "preflight refusal created a build directory in $case_dir"
  ! compgen -G "$case_dir/releases/.generation-*" >/dev/null \
    || fail "preflight refusal created a candidate generation in $case_dir"
  ! compgen -G "$case_dir/releases/.bootstrap-*" >/dev/null \
    || fail "preflight refusal created a bootstrap generation in $case_dir"
  grep -F 'живую metadata не исправляли автоматически' "$case_dir/output" >/dev/null \
    || fail "preflight refusal did not explain metadata was left unchanged"
  grep -F 'проверенная восстановимая исходная точка' "$case_dir/output" >/dev/null \
    || fail "preflight refusal did not explain the required source state"
}

verify_immutable_generation() {
  python3 - "$1" <<'PY'
import hashlib,json,os,stat,sys
root=sys.argv[1]
raw=open(os.path.join(root,"manifest.json"),"rb").read()
data=json.loads(raw)
assert hashlib.sha256(raw).hexdigest()==open(os.path.join(root,"manifest.sha256")).read().strip()
assert data.get("format")==1 and data.get("candidate_sha")
for item in data.get("artifacts",[]):
    path=os.path.join(root,item["source"])
    info=os.lstat(path)
    assert stat.S_ISREG(info.st_mode)
    body=open(path,"rb").read()
    assert len(body)==item["size"] and hashlib.sha256(body).hexdigest()==item["sha256"]
    assert stat.S_IMODE(info.st_mode)==item["mode"]
database=data.get("database",{})
if database.get("snapshot"):
    snapshot=os.path.join(root,database["snapshot"])
    marker=snapshot+".v2-control-plane"
    assert stat.S_IMODE(os.lstat(snapshot).st_mode)==0o600
    assert stat.S_IMODE(os.lstat(marker).st_mode)==0o600
    assert hashlib.sha256(open(snapshot,"rb").read()).hexdigest()==database["sha256"]
    assert hashlib.sha256(open(marker,"rb").read()).hexdigest()==database["marker_sha256"]
PY
}

make_fixture() {
  case_dir=$1 mode=$2
  mkdir -p "$case_dir/bin" "$case_dir/install/factory-pilot.service.d" "$case_dir/releases" "$case_dir/repo/web" \
    "$case_dir/live/pilot" "$case_dir/live/intake" "$case_dir/database"
  cat >"$case_dir/install/factory-server" <<'EOF'
#!/bin/bash
# old-server
case " $* " in
  *' version '*) echo 'factory-server test aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' ;;
  *' -backup '*)
    [ "$TEST_MODE" = installed-server-no-backup ] && exit 42
    echo backup-snapshot >>"$TEST_EVENTS"
    while [ "$#" -gt 0 ]; do case "$1" in -database) db=$2; shift 2;; -backup) out=$2; shift 2;; *) shift;; esac; done
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
[ "${1:-}" = version ] && echo 'factory-worker test aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
EOF
  printf '#!/bin/bash\nexit 0\n' >"$case_dir/install/factory-release-broker"
  /bin/cp "$SCRIPT_DIR/systemd/factory-release-broker.service" "$case_dir/install/factory-release-broker.service"
  printf '[Service]\nSupplementaryGroups=factory-release\n' >"$case_dir/install/factory-pilot.service.d/50-project-release-broker.conf"
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
  /usr/bin/git -C "$FIXTURE_TREE" archive --format=tar HEAD | /bin/tar -x -C "$case_dir/repo"
  /bin/cp "$RELEASE" "$case_dir/repo/ops/fx-factory-release"
  /bin/cp "$SCRIPT_DIR/test-fx-factory-release.sh" "$case_dir/repo/ops/test-fx-factory-release.sh"
  if [ "$mode" = trusted-gate-real-race ]; then
    /bin/cp "$SCRIPT_DIR/test-fx-factory-release.sh" "$case_dir/repo/ops/test-fx-factory-release.sh"
  else
    cat >"$case_dir/repo/ops/test-fx-factory-release.sh" <<'GATE'
#!/bin/bash
echo "bash ops/test-fx-factory-release.sh" >>"$TEST_GATES"
case "$TEST_MODE" in
  release-test-fail|forked-gate-fail|gate-result-spoof|path-shadow-chain|handshake-file-spoof|trusted-gate-tamper) exit 1 ;;
esac
exit 0
GATE
    chmod +x "$case_dir/repo/ops/test-fx-factory-release.sh"
  fi
  /usr/bin/git -C "$case_dir/repo" init -q
  /usr/bin/git -C "$case_dir/repo" config user.name fixture
  /usr/bin/git -C "$case_dir/repo" config user.email fixture@example.invalid
  /usr/bin/git -C "$case_dir/repo" add -f web ops pilot intake
  /usr/bin/git -C "$case_dir/repo" commit -qm 'Проверочный релиз'
  /usr/bin/git -C "$case_dir/repo" branch -M main
  printf '{"name":"old","sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","release_id":"installed-old-release"}\n' >"$case_dir/current.json"
  # The real release gate runs this test under umask 077.  Set the fixture
  # modes explicitly so the rollback preflight verifies production-like
  # artifacts instead of inheriting the caller's umask.
  chmod 755 "$case_dir/install/factory-server" "$case_dir/install/factory-worker" \
    "$case_dir/install/factory-release-broker" "$case_dir/install/fx" "$case_dir/install/fx-factory-release"
  chmod 644 "$case_dir/install/factory-release-broker.service" \
    "$case_dir/install/factory-pilot.service.d/50-project-release-broker.conf" \
    "$case_dir/live/pilot/pilot.py" "$case_dir/live/pilot/context.md" \
    "$case_dir/live/intake/app.py" "$case_dir/live/intake/plan.py"
  mkdir -p "$case_dir/trusted"
  chmod 600 "$case_dir/current.json"
  : >"$case_dir/events"
  : >"$case_dir/worker.toml"
  : >"$case_dir/gate-children"
  : >"$case_dir/handshake-events"
  : >"$case_dir/spoof-events"

cat >"$case_dir/bin/git" <<'EOF'
#!/bin/bash
printf 'untrusted-git-invoked\n' >>"$TEST_SPOOF_EVENTS"
case "$*" in
  *'clone --quiet'*)
    destination=${@: -1}
    mkdir -p "$destination/web" "$destination/ops/systemd"
    /bin/cp "$TEST_RELEASE_SOURCE/ops/install-project-release-broker.sh" \
      "$destination/ops/install-project-release-broker.sh"
    /bin/cp "$TEST_RELEASE_SOURCE/ops/systemd/factory-release-broker.service" \
      "$destination/ops/systemd/factory-release-broker.service"
    mkdir -p "$destination/pilot" "$destination/intake"
    /bin/cp "$TEST_RELEASE_SOURCE/ops/fx" "$destination/ops/fx"
    /bin/cp "$TEST_RELEASE_SOURCE/ops/fx-factory-release" "$destination/ops/fx-factory-release"
    /bin/cp "$TEST_RELEASE_SOURCE/pilot/pilot.py" "$destination/pilot/pilot.py"
    /bin/cp "$TEST_RELEASE_SOURCE/pilot/test_pilot.py" "$destination/pilot/test_pilot.py"
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
    if [ "$TEST_MODE" = trusted-gate-real-race ]; then
      /bin/cp "$TEST_REAL_GATE" "$destination/ops/test-fx-factory-release.sh"
    else
    cat >"$destination/ops/test-fx-factory-release.sh" <<'RELEASE_GATE'
#!/bin/bash
echo "bash ops/test-fx-factory-release.sh" >>"$TEST_GATES"
if [ "$TEST_MODE" = trusted-gate-integration ]; then
  SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
  [ -x "$SCRIPT_DIR/fx-factory-release" ] || exit 31
  [ -f "$SCRIPT_DIR/systemd/factory-release-broker.service" ] || exit 32
  printf 'extracted-gate-after-handshake\n' >>"$TEST_HANDSHAKE_EVENTS"
fi
if [ "$TEST_MODE" = gate-result-spoof ]; then
  for ((i = 0; i < 400; i++)); do
    grep -Fx 'replayed-success' "$TEST_SPOOF_EVENTS" >/dev/null 2>&1 && break
    /bin/sleep 0.005
  done
  grep -Fx 'replayed-success' "$TEST_SPOOF_EVENTS" >/dev/null || exit 20
  exit 1
fi
case "$TEST_MODE" in
  release-test-fail|forked-gate-fail|gate-result-spoof|path-shadow-chain|handshake-file-spoof|trusted-gate-tamper) exit 1 ;;
esac
exit 0
RELEASE_GATE
    fi
    chmod +x "$destination/ops/install-brain.sh"
    chmod +x "$destination/ops/install-project-release-broker.sh"
    chmod +x "$destination/ops/install-server-browser.sh"
    /usr/bin/git -C "$destination" init -q
    /usr/bin/git -C "$destination" config user.name fixture
    /usr/bin/git -C "$destination" config user.email fixture@example.invalid
    /usr/bin/git -C "$destination" add .
    /usr/bin/git -C "$destination" commit -qm fixture
    ;;
  *'checkout --quiet'*)
    if [ "$TEST_MODE" = trusted-gate-tamper ]; then
      printf '#!/bin/bash\nexit 0\n' >"$2/ops/test-fx-factory-release.sh"
    fi
    ;;
  *'rev-parse HEAD'*)
    if [ "$TEST_MODE" = trusted-gate-real-race ]; then
      (
        for ((i = 0; i < 500; i++)); do
          for target in "$TEST_RELEASE_DIR"/trusted-gate-*; do
            [ -d "$target" ] || continue
            /bin/rm -rf -- "$target"
            mkdir -p "$target/ops"
            printf '#!/bin/bash\nexit 0\n' >"$target/ops/test-fx-factory-release.sh"
          done
          /bin/sleep 0.005
        done
      ) &
      : >"$TEST_TRUSTED_GATE_ATTACK_STARTED"
    fi
    echo 1234567890abcdef1234567890abcdef12345678 ;;
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
  local name=$1 state='' sid_field pgid_field nonce_field ready_field extra sid pgid actual_sid actual_pgid
  state=$(find "$TEST_RELEASE_DIR" -name "$name" -type f -print -quit)
  [ -n "$state" ] || exit 18
  IFS=' ' read -r sid_field pgid_field nonce_field ready_field extra <"$state" || exit 18
  case "$sid_field:$pgid_field:$nonce_field:$ready_field:$extra" in
    sid=*:pgid=*:nonce=*:ready=1:) ;;
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
  local name=$1 state='' sid_field pgid_field nonce_field ready_field extra sid pgid actual_sid actual_pgid
  state=$(find "$TEST_RELEASE_DIR" -name "$name" -type f -print -quit)
  [ -n "$state" ] || exit 18
  IFS=' ' read -r sid_field pgid_field nonce_field ready_field extra <"$state" || exit 18
  case "$sid_field:$pgid_field:$nonce_field:$ready_field:$extra" in
    sid=*:pgid=*:nonce=*:ready=1:) ;;
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
    go-test-fail|forged-gate-result) exit 1 ;;
  esac
  exit 0
fi
commit=
for argument in "$@"; do
  case "$argument" in *Commit=*) commit=${argument##*Commit=} ;; esac
done
output=
while [ "$#" -gt 0 ]; do
  if [ "$1" = -o ]; then output=$2; shift 2; else shift; fi
done
case "$output" in
  *factory-server)
    cat >"$output" <<'SERVER'
#!/bin/bash
case " $* " in
  *' version '*) echo 'factory-server test 1234567890abcdef1234567890abcdef12345678' ;;
  *' -backup '*)
    echo candidate-backup >>"$TEST_EVENTS"
    while [ "$#" -gt 0 ]; do case "$1" in -database) db=$2; shift 2;; -backup) out=$2; shift 2;; *) shift;; esac; done
    python3 - "$db" "$out" <<'PY'
import sqlite3,sys
s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close(); s.close()
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
[ "${1:-}" = version ] && { echo 'factory-worker test 1234567890abcdef1234567890abcdef12345678'; exit 0; }
[ "${1:-}" = identity ] && {
  [ "$(grep -E '^(start|stop) factory-worker.service$' "$TEST_EVENTS" | tail -1)" \
    = 'stop factory-worker.service' ] || exit 9
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
  *factory-release-broker)
    printf '#!/bin/bash\n# candidate-broker\nexit 0\n' >"$output"
    ;;
  *) printf '#!/bin/bash\nexit 0\n' >"$output" ;;
esac
[ -z "$commit" ] || /bin/sed -i "s/1234567890abcdef/$commit/g" "$output"
chmod +x "$output"
EOF
  cat >"$case_dir/trusted/python3" <<'EOF'
#!/bin/bash
echo "python3 $*" >>"$TEST_GATES"
[ "$TEST_MODE" != pilot-test-fail ]
EOF
  cat >"$case_dir/bin/bash" <<'EOF'
#!/bin/bash
if [[ "${1:-}" = */ops/test-fx-factory-release.sh ]] \
  || [ "${1:-}" = ops/test-fx-factory-release.sh ]; then
  echo 'path-bash-gate-invoked' >>"$TEST_SPOOF_EVENTS"
  echo "bash $1" >>"$TEST_GATES"
  if [ "$TEST_MODE" = gate-result-spoof ]; then
    for ((i = 0; i < 400; i++)); do
      grep -Fx 'replayed-success' "$TEST_SPOOF_EVENTS" >/dev/null 2>&1 && break
      /bin/sleep 0.005
    done
    grep -Fx 'replayed-success' "$TEST_SPOOF_EVENTS" >/dev/null || exit 20
    exit 1
  fi
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
  cat >"$case_dir/trusted/setsid" <<'EOF'
#!/bin/bash
saw_fork=0
saw_wait=0
while [ "${1:-}" = --fork ] || [ "${1:-}" = --wait ]; do
  [ "$1" != --fork ] || saw_fork=1
  [ "$1" != --wait ] || saw_wait=1
  shift
done
if [ "$TEST_MODE" = forged-gate-result ]; then
  for argument in "$@"; do
    case "$argument" in
      *.session)
        printf 'state=finished status=0\n' >"$argument.result"
        printf 'forged-gate-result\n' >>"$TEST_SPOOF_EVENTS"
        ;;
    esac
  done
fi
case "$TEST_MODE" in
  forked-gates-success|forked-gate-fail|forged-gate-result|signal-forked-gates)
    printf 'setsid-forked\n' >>"$TEST_HANDSHAKE_EVENTS"
    [ "$saw_fork:$saw_wait" = 1:1 ] \
      || { printf 'setsid-missing-wait\n' >>"$TEST_HANDSHAKE_EVENTS"; exit 125; }
    printf 'setsid-waits\n' >>"$TEST_HANDSHAKE_EVENTS"
    exec /usr/bin/setsid --fork --wait "$@"
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
  missing-session) exit 0 ;;
  *) exec /usr/bin/setsid --fork --wait "$@" ;;
esac
EOF
  cat >"$case_dir/bin/setsid" <<'EOF'
#!/bin/bash
printf 'path-setsid-invoked\n' >>"$TEST_SPOOF_EVENTS"
build_dir=$(find "$TEST_RELEASE_DIR" -maxdepth 1 -type d -name 'build-*' -print -quit)
if [ -n "$build_dir" ]; then
  printf 'sid=999999 pgid=999999 ready=1\n' >"$build_dir/ui-checks.session"
  printf 'sid=999999 pgid=999999 ready=1\n' >"$build_dir/go-checks.session"
fi
exit 0
EOF
  cat >"$case_dir/bin/node" <<'EOF'
#!/bin/bash
printf 'path-node-invoked\n' >>"$TEST_SPOOF_EVENTS"
exit 0
EOF
  cat >"$case_dir/trusted/node" <<'EOF'
#!/bin/bash
script=$1
shift
exec /bin/bash "$script" "$@"
EOF
  cat >"$case_dir/trusted/sudo" <<'EOF'
#!/bin/bash
[ "${1:-}" != -H ] || shift
if [ "${1:-}" = -u ]; then shift 2; fi
[ "${1:-}" != -- ] || shift
exec "$@"
EOF
  cat >"$case_dir/bin/sudo" <<'EOF'
#!/bin/bash
printf 'path-sudo-invoked\n' >>"$TEST_SPOOF_EVENTS"
exit 0
EOF
  cat >"$case_dir/bin/test-fx-factory-release.sh" <<'EOF'
#!/bin/bash
printf 'path-gate-invoked\n' >>"$TEST_SPOOF_EVENTS"
exit 0
EOF
  cat >"$case_dir/bin/as-fork" <<'EOF'
#!/bin/bash
for argument in "$@"; do
  [[ "$argument" != *.session.result ]] || printf 'result-path-leaked\n' >>"$TEST_SPOOF_EVENTS"
done
if [ "$TEST_MODE" = gate-result-spoof ] && mkdir "$TEST_SPOOF_LOCK" 2>/dev/null; then
  (
    result=
    for ((i = 0; i < 400; i++)); do
      build_dir=$(find "$TEST_RELEASE_DIR" -maxdepth 1 -type d -name 'build-*' -print -quit)
      if [ -n "$build_dir" ]; then
        result="$build_dir/go-checks.session.result"
        break
      fi
      /bin/sleep 0.005
    done
    [ -n "$result" ] || exit 19

    # Reproduce every unsafe filesystem state before writing the exact valid
    # success that fooled the old protocol. All writes are by the untrusted AS.
    printf 'state=finished status=0\n' >"$result"
    printf 'stale\n' >>"$TEST_SPOOF_EVENTS"
    for ((i = 0; i < 400; i++)); do
      [ -e "${result%.result}" ] && break
      /bin/sleep 0.005
    done
    printf 'corrupt\n' >"$result"
    printf 'corrupt\n' >>"$TEST_SPOOF_EVENTS"
    temporary_result="${result}.attacker.$$"
    printf 'state=finished status=0\n' >"$temporary_result"
    mv -f -- "$temporary_result" "$result"
    printf 'valid-success\n' >>"$TEST_SPOOF_EVENTS"
    temporary_result="${result}.replay.$$"
    printf 'state=finished status=0\n' >"$temporary_result"
    mv -f -- "$temporary_result" "$result"
    printf 'replayed-success\n' >>"$TEST_SPOOF_EVENTS"
  ) </dev/null >/dev/null 2>&1 &
fi
if [ "$TEST_MODE" = handshake-file-spoof ] && mkdir "$TEST_SPOOF_LOCK" 2>/dev/null; then
  (
    seen_build=0
    for ((i = 0; i < 100; i++)); do
      build_dir=$(find "$TEST_RELEASE_DIR" -maxdepth 1 -type d -name 'build-*' -print -quit)
      if [ -n "$build_dir" ]; then
        seen_build=1
        printf 'sid=999999 pgid=999999 nonce=forged ready=1\n' >"$build_dir/ui-checks.session"
        printf 'sid=999999 pgid=999999 nonce=forged ready=1\n' >"$build_dir/go-checks.session"
        printf 'forged-handshake\n' >>"$TEST_SPOOF_EVENTS"
      elif [ "$seen_build" = 1 ]; then
        break
      fi
      /bin/sleep 0.002
    done
  ) </dev/null >/dev/null 2>&1 &
fi
exec "$@"
EOF
  cat >"$case_dir/bin/systemctl" <<'EOF'
#!/bin/bash
if [ "$TEST_MODE" = deleted-inode ]; then
  case "$*" in
    '-q is-active factory-worker.service')
      [ "${FACTORY_TEST_ONLY:-}" = deleted-inode ] && exit 0 ;;
    'show -p MainPID --value factory-worker.service')
      [ "${FACTORY_TEST_ONLY:-}" = deleted-inode ] && { echo 4242; exit 0; } ;;
    '-q is-active factory-server.service')
      [ "${FACTORY_TEST_ONLY:-}" != deleted-inode ] && exit 0 ;;
    'show -p MainPID --value factory-server.service')
      [ "${FACTORY_TEST_ONLY:-}" != deleted-inode ] && { echo 4242; exit 0; } ;;
  esac
fi
case "$*" in
  '-q is-active '*|'-q is-enabled '*) exit 1 ;;
  'show '*) exit 1 ;;
esac
echo "$1 $2" >>"$TEST_EVENTS"
exit 0
EOF
  cat >"$case_dir/bin/readlink" <<'EOF'
#!/bin/bash
if [ "$TEST_MODE" = deleted-inode ] && [ "${1:-}" = /proc/4242/exe ]; then
  if [ "${FACTORY_TEST_ONLY:-}" = deleted-inode ]; then
    echo '/fixture/factory-worker (deleted)'
  else
    printf '%s (deleted)\n' "$TEST_SERVER_BIN"
  fi
  exit 0
fi
exec /usr/bin/readlink "$@"
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
  chmod +x "$case_dir/trusted/"*

  # Production has immutable root-owned paths. The hermetic copy changes only
  # those constants and accepts the fixture owner's files; the shipped script
  # remains unable to read PATH or environment overrides for the gate chain.
  fixture_uid=$(id -u)
  /bin/sed \
    -e "s|^TRUSTED_OWNER_UID=0$|TRUSTED_OWNER_UID=$fixture_uid|" \
    -e 's|\[ "$owner" = "$TRUSTED_OWNER_UID" \]|[[ "$owner" = 0 \|\| "$owner" = "$TRUSTED_OWNER_UID" ]]|' \
    -e "s|^TRUSTED_SETSID=.*$|TRUSTED_SETSID=$case_dir/trusted/setsid|" \
    -e "s|^TRUSTED_SUDO=.*$|TRUSTED_SUDO=$case_dir/trusted/sudo|" \
    -e "s|^TRUSTED_NODE=.*$|TRUSTED_NODE=$case_dir/trusted/node|" \
    -e "s|^TRUSTED_NPX=.*$|TRUSTED_NPX=$case_dir/trusted/npx|" \
    -e "s|^TRUSTED_NPM=.*$|TRUSTED_NPM=$case_dir/trusted/npm|" \
    -e "s|^TRUSTED_GO=.*$|TRUSTED_GO=$case_dir/trusted/go|" \
    -e "s|^TRUSTED_PYTHON=.*$|TRUSTED_PYTHON=$case_dir/trusted/python3|" \
    "$RELEASE" >"$case_dir/fx-factory-release-under-test"
}

configure_release_mode() {
  case_dir=$1 mode=$2
  fixture_release_as=''
  fixture_gate_ready_attempts=500
  fixture_gate_stop_attempts=100
  case "$mode" in
    ui-test-fail|forked-gates-success|forked-gate-fail|gate-result-spoof|path-shadow-chain|handshake-file-spoof|missing-session|signal-forked-gates|signal-before-ready)
      fixture_gate_ready_attempts=20
      fixture_gate_stop_attempts=20
      ;;
  esac
  case "$mode" in
    gate-result-spoof|handshake-file-spoof)
      fixture_release_as="$case_dir/bin/as-fork"
      ;;
  esac
  fixture_release_owner=''
  case "$mode" in
    path-shadow-chain|owner-release) fixture_release_owner=factory:factory ;;
  esac
}

run_release() {
  case_dir=$1 mode=$2 deep_gate=${3:-1}
  configure_release_mode "$case_dir" "$mode"
    TEST_EVENTS="$case_dir/events" TEST_GATES="$case_dir/gates" TEST_MODE="$mode" \
    TEST_RELEASE_SOURCE="$SCRIPT_DIR/.." TEST_REAL_GATE="$SCRIPT_DIR/test-fx-factory-release.sh" \
    TEST_BROKER_EVENTS="$case_dir/broker-events" \
    TEST_SERVER_BIN="$case_dir/install/factory-server" \
    TEST_INTERRUPT_MARK="$case_dir/interrupted" PATH="$case_dir/bin:$PATH" \
    TEST_UI_STARTED="$case_dir/ui-started" TEST_GO_STARTED="$case_dir/go-started" \
    TEST_GO_RUNNING="$case_dir/go-running" TEST_UI_RUNNING="$case_dir/ui-running" \
    TEST_IDENTITY_MARK="$case_dir/identity-retried" \
    TEST_DEFERRED_COMMAND="$case_dir/deferred-pilot-restart" \
    TEST_GATE_CHILDREN="$case_dir/gate-children" \
    TEST_HANDSHAKE_EVENTS="$case_dir/handshake-events" \
    TEST_SPOOF_EVENTS="$case_dir/spoof-events" TEST_SPOOF_LOCK="$case_dir/spoof-lock" \
    TEST_TRUSTED_GATE_ATTACK_STARTED="$case_dir/trusted-gate-attack-started" \
    TEST_RELEASE_DIR="$case_dir/releases" TEST_SETSID_STARTED="$case_dir/setsid-started" \
    TEST_STUCK_CWD="$case_dir" \
    FACTORY_RELEASE_REPO="$case_dir/repo" \
    FACTORY_SERVER_BIN="$case_dir/install/factory-server" \
    FACTORY_WORKER_BIN="$case_dir/install/factory-worker" \
    FACTORY_FX_BIN="$case_dir/install/fx" \
    FACTORY_RELEASE_DRIVER="$case_dir/install/fx-factory-release" \
    FACTORY_BRAIN_LIVE="$case_dir/live" \
    FACTORY_DATABASE="$case_dir/database/factory.sqlite3" \
    FACTORY_RELEASE_DIR="$case_dir/releases" \
    FACTORY_RELEASE_TRUSTED_GATE_DIR="$case_dir/root-owned-gates" \
    FACTORY_RELEASE_INFO="$case_dir/current.json" \
    FACTORY_RELEASE_LOCK="$case_dir/release.lock" \
    FACTORY_RELEASE_AS='' FACTORY_RELEASE_OWNER='' FACTORY_CONTROL_OWNER='' FACTORY_BRAIN_OWNER='' \
    FACTORY_RELEASE_AS="$fixture_release_as" FACTORY_RELEASE_OWNER="$fixture_release_owner" \
    FACTORY_RELEASE_GATE_READY_ATTEMPTS="$fixture_gate_ready_attempts" \
    FACTORY_RELEASE_GATE_STOP_ATTEMPTS="$fixture_gate_stop_attempts" \
    FACTORY_RELEASE_GATE_POLL_DELAY=0.01 \
    FACTORY_RELEASE_DEEP_GATE="$deep_gate" \
    FACTORY_RELEASE_BROKER_BIN="$case_dir/install/factory-release-broker" \
    FACTORY_RELEASE_BROKER_UNIT="$case_dir/install/factory-release-broker.service" \
    FACTORY_RELEASE_BROKER_PILOT_DROPIN="$case_dir/install/factory-pilot.service.d/50-project-release-broker.conf" \
    FACTORY_RELEASE_BROKER_OWNER='' \
    FACTORY_RELEASE_BROKER_SYSTEMCTL="$case_dir/bin/broker-systemctl" \
    FACTORY_RELEASE_BROKER_GETENT="$case_dir/bin/getent" \
    FACTORY_RELEASE_BROKER_GROUPADD="$case_dir/bin/groupadd" \
    FACTORY_WORKER_CONFIG="$case_dir/worker.toml" \
    FACTORY_WORKER_SERVICES="factory-worker.service factory-worker-2.service" \
    FACTORY_API_URL=http://test FACTORY_REGISTER_ATTEMPTS=2 FACTORY_REGISTER_DELAY=0 \
    /usr/bin/timeout --signal=TERM --kill-after=2s "${FACTORY_RELEASE_TEST_TIMEOUT:-30}" \
    /bin/bash "$case_dir/fx-factory-release-under-test" main >"$case_dir/output" 2>&1
}

run_driver() {
  case_dir=$1; shift
  TEST_EVENTS="$case_dir/events" TEST_GATES="$case_dir/gates" TEST_MODE=control \
    PATH="$case_dir/bin:$PATH" FACTORY_SERVER_BIN="$case_dir/install/factory-server" \
    FACTORY_WORKER_BIN="$case_dir/install/factory-worker" FACTORY_FX_BIN="$case_dir/install/fx" \
    FACTORY_RELEASE_DRIVER="$case_dir/install/fx-factory-release" FACTORY_BRAIN_LIVE="$case_dir/live" \
    FACTORY_DATABASE="$case_dir/database/factory.sqlite3" FACTORY_RELEASE_DIR="$case_dir/releases" \
    FACTORY_RELEASE_TRUSTED_GATE_DIR="$case_dir/root-owned-gates" \
    FACTORY_RELEASE_INFO="$case_dir/current.json" FACTORY_RELEASE_LOCK="$case_dir/release.lock" \
    FACTORY_RELEASE_AS='' FACTORY_RELEASE_OWNER="${fixture_release_owner:-}" FACTORY_CONTROL_OWNER='' FACTORY_BRAIN_OWNER='' FACTORY_RELEASE_BROKER_OWNER='' \
    FACTORY_RELEASE_BROKER_BIN="$case_dir/install/factory-release-broker" \
    FACTORY_RELEASE_BROKER_UNIT="$case_dir/install/factory-release-broker.service" \
    FACTORY_RELEASE_BROKER_PILOT_DROPIN="$case_dir/install/factory-pilot.service.d/50-project-release-broker.conf" \
    FACTORY_WORKER_SERVICES="factory-worker.service factory-worker-2.service" FACTORY_API_URL=http://test \
    /usr/bin/timeout --signal=TERM --kill-after=2s "${FACTORY_RELEASE_TEST_TIMEOUT:-30}" \
    /bin/bash "$case_dir/fx-factory-release-under-test" "$@"
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
    TEST_SPOOF_EVENTS="$case_dir/spoof-events" TEST_SPOOF_LOCK="$case_dir/spoof-lock" \
    TEST_RELEASE_DIR="$case_dir/releases" TEST_SETSID_STARTED="$case_dir/setsid-started" \
    TEST_STUCK_CWD="$case_dir" \
    FACTORY_RELEASE_REPO="$case_dir/repo" \
    FACTORY_SERVER_BIN="$case_dir/install/factory-server" \
    FACTORY_WORKER_BIN="$case_dir/install/factory-worker" \
    FACTORY_FX_BIN="$case_dir/install/fx" \
    FACTORY_RELEASE_DRIVER="$case_dir/install/fx-factory-release" \
    FACTORY_BRAIN_LIVE="$case_dir/live" \
    FACTORY_DATABASE="$case_dir/database/factory.sqlite3" \
    FACTORY_RELEASE_DIR="$case_dir/releases" \
    FACTORY_RELEASE_TRUSTED_GATE_DIR="$case_dir/root-owned-gates" \
    FACTORY_RELEASE_INFO="$case_dir/current.json" \
    FACTORY_RELEASE_LOCK="$case_dir/release.lock" \
    FACTORY_RELEASE_AS='' FACTORY_RELEASE_OWNER='' FACTORY_CONTROL_OWNER='' FACTORY_BRAIN_OWNER='' \
    FACTORY_RELEASE_AS="$fixture_release_as" FACTORY_RELEASE_OWNER="$fixture_release_owner" \
    FACTORY_RELEASE_GATE_READY_ATTEMPTS="$fixture_gate_ready_attempts" \
    FACTORY_RELEASE_GATE_STOP_ATTEMPTS="$fixture_gate_stop_attempts" \
    FACTORY_RELEASE_GATE_POLL_DELAY=0.01 \
    FACTORY_RELEASE_DEEP_GATE=1 \
    FACTORY_RELEASE_BROKER_BIN="$case_dir/install/factory-release-broker" \
    FACTORY_RELEASE_BROKER_UNIT="$case_dir/install/factory-release-broker.service" \
    FACTORY_RELEASE_BROKER_PILOT_DROPIN="$case_dir/install/factory-pilot.service.d/50-project-release-broker.conf" \
    FACTORY_RELEASE_BROKER_OWNER='' \
    FACTORY_RELEASE_BROKER_SYSTEMCTL="$case_dir/bin/broker-systemctl" \
    FACTORY_RELEASE_BROKER_GETENT="$case_dir/bin/getent" \
    FACTORY_RELEASE_BROKER_GROUPADD="$case_dir/bin/groupadd" \
    FACTORY_WORKER_CONFIG="$case_dir/worker.toml" \
    FACTORY_API_URL=http://test FACTORY_REGISTER_ATTEMPTS=2 FACTORY_REGISTER_DELAY=0 \
    env --default-signal=INT /usr/bin/timeout --foreground --signal=TERM --kill-after=2s \
      "${FACTORY_RELEASE_TEST_TIMEOUT:-30}" /bin/bash "$case_dir/fx-factory-release-under-test" main \
      >"$case_dir/output" 2>&1 &
  release_pid=$!
}

run_crash_cleanup() {
  local crash_phase crashed status current_after_recovery
  for crash_phase in prepared old-stopped pair-installed services-started; do
    crashed="$temporary/crash-$crash_phase"
    make_fixture "$crashed" parallel-success
    set +e
    FACTORY_RELEASE_CRASH_AFTER_PHASE="$crash_phase" run_release "$crashed" parallel-success
    status=$?
    set -e
    [ "$status" -ne 0 ] || fail "crash hook $crash_phase unexpectedly committed"
    [ "$status" -ne 124 ] || fail "crash cleanup $crash_phase exceeded ${FACTORY_RELEASE_TEST_TIMEOUT:-30}s"
    assert_file "$crashed/releases/transaction" "phase=$crash_phase"
    : >"$crashed/events"
    FACTORY_RELEASE_CRASH_AFTER_PHASE= run_release "$crashed" parallel-success \
      || { cat "$crashed/output" >&2; fail "restart did not recover phase $crash_phase"; }
    [ ! -e "$crashed/releases/transaction" ] || fail "recovery left journal for $crash_phase"
    current_after_recovery=$(readlink -f "$crashed/releases/current")
    [ -f "$current_after_recovery/manifest.json" ] || fail "recovery did not reach a committed generation"
  done
}

run_fast_release() {
  local fast="$temporary/fast"
  make_fixture "$fast" parallel-success
  run_release "$fast" parallel-success 0 \
    || { cat "$fast/output" >&2; fail "fast release failed"; }
  for skipped in 'npx tsc -p tsconfig.app.json --noEmit' 'npm test' \
    'go test ./...' 'python3 -m unittest pilot.test_pilot' \
    'bash ops/test-fx-factory-release.sh'; do
    ! grep -Fx "$skipped" "$fast/gates" >/dev/null \
      || fail "fast release unexpectedly ran: $skipped"
  done
  grep -Fx 'npx vite build' "$fast/gates" >/dev/null \
    || fail "fast release did not build the UI"
  grep -F 'go build -ldflags ' "$fast/gates" >/dev/null \
    || fail "fast release did not build Linux binaries"
  grep -F 'быстрый выпуск: код уже проверен обязательным Linux-воротом GitHub' "$fast/output" >/dev/null \
    || fail "fast release did not explain why duplicate tests were skipped"
}

if [ "${FACTORY_TEST_ONLY:-}" = fast-release ]; then
  run_fast_release
  echo "PASS: fast release builds, installs and verifies without duplicate test suites"
  exit 0
fi

if [ "${FACTORY_TEST_ONLY:-}" = crash-cleanup ]; then
  run_crash_cleanup
  echo "PASS: crash-cleanup scenarios recovered every journal phase"
  exit 0
fi

if [ "${FACTORY_TEST_ONLY:-}" = forged-gate-result ]; then
  forged_gate_result="$temporary/forged-gate-result"
  make_fixture "$forged_gate_result" forged-gate-result
  set +e
  run_release "$forged_gate_result" forged-gate-result
  status=$?
  set -e
  [ "$status" -eq 5 ] || fail "forged-gate-result returned $status instead of build error 5"
  assert_file "$forged_gate_result/install/factory-server" old-server
  assert_file "$forged_gate_result/install/factory-worker" old-worker
  [ ! -s "$forged_gate_result/events" ] || fail "services restarted after forged-gate-result"
  ! grep -F 'go build ' "$forged_gate_result/gates" >/dev/null \
    || fail "binaries were built after forged-gate-result"
  grep -Fx 'forged-gate-result' "$forged_gate_result/spoof-events" >/dev/null \
    || fail "forged result scenario did not inject a fake successful status"
  assert_no_fixture_processes "$forged_gate_result"
  echo "PASS: real forked gate error won over forged success; install was not started"
  exit 0
fi

if [ "${FACTORY_TEST_ONLY:-}" = deleted-inode ]; then
  deleted_inode="$temporary/deleted-inode"
  make_fixture "$deleted_inode" deleted-inode
  set +e
  run_release "$deleted_inode" deleted-inode
  status=$?
  set -e
  [ "$status" -eq 4 ] || fail "deleted-inode returned $status instead of preflight error 4"
  grep -F 'процесс factory-worker.service использует deleted-inode' "$deleted_inode/output" >/dev/null \
    || fail "deleted-inode refusal did not name the affected unit"
  [ ! -s "$deleted_inode/events" ] || fail "deleted-inode mutated services before refusal"
  [ ! -e "$deleted_inode/releases/transaction" ] || fail "deleted-inode created a release journal"
  [ ! -e "$deleted_inode/releases/current" ] || fail "deleted-inode changed current generation"
  assert_no_fixture_processes "$deleted_inode"
  echo "PASS: deleted-inode preflight names the unit and stops before mutation"
  exit 0
fi

success="$temporary/success"
make_fixture "$success" parallel-success
cp "$success/current.json" "$success/source-current.json"
mkdir -p "$success/releases/build-orphaned" "$success/releases/operator-data" \
  "$success/outside-build-target"
printf 'remove me\n' >"$success/releases/build-orphaned/marker"
printf 'keep me\n' >"$success/releases/operator-data/marker"
printf 'outside stays\n' >"$success/outside-build-target/marker"
ln -s "$success/outside-build-target" "$success/releases/build-external-link"
run_release "$success" parallel-success \
  || { cat "$success/output" >&2; fail "successful release failed"; }
[ ! -e "$success/releases/build-orphaned" ] \
  || fail "successful release retained an orphaned build directory"
assert_file "$success/releases/operator-data/marker" 'keep me'
[ -L "$success/releases/build-external-link" ] \
  || fail "successful release removed a build-prefixed symlink"
assert_file "$success/releases/build-external-link/marker" 'outside stays'
assert_file "$success/outside-build-target/marker" 'outside stays'
grep -F 'удаляю остаток прерванной сборки: build-orphaned' "$success/output" >/dev/null \
  || fail "successful release did not report orphaned build cleanup"
grep -F 'пропускаю небезопасный остаток сборки:' "$success/output" >/dev/null \
  || fail "successful release did not report the skipped symlink"
wait_for_file "$success/ui-started"
wait_for_file "$success/go-started"
for gate in 'npx tsc -p tsconfig.app.json --noEmit' 'npm test' \
  'go test ./...' 'python3 -m unittest pilot.test_pilot' \
  'bash ops/test-fx-factory-release.sh'; do
  assert_before "$success/gates" "$gate" 'npx vite build'
done
assert_before "$success/gates" 'npx vite build' 'go build -ldflags '
grep -F 'полный вывод: UI-проверки' "$success/output" >/dev/null \
  || fail "UI output was not kept separate"
grep -F 'полный вывод: Go-проверки, тесты пилота и сценарий выката' "$success/output" >/dev/null \
  || fail "Go and Pilot output was not kept separate"

run_fast_release
assert_file "$success/install/factory-server" '#!/bin/bash'
assert_file "$success/install/factory-worker" '#!/bin/bash'
! grep -Fx 'untrusted-git-invoked' "$success/spoof-events" >/dev/null 2>&1 \
  || fail "release source chain invoked PATH-provided git"
assert_file "$success/install/factory-release-broker" '#!/bin/bash'
assert_file "$success/install/factory-release-broker" '# candidate-broker'
current_generation=$(readlink -f "$success/releases/current")
previous_generation=$(readlink -f "$success/releases/previous")
[ -f "$current_generation/manifest.json" ] && [ -f "$current_generation/manifest.sha256" ] \
  || fail "committed generation has no immutable manifest"
[ -f "$current_generation/database.sqlite3" ] && [ -d "$previous_generation" ] \
  || fail "release did not retain snapshot and previous complete generation"
verify_immutable_generation "$current_generation" \
  || fail "candidate generation did not pass immutable verification"
verify_immutable_generation "$previous_generation" \
  || fail "bootstrap generation did not pass immutable verification"
python3 - "$current_generation" "$previous_generation" "$success/source-current.json" <<'PY' \
  || fail "bootstrap manifest does not cover the complete installed release"
import json,sys
current,previous,source_info=sys.argv[1:]
expected={
 "payload/factory-server","payload/factory-worker","payload/factory-release-broker",
 "payload/factory-release-broker.service","payload/factory-release-broker-dropin.conf",
 "payload/fx","payload/fx-factory-release","payload/pilot.py","payload/context.md",
 "payload/intake-app.py","payload/intake-plan.py","release-info.json","services.tsv",
}
candidate=json.load(open(current+"/manifest.json"))
bootstrap=json.load(open(previous+"/manifest.json"))
source=json.load(open(source_info))
assert expected <= {item["source"] for item in candidate["artifacts"]}
assert expected <= {item["source"] for item in bootstrap["artifacts"]}
assert bootstrap["candidate_sha"]==source["sha"]
assert bootstrap["source_release_id"]==source["release_id"]
assert json.load(open(previous+"/release-info.json"))==source
assert bootstrap["database"]["snapshot"]=="database.sqlite3"
assert bootstrap["processes"]==candidate["processes"]
assert bootstrap["services"]==candidate["services"]
PY
assert_before "$success/events" 'stop factory-worker.service' 'stop factory-server.service'
! grep -Fx 'stop factory-release-broker.service' "$success/events" >/dev/null \
  || fail "release stopped its parent broker before terminal persistence"
assert_before "$success/events" 'backup-snapshot' 'stop factory-worker.service'
assert_before "$success/events" 'stop factory-server.service' 'start factory-server.service'
assert_before "$success/events" 'start factory-server.service' 'start factory-worker.service'
grep -F 'выкачено:' "$success/output" >/dev/null || fail "release did not report success"
grep -F 'Проверочный релиз' "$success/output" >/dev/null \
  || fail "release did not explain the deployed change"
! grep -F 'Merge pull request' "$success/output" >/dev/null \
  || fail "release exposed GitHub merge plumbing instead of a human title"
! grep -F '#123' "$success/output" >/dev/null \
  || fail "release exposed a pull request number in owner-facing output"

# Historical generations are not rollback targets. A fresh, even corrupted,
# unreferenced copy must neither block the next release nor survive it. The
# bootstrap snapshot (ledger <= 27), current and previous remain protected.
stale_generation="$success/releases/generations/stale-unreferenced"
cp -a "$previous_generation" "$stale_generation"
python3 - "$stale_generation/manifest.json" <<'PY'
import json, sys
path=sys.argv[1]
body=json.load(open(path))
body.setdefault("database", {})["ledger"]=30
with open(path, "w") as out: json.dump(body, out)
PY
printf 'tampered stale payload\n' >>"$stale_generation/payload/factory-worker"
# The second release is a new boot cycle. Drop the first cycle's synthetic
# service events so the worker-health fixture can emit a genuinely newer
# heartbeat after restart, just as production does.
: >"$success/events"
run_release "$success" parallel-success 0 \
  || { cat "$success/output" >&2; fail "release was blocked by unreferenced history"; }
[ ! -e "$stale_generation" ] || fail "unreferenced generation survived retention"
current_generation=$(readlink -f "$success/releases/current")
previous_generation=$(readlink -f "$success/releases/previous")
verify_immutable_generation "$current_generation" \
  || fail "retention damaged current generation"
verify_immutable_generation "$previous_generation" \
  || fail "retention damaged previous generation"
find "$success/releases/generations" -mindepth 1 -maxdepth 1 -type d -name 'bootstrap-*' -print -quit \
  | grep -q . || fail "retention removed the bootstrap generation"
grep -F 'retention: удалено старое поколение вне current/previous: stale-unreferenced' "$success/output" >/dev/null \
  || fail "retention did not explain removal of unreferenced history"

fresh_snapshot="$temporary/installed-server-no-backup"
make_fixture "$fresh_snapshot" installed-server-no-backup
run_release "$fresh_snapshot" installed-server-no-backup \
  || { cat "$fresh_snapshot/output" >&2; fail "fresh server snapshot fallback failed"; }
grep -F 'текущий server не знает новую схему' "$fresh_snapshot/output" >/dev/null \
  || fail "snapshot fallback was not reported"
assert_before "$fresh_snapshot/events" candidate-backup 'stop factory-worker.service'
! grep -Fx 'backup-snapshot' "$fresh_snapshot/events" >/dev/null \
  || fail "incompatible installed server created the snapshot"

forked_success="$temporary/forked-gates-success"
make_fixture "$forked_success" forked-gates-success
run_release "$forked_success" forked-gates-success \
  || { cat "$forked_success/output" >&2; fail "forked gates lost a successful status"; }
[ "$(grep -Fxc 'setsid-forked' "$forked_success/handshake-events")" -eq 2 ] \
  || fail "successful fork scenario did not fork both gate sessions"
! grep -Fx 'untrusted-git-invoked' "$forked_success/spoof-events" >/dev/null \
  || fail "successful fork scenario invoked untrusted git"
assert_file "$forked_success/install/factory-server" '#!/bin/bash'
assert_file "$forked_success/install/factory-worker" '#!/bin/bash'
[ "$(grep -Fxc 'start factory-server.service' "$forked_success/events")" -eq 1 ] \
  || fail "successful fork scenario did not install exactly once"
assert_no_fixture_processes "$forked_success"

# A PATH-provided Node must not be able to turn either UI command into success.
path_shadow_success="$temporary/path-shadow-success"
make_fixture "$path_shadow_success" parallel-success
run_release "$path_shadow_success" parallel-success \
  || { cat "$path_shadow_success/output" >&2; fail "PATH-shadowed gate did not complete"; }
! grep -Fx 'path-setsid-invoked' "$path_shadow_success/spoof-events" >/dev/null 2>&1 \
  || fail "PATH shadow entered the trusted gate chain"
! grep -Fx 'path-node-invoked' "$path_shadow_success/spoof-events" >/dev/null 2>&1 \
  || fail "PATH node entered the trusted gate chain"
! grep -Fx 'untrusted-git-invoked' "$path_shadow_success/spoof-events" >/dev/null 2>&1 \
  || fail "PATH git entered the trusted source chain"
assert_no_fixture_processes "$path_shadow_success"

metadata_mode="$temporary/metadata-mode-0644"
make_fixture "$metadata_mode" metadata-mode-0644
cp "$metadata_mode/current.json" "$metadata_mode/source-current.json"
chmod 644 "$metadata_mode/current.json"
set +e
run_release "$metadata_mode" metadata-mode-0644
status=$?
set -e
[ "$status" -eq 4 ] || fail "metadata mode 0644 was not rejected before release work"
assert_preflight_refusal "$metadata_mode"
cmp "$metadata_mode/source-current.json" "$metadata_mode/current.json" \
  || fail "metadata mode refusal rewrote the live metadata"
[ "$(stat -c %a "$metadata_mode/current.json")" = 644 ] \
  || fail "metadata mode refusal corrected permissions automatically"
[ ! -e "$metadata_mode/releases/generations" ] \
  || fail "metadata mode refusal created release history"

missing_release_id="$temporary/missing-release-id"
make_fixture "$missing_release_id" missing-release-id
python3 - "$missing_release_id/current.json" <<'PY'
import json,sys
path=sys.argv[1]
data=json.load(open(path)); data.pop("release_id")
json.dump(data,open(path,"w"),sort_keys=True,separators=(",",":"))
PY
chmod 600 "$missing_release_id/current.json"
cp "$missing_release_id/current.json" "$missing_release_id/source-current.json"
set +e
run_release "$missing_release_id" missing-release-id
status=$?
set -e
[ "$status" -eq 4 ] || fail "missing release_id was not rejected before release work"
assert_preflight_refusal "$missing_release_id"
cmp "$missing_release_id/source-current.json" "$missing_release_id/current.json" \
  || fail "missing release_id refusal rewrote the live metadata"
[ ! -e "$missing_release_id/releases/generations" ] \
  || fail "missing release_id refusal created release history"

partial_history="$temporary/partial-history"
make_fixture "$partial_history" partial-history
mkdir -p "$partial_history/releases/generations/unfinished"
ln -s "$partial_history/releases/generations/unfinished" "$partial_history/releases/current"
set +e
run_release "$partial_history" partial-history
status=$?
set -e
[ "$status" -eq 4 ] || fail "partial release history was not rejected before release work"
assert_preflight_refusal "$partial_history"
[ -L "$partial_history/releases/current" ] && [ -d "$partial_history/releases/generations/unfinished" ] \
  || fail "partial history refusal rewrote the existing history"

dangling_history="$temporary/dangling-history"
make_fixture "$dangling_history" dangling-history
mkdir -p "$dangling_history/releases/generations"
ln -s "$dangling_history/releases/generations/missing-current" "$dangling_history/releases/current"
ln -s "$dangling_history/releases/generations/missing-previous" "$dangling_history/releases/previous"
set +e
run_release "$dangling_history" dangling-history
status=$?
set -e
[ "$status" -eq 4 ] || fail "two dangling release links were not rejected before release work"
assert_preflight_refusal "$dangling_history"
grep -F 'не указывают на проверенные поколения' "$dangling_history/output" >/dev/null \
  || fail "two dangling links did not explain the rejected history"

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

run_crash_cleanup

build_failed="$temporary/worker-build-fail"
make_fixture "$build_failed" worker-build-fail
if run_release "$build_failed" worker-build-fail; then fail "worker build unexpectedly succeeded"; fi
assert_file "$build_failed/install/factory-server" old-server
assert_file "$build_failed/install/factory-worker" old-worker
[ ! -s "$build_failed/events" ] || fail "services restarted after a build failure"
assert_no_fixture_processes "$build_failed"

for mode in ui-test-fail go-test-fail pilot-test-fail release-test-fail forged-gate-result; do
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
grep -Fx 'python3 -m unittest pilot.test_pilot' "$temporary/pilot-test-fail/gates" >/dev/null \
  || fail "pilot failure scenario did not run the Pilot test suite"
! grep -Fx 'bash ops/test-fx-factory-release.sh' "$temporary/pilot-test-fail/gates" >/dev/null \
  || fail "release scenario gate ran after the Pilot test suite failed"
grep -Fx 'forged-gate-result' "$temporary/forged-gate-result/spoof-events" >/dev/null \
  || fail "forged result scenario did not inject a fake successful status"
grep -Fx 'go-stopped' "$temporary/ui-test-fail/gate-children" >/dev/null \
  || fail "a failed UI group did not stop and reap the Go group"

extracted_gate="$temporary/trusted-gate-real-race"
make_fixture "$extracted_gate" trusted-gate-real-race
start_gate_directory_attack "$extracted_gate"
run_release "$extracted_gate" trusted-gate-real-race \
  || { cat "$extracted_gate/output" >&2; fail "the extracted trusted gate did not run"; }
wait "$trusted_gate_attack_pid" || true
grep -Fx 'real-extracted-gate-after-handshake' "$extracted_gate/handshake-events" >/dev/null \
  || fail "the real extracted gate did not run after a verified handshake"
[ -e "$extracted_gate/trusted-gate-attack-started" ] \
  || fail "the concurrent gate-directory substitution attempt did not start"
! find "$extracted_gate/releases" -maxdepth 1 -type d -name 'trusted-gate-*' -print -quit | grep -q . \
  || fail "a trusted gate was created below the user-writable release directory"
assert_file "$extracted_gate/install/factory-server" '#!/bin/bash'
assert_no_fixture_processes "$extracted_gate"

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
forked_failed="$temporary/forked-gate-fail"
make_fixture "$forked_failed" forked-gate-fail
set +e
run_release "$forked_failed" forked-gate-fail
status=$?
set -e
[ "$status" -eq 5 ] || fail "forked failing gate returned $status instead of build error 5"
[ "$(grep -Fxc 'setsid-forked' "$forked_failed/handshake-events")" -eq 2 ] \
  || fail "failing fork scenario did not fork both gate sessions"
[ "$(grep -Fxc 'setsid-waits' "$forked_failed/handshake-events")" -eq 2 ] \
  || fail "forked failure did not keep the launcher waiting for both gate statuses"
# The release may continue only when Bash reaps one of the two launchers it
# started.  The fixture's successful forged result is deliberately ignored.
! grep -F 'ядро не вернуло статус известного launcher test gate' "$forked_failed/output" >/dev/null \
  || fail "forked failure accepted an unknown launcher status"
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

spoofed_result="$temporary/gate-result-spoof"
make_fixture "$spoofed_result" gate-result-spoof
set +e
run_release "$spoofed_result" gate-result-spoof
status=$?
set -e
[ "$status" -eq 5 ] || fail "spoofed successful result returned $status instead of build error 5"
for attack in stale corrupt valid-success replayed-success; do
  grep -Fx "$attack" "$spoofed_result/spoof-events" >/dev/null \
    || fail "adversarial AS did not attempt $attack result"
done
! grep -Fx 'result-path-leaked' "$spoofed_result/spoof-events" >/dev/null \
  || fail "gate result path was passed through adversarial AS"
grep -F 'завершилась с кодом 1' "$spoofed_result/output" >/dev/null \
  || fail "spoof hid the real gate status"
assert_file "$spoofed_result/install/factory-server" old-server
assert_file "$spoofed_result/install/factory-worker" old-worker
[ ! -s "$spoofed_result/events" ] \
  || fail "installation ran after AS forged a successful gate result"
! grep -F 'go build ' "$spoofed_result/gates" >/dev/null \
  || fail "binaries were built after the spoofed gate failure"
assert_no_fixture_processes "$spoofed_result"

path_shadow="$temporary/path-shadow-chain"
make_fixture "$path_shadow" path-shadow-chain
mkdir -p "$path_shadow/attacker/build-fake"
TEST_RELEASE_DIR="$path_shadow/attacker" TEST_SPOOF_EVENTS="$path_shadow/attacker-events" \
  "$path_shadow/bin/setsid" || fail "malicious PATH setsid did not return success"
assert_file "$path_shadow/attacker/build-fake/ui-checks.session" \
  'sid=999999 pgid=999999 ready=1'
: >"$path_shadow/spoof-events"
set +e
run_release "$path_shadow" path-shadow-chain
status=$?
set -e
[ "$status" -eq 5 ] || fail "PATH-shadowed chain returned $status instead of build error 5"
grep -Fx 'bash ops/test-fx-factory-release.sh' "$path_shadow/gates" >/dev/null \
  || fail "absolute trusted gate script did not run"
for bypass in path-setsid-invoked path-sudo-invoked path-bash-gate-invoked path-gate-invoked; do
  ! grep -Fx "$bypass" "$path_shadow/spoof-events" >/dev/null 2>&1 \
    || fail "PATH shadow entered the trusted gate chain: $bypass"
done
assert_file "$path_shadow/install/factory-server" old-server
assert_file "$path_shadow/install/factory-worker" old-worker
[ ! -s "$path_shadow/events" ] || fail "PATH shadow caused an install or restart"
! grep -F 'go build ' "$path_shadow/gates" >/dev/null \
  || fail "binaries were replaced after the PATH-shadowed gate failure"
assert_no_fixture_processes "$path_shadow"

forged_handshake="$temporary/handshake-file-spoof"
make_fixture "$forged_handshake" handshake-file-spoof
set +e
run_release "$forged_handshake" handshake-file-spoof
status=$?
set -e
[ "$status" -eq 5 ] || fail "forged handshake returned $status instead of build error 5"
grep -Fx 'forged-handshake' "$forged_handshake/spoof-events" >/dev/null \
  || fail "handshake attacker did not write a forged file"
assert_file "$forged_handshake/install/factory-server" old-server
assert_file "$forged_handshake/install/factory-worker" old-worker
[ ! -s "$forged_handshake/events" ] || fail "forged handshake caused an install or restart"
! grep -F 'go build ' "$forged_handshake/gates" >/dev/null \
  || fail "binaries were replaced after the forged handshake"
/bin/sleep 0.3
assert_no_fixture_processes "$forged_handshake"

missing_session="$temporary/missing-session"
make_fixture "$missing_session" missing-session
set +e
run_release "$missing_session" missing-session
status=$?
set -e
[ "$status" -eq 5 ] || fail "missing session returned $status instead of build error 5"
grep -F 'не дождался handshake реальной session' "$missing_session/output" >/dev/null \
  || fail "missing live session was not rejected before gate readiness"
assert_file "$missing_session/install/factory-server" old-server
assert_file "$missing_session/install/factory-worker" old-worker
[ ! -s "$missing_session/events" ] || fail "missing session caused an install or restart"
! grep -F 'go build ' "$missing_session/gates" >/dev/null \
  || fail "binaries were replaced without a live session"
assert_no_fixture_processes "$missing_session"

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

deleted_inode="$temporary/deleted-inode"
make_fixture "$deleted_inode" deleted-inode
set +e
run_release "$deleted_inode" deleted-inode
status=$?
set -e
[ "$status" -eq 4 ] || fail "deleted inode was not rejected before release"
[ ! -s "$deleted_inode/events" ] || fail "deleted inode caused a service mutation"
grep -F 'процесс factory-server.service использует deleted-inode' "$deleted_inode/output" >/dev/null \
  || fail "deleted inode refusal was not human-readable"

rollback_case="$temporary/full-rollback"
make_fixture "$rollback_case" parallel-success
run_release "$rollback_case" owner-release || fail "rollback fixture release failed"
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

# A release after rollback must accept the metadata republished from the old
# generation when Factory owns it explicitly, as production does.
run_driver "$rollback_case" --rollback >"$rollback_case/second-rollback-output" 2>&1 \
  || { cat "$rollback_case/second-rollback-output" >&2; fail "second rollback with release owner failed"; }
[ "$(stat -c %U:%G "$rollback_case/current.json")" = factory:factory ] \
  || fail "rollback did not restore the configured owner on release metadata"
run_release "$rollback_case" owner-release \
  || { cat "$rollback_case/output" >&2; fail "release after rollback with owner failed"; }

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
