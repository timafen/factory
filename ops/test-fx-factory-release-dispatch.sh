#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
RELEASE="$SCRIPT_DIR/fx-factory-release"
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT
mkdir -p "$temporary/bin" "$temporary/releases"

fail() { echo "FAIL: $*" >&2; exit 1; }

cat >"$temporary/bin/git" <<'GIT'
#!/bin/bash
case "$*" in
  *'clone --quiet'*)
    destination=${@: -1}
    mkdir -p "$destination/ops"
    if [ "$TEST_DISPATCH_MODE" = invalid-helper ]; then
      printf '#!/bin/bash\nif broken\n' >"$destination/ops/fx-factory-release"
    else
      cat >"$destination/ops/fx-factory-release" <<'HELPER'
#!/bin/bash
printf 'arg=%s\ncandidate=%s\nrequested=%s\nbootstrap=%s\ntrusted=%s\n' \
  "$1" "$FACTORY_RELEASE_CANDIDATE" "$FACTORY_RELEASE_REQUESTED_REF" \
  "$FACTORY_RELEASE_BOOTSTRAP_DIR" "$FACTORY_RELEASE_TRUSTED_DIR" >"$TEST_DISPATCH_RESULT"
HELPER
    fi
    chmod 755 "$destination/ops/fx-factory-release"
    ;;
  *'checkout --quiet'*) [ "$TEST_DISPATCH_MODE" != missing-ref ] ;;
  *'rev-parse HEAD'*) printf '%s\n' 1234567890abcdef1234567890abcdef12345678 ;;
esac
GIT
chmod 755 "$temporary/bin/git"

run_dispatch() {
  local mode=$1
  TEST_DISPATCH_MODE="$mode" TEST_DISPATCH_RESULT="$temporary/result" \
    PATH="$temporary/bin:$PATH" FACTORY_RELEASE_REPO=test-repo \
    FACTORY_RELEASE_DIR="$temporary/releases" FACTORY_RELEASE_AS='' \
    FACTORY_RELEASE_OWNER='' bash "$RELEASE" candidate-branch \
    >"$temporary/$mode.output" 2>&1
}

run_dispatch success || fail "candidate dispatch failed"
grep -Fx 'arg=1234567890abcdef1234567890abcdef12345678' "$temporary/result" >/dev/null \
  || fail "candidate helper did not receive the pinned commit"
grep -Fx 'candidate=1' "$temporary/result" >/dev/null || fail "candidate marker missing"
grep -Fx 'requested=candidate-branch' "$temporary/result" >/dev/null \
  || fail "human branch name was not preserved"
bootstrap=$(sed -n 's/^bootstrap=//p' "$temporary/result")
case "$bootstrap" in "$temporary/releases"/bootstrap-*) ;; *) fail "unexpected bootstrap path" ;; esac
trusted=$(sed -n 's/^trusted=//p' "$temporary/result")
case "$trusted" in /tmp/factory-release-helper-*) ;; *) fail "unexpected trusted helper path" ;; esac
[ ! -e "$bootstrap" ] || fail "candidate checkout was not cleaned up"
[ ! -e "$trusted" ] || fail "trusted helper copy was not cleaned up"

set +e
run_dispatch invalid-helper
invalid_status=$?
run_dispatch missing-ref
missing_status=$?
set -e
[ "$invalid_status" -eq 5 ] || fail "invalid helper returned $invalid_status instead of 5"
[ "$missing_status" -eq 4 ] || fail "missing ref returned $missing_status instead of 4"

echo "PASS: установленный helper передаёт выпуск точной проверенной ревизии кандидата"
