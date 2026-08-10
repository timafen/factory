#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
RELEASE="$SCRIPT_DIR/fx-factory-release"
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
assert_file() { grep -Fx "$2" "$1" >/dev/null || fail "$1 does not contain: $2"; }
assert_trusted_unchanged() {
  assert_file "$1/system/trusted-helper" trusted-release-helper
  assert_file "$1/system/browser-checker" '#!/bin/bash'
  assert_file "$1/system/brain-installer" '#!/bin/bash'
}

make_fixture() {
  case_dir=$1 mode=$2
  mkdir -p "$case_dir/bin" "$case_dir/install" "$case_dir/releases" "$case_dir/repo/web" "$case_dir/system"
  printf 'old-server\n' >"$case_dir/install/factory-server"
  printf 'old-worker\n' >"$case_dir/install/factory-worker"
  chmod +x "$case_dir/install/factory-server" "$case_dir/install/factory-worker"
  : >"$case_dir/events"
  : >"$case_dir/backup-events"
  : >"$case_dir/worker.toml"
  printf 'root-only secret\n' >"$case_dir/secret"
  printf 'trusted-release-helper\n' >"$case_dir/system/trusted-helper"
  printf 'old janitor\n' >"$case_dir/system/janitor"
  cat >"$case_dir/system/browser-checker" <<'CHECKER'
#!/bin/bash
printf 'browser-chain worker=%s\n' "${FACTORY_BROWSER_WORKER:-}" >>"$TEST_SYSTEM_EVENTS"
[ "$TEST_MODE" != browser-chain-fail ]
CHECKER
  cat >"$case_dir/system/brain-installer" <<'BRAIN'
#!/bin/bash
printf 'brain-installer source=%s\n' "$1" >>"$TEST_SYSTEM_EVENTS"
printf 'brain-source-parent-mode=%s\n' "$(stat -c %a "$(dirname "$1")")" >>"$TEST_SYSTEM_EVENTS"
printf 'brain-context=%s\n' "$(cat "$1/pilot/context.md")" >>"$TEST_SYSTEM_EVENTS"
BRAIN
  chmod +x "$case_dir/system/browser-checker" "$case_dir/system/brain-installer"

  cat >"$case_dir/bin/git" <<'GIT'
#!/bin/bash
case "$*" in
  *'clone --quiet'*)
    destination=${@: -1}
    mkdir -p "$destination/web" "$destination/ops" "$destination/pilot" "$destination/intake"
    printf 'committed context\n' >"$destination/pilot/context.md"
    printf 'committed = True\n' >"$destination/pilot/pilot.py"
    printf 'committed = True\n' >"$destination/intake/app.py"
    printf 'committed = True\n' >"$destination/intake/plan.py"
    if [ "$TEST_MODE" = snapshot-symlink ]; then
      case "$destination" in
        /tmp/factory-release-source-*/source)
          rm "$destination/pilot/context.md"
          ln -s "$TEST_SECRET" "$destination/pilot/context.md"
          ;;
      esac
    fi
    for file in fx fx-factory-release bootstrap-factory-release.sh install-brain.sh install-server-browser.sh factory-browser-sandbox test-browser-sandbox.sh; do
      printf '#!/bin/sh\nprintf "untrusted %%s\\n" "$0" >>"$TEST_UNTRUSTED_EXECUTED"\n' >"$destination/ops/$file"
      chmod 755 "$destination/ops/$file"
    done
    printf '#!/bin/sh\n# committed janitor\n' >"$destination/ops/factory-janitor.sh"
    ;;
  *'checkout --quiet'*) exit 0 ;;
  *'rev-parse HEAD'*) echo 1234567890abcdef ;;
  *'log -1'*) echo 'Проверочный релиз' ;;
esac
GIT
  cat >"$case_dir/bin/npm" <<'NPM'
#!/bin/bash
echo "npm $*" >>"$TEST_GATES"
[ "$TEST_MODE" != ui-test-fail ] || [ "${1:-}" != test ] || exit 1
NPM
  cat >"$case_dir/bin/npx" <<'NPX'
