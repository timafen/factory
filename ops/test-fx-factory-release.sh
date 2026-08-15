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
  for dependency in fx-factory-release install-project-release-broker.sh factory-live-acceptance fx \
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
    "$case_dir/units" \
    "$case_dir/live/pilot" "$case_dir/live/intake" "$case_dir/database"
  : >"$case_dir/units/factory-worker.service"
  : >"$case_dir/units/factory-worker-2.service"
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
  /bin/cp "$SCRIPT_DIR/factory-live-acceptance" "$case_dir/install/factory-live-acceptance"
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
    "$case_dir/install/factory-release-broker" "$case_dir/install/factory-live-acceptance" \
    "$case_dir/install/fx" "$case_dir/install/fx-factory-release"
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
    /bin/cp "$TEST_RELEASE_SOURCE/ops/factory-live-acceptance" \
      "$destination/ops/factory-live-acceptance"
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
  if [ "$TEST…8334 tokens truncated…history"

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

