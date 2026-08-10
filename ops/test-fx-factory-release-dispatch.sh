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
    mkdir -p "$destination/ops" "$destination/web"
    cat >"$destination/ops/fx-factory-release" <<'MALICIOUS'
#!/bin/bash
printf 'candidate helper executed as uid=%s\n' "$(id -u)" >"$TEST_DISPATCH_MARK"
MALICIOUS
    chmod 755 "$destination/ops/fx-factory-release"
    ;;
  *'checkout --quiet'*) exit 0 ;;
  *'rev-parse HEAD'*) echo 1234567890abcdef1234567890abcdef12345678 ;;
  *'log -1'*) echo 'Недоверенный кандидат' ;;
esac
GIT
cat >"$temporary/bin/npm" <<'NPM'
#!/bin/bash
exit 9
NPM
chmod 755 "$temporary/bin/git" "$temporary/bin/npm"

set +e
TEST_DISPATCH_MARK="$temporary/candidate-ran" PATH="$temporary/bin:$PATH" \
  FACTORY_RELEASE_REPO=test-repo FACTORY_RELEASE_DIR="$temporary/releases" \
  FACTORY_RELEASE_INFO="$temporary/current.json" FACTORY_RELEASE_LOCK="$temporary/release.lock" \
  FACTORY_RELEASE_AS='' \
  FACTORY_RELEASE_OWNER='' bash "$RELEASE" arbitrary-contributor-branch \
  >"$temporary/output" 2>&1
status=$?
set -e

[ "$status" -eq 4 ] || fail "build gate returned $status instead of 4"
[ ! -e "$temporary/candidate-ran" ] \
  || fail "root release executed fx-factory-release from candidate checkout"
grep -F 'npm ci не прошёл' "$temporary/output" >/dev/null \
  || fail "trusted helper did not continue through its own build gate"

echo "PASS: root-owned release helper never dispatches to a candidate checkout helper"