#!/bin/bash
echo "npx $*" >>"$TEST_GATES"
NPX
  cat >"$case_dir/bin/go" <<'GO'
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
[ "${1:-}" = identity ] && {
  grep -F 'stop factory-worker.service' "$TEST_EVENTS" >/dev/null || exit 9
  echo worker-release-test
  exit 0
}
WORKER
    if [ "$TEST_MODE" = checkout-mutated ]; then
      printf 'mutated after build\n' >pilot/context.md
      printf '#!/bin/sh\n# mutated janitor\n' >ops/factory-janitor.sh
    fi
    ;;
  *) printf '#!/bin/bash\nexit 0\n' >"$output" ;;
esac
chmod +x "$output"
GO
  cat >"$case_dir/bin/bash" <<'BASH'
#!/bin/bash
case "${1:-}" in
  ops/test-fx-factory-release-dispatch.sh|ops/test-bootstrap-factory-release.sh|ops/test-install-server-browser.sh|ops/test-fx-browser-sandbox.sh|ops/test-install-brain.sh|ops/test-fx-factory-release.sh)
    echo "bash $1" >>"$TEST_GATES"
    [ "$TEST_MODE" != release-test-fail ] || [ "$1" != ops/test-fx-factory-release.sh ]
    exit
    ;;
esac
exec /bin/bash "$@"
BASH
  cat >"$case_dir/bin/systemctl" <<'SYSTEMCTL'
#!/bin/bash
echo "$1 $2" >>"$TEST_EVENTS"
SYSTEMCTL
  cat >"$case_dir/bin/mv" <<'MV'
#!/bin/bash
/bin/mv "$@" || exit
target=${@: -1}
if [ "$TEST_MODE" = interrupt-between-install ] \
  && [ "$target" = "$TEST_SERVER_BIN" ] && [ ! -e "$TEST_INTERRUPT_MARK" ]; then
  : >"$TEST_INTERRUPT_MARK"
  kill -TERM "$PPID"
fi
MV
  printf '#!/bin/bash\nexit 0\n' >"$case_dir/bin/sleep"
  cat >"$case_dir/bin/chmod" <<'CHMOD'
#!/bin/bash
if [ "$TEST_MODE" = worker-install-fail ] \
  && [[ "${*: -1}" = *.factory-release-factory-worker.* ]]; then exit 1; fi
exec /bin/chmod "$@"
CHMOD
  cat >"$case_dir/bin/cp" <<'CP'
#!/bin/bash
target=${@: -1}
case "$target" in
  /tmp/factory-release-backup-*/*.prev)
    printf 'backup=%s mode=%s\n' "$target" "$(stat -c %a "$(dirname "$target")")" >>"$TEST_BACKUP_EVENTS"
    ;;
esac
exec /bin/cp "$@"
CP
  cat >"$case_dir/bin/curl" <<'CURL'
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
CURL
  chmod +x "$case_dir/bin/"*
}

run_release() {
  case_dir=$1 mode=$2
  TEST_EVENTS="$case_dir/events" TEST_GATES="$case_dir/gates" TEST_MODE="$mode" \
    TEST_BACKUP_EVENTS="$case_dir/backup-events" \
    TEST_SYSTEM_EVENTS="$case_dir/system-events" TEST_UNTRUSTED_EXECUTED="$case_dir/untrusted-executed" \
    TEST_SECRET="$case_dir/secret" \
    TEST_SERVER_BIN="$case_dir/install/factory-server" TEST_INTERRUPT_MARK="$case_dir/interrupted" \
    PATH="$case_dir/bin:$PATH" FACTORY_RELEASE_REPO="$case_dir/repo" \
    FACTORY_SERVER_BIN="$case_dir/install/factory-server" FACTORY_WORKER_BIN="$case_dir/install/factory-worker" \
    FACTORY_RELEASE_DIR="$case_dir/releases" FACTORY_RELEASE_INFO="$case_dir/current.json" \
    FACTORY_RELEASE_LOCK="$case_dir/release.lock" \
    FACTORY_BROWSER_CHECKER="$case_dir/system/browser-checker" \
    FACTORY_BRAIN_INSTALLER="$case_dir/system/brain-installer" \
    FACTORY_JANITOR_BIN="$case_dir/system/janitor" \
    FACTORY_RELEASE_AS='' FACTORY_RELEASE_OWNER='' FACTORY_WORKER_CONFIG="$case_dir/worker.toml" \
    FACTORY_API_URL=http://test FACTORY_REGISTER_ATTEMPTS=2 FACTORY_REGISTER_DELAY=0 \
    /bin/bash "$RELEASE" main >"$case_dir/output" 2>&1
}

success="$temporary/success"
make_fixture "$success" success
run_release "$success" success || fail "successful release failed"
diff -u <(printf '%s\n' \
  'npm ci --no-audit --no-fund --silent' 'npx tsc -p tsconfig.app.json --noEmit' 'npm test' \
  'go test ./...' 'bash ops/test-fx-factory-release-dispatch.sh' \
  'bash ops/test-bootstrap-factory-release.sh' 'bash ops/test-install-server-browser.sh' \
  'bash ops/test-fx-browser-sandbox.sh' \
  'bash ops/test-install-brain.sh' 'bash ops/test-fx-factory-release.sh' 'npx vite build' \
  'go build -o PLACEHOLDER ./cmd/factory-server' 'go build -o PLACEHOLDER ./cmd/factory-worker') \
  <(sed -e 's|-o [^ ]*/factory-server|-o PLACEHOLDER|' \
    -e 's|-o [^ ]*/factory-worker|-o PLACEHOLDER|' "$success/gates") >/dev/null \
  || fail "release gates ran in the wrong order"
assert_file "$success/install/factory-server" '#!/bin/bash'
assert_file "$success/install/factory-worker" '#!/bin/bash'
grep -F "browser-chain worker=$success/install/factory-worker" "$success/system-events" >/dev/null \
  || fail "installed worker/browser chain was not checked"
grep -F 'brain-installer source=' "$success/system-events" >/dev/null \
  || fail "trusted brain installer was not used"
grep -F 'brain-source-parent-mode=700' "$success/system-events" >/dev/null \
  || fail "brain snapshot parent is not closed with mode 0700"
grep -F 'brain-context=committed context' "$success/system-events" >/dev/null \
  || fail "brain installer did not read the exact commit snapshot"
! grep -F "brain-installer source=$success/releases/" "$success/system-events" >/dev/null \
  || fail "brain installer received the factory-owned build checkout"
grep -F '# committed janitor' "$success/system/janitor" >/dev/null \
  || fail "janitor was not installed from the exact commit snapshot"
[ ! -e "$success/untrusted-executed" ] || fail "candidate checkout ops file ran as root"
assert_trusted_unchanged "$success"
grep -F 'выкачено:' "$success/output" >/dev/null || fail "release did not report success"
grep -F 'Проверочный релиз' "$success/output" >/dev/null \
  || fail "release did not explain the deployed change"
! grep -F '1234567890abcdef' "$success/output" >/dev/null \
  || fail "release exposed a bare technical version in owner-facing output"
[ "$(sed -n '1p' "$success/events")" = 'restart factory-server.service' ] \
  || fail "server was not restarted first"
[ "$(sed -n '2p' "$success/events")" = 'stop factory-worker.service' ] \
  || fail "worker was not stopped before determining its identity"
[ "$(sed -n '3p' "$success/events")" = 'start factory-worker.service' ] \
  || fail "worker was not started after taking the heartbeat baseline"
grep -E 'backup=/tmp/factory-release-backup-.+/factory-server.prev mode=700' \
  "$success/backup-events" >/dev/null || fail "release rollback backup is not closed with mode 0700"
while read -r entry _; do
  backup_path=${entry#backup=}
  [ ! -e "$(dirname "$backup_path")" ] || fail "release rollback backup was not removed"
done <"$success/backup-events"

mutated="$temporary/checkout-mutated"
make_fixture "$mutated" checkout-mutated
run_release "$mutated" checkout-mutated || fail "release with a post-build checkout mutation failed"
grep -F 'brain-context=committed context' "$mutated/system-events" >/dev/null \
  || fail "post-build checkout mutation reached the root brain installer"
! grep -F 'brain-context=mutated after build' "$mutated/system-events" >/dev/null \
  || fail "root brain installer followed the mutable build checkout"
grep -F '# committed janitor' "$mutated/system/janitor" >/dev/null \
  || fail "post-build checkout mutation reached the root janitor install"

symlinked="$temporary/snapshot-symlink"
make_fixture "$symlinked" snapshot-symlink
run_release "$symlinked" snapshot-symlink || fail "safe rejection of a snapshot symlink failed the binary release"
! grep -F 'brain-installer source=' "$symlinked/system-events" >/dev/null \
  || fail "root brain installer received a snapshot containing a symlink"
! grep -F 'root-only secret' "$symlinked/system-events" >/dev/null \
  || fail "root brain installer followed a candidate symlink"
grep -F 'снимок выпуска содержит симлинк: pilot/context.md' "$symlinked/output" >/dev/null \
  || fail "release did not explain why the root snapshot was rejected"
assert_file "$symlinked/system/janitor" 'old janitor'

destination_symlink="$temporary/destination-symlink"
make_fixture "$destination_symlink" success
printf 'do not overwrite\n' >"$destination_symlink/destination-secret"
rm "$destination_symlink/install/factory-server"
ln -s "$destination_symlink/destination-secret" "$destination_symlink/install/factory-server"
if run_release "$destination_symlink" success; then
  fail "release accepted a server destination symlink"
fi
assert_file "$destination_symlink/destination-secret" 'do not overwrite'
[ ! -s "$destination_symlink/events" ] || fail "destination symlink changed services"
grep -F 'не являются обычными файлами' "$destination_symlink/output" >/dev/null \
  || fail "release did not explain the unsafe destination"

for mode in server-fail worker-fail stale-healthy-worker heartbeat-during-stop worker-install-fail interrupt-between-install browser-chain-fail; do
  failed="$temporary/$mode"
  make_fixture "$failed" "$mode"
  if run_release "$failed" "$mode"; then fail "$mode unexpectedly succeeded"; fi
  assert_file "$failed/install/factory-server" old-server
  assert_file "$failed/install/factory-worker" old-worker
  assert_trusted_unchanged "$failed"
  [ ! -e "$failed/untrusted-executed" ] || fail "$mode executed candidate checkout ops"
done

missing_transition="$temporary/missing-transition"
make_fixture "$missing_transition" success
rm -f "$missing_transition/system/browser-checker"
if run_release "$missing_transition" success; then fail "release without trusted transition succeeded"; fi
assert_file "$missing_transition/install/factory-server" old-server
assert_file "$missing_transition/install/factory-worker" old-worker
[ ! -s "$missing_transition/events" ] || fail "services changed before trusted transition"

build_failed="$temporary/worker-build-fail"
make_fixture "$build_failed" worker-build-fail
if run_release "$build_failed" worker-build-fail; then fail "worker build unexpectedly succeeded"; fi
assert_file "$build_failed/install/factory-server" old-server
assert_file "$build_failed/install/factory-worker" old-worker

for mode in ui-test-fail go-test-fail release-test-fail; do
  gate_failed="$temporary/$mode"
  make_fixture "$gate_failed" "$mode"
  set +e; run_release "$gate_failed" "$mode"; status=$?; set -e
  [ "$status" -eq 5 ] || fail "$mode returned $status instead of build error 5"
  assert_file "$gate_failed/install/factory-server" old-server
  assert_file "$gate_failed/install/factory-worker" old-worker
  ! grep -F 'go build ' "$gate_failed/gates" >/dev/null || fail "binaries were built after $mode"
done

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

echo "PASS: штатный выпуск не исполняет checkout от root и проверяет browser cleanup"
