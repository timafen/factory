#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
CHECKER="$SCRIPT_DIR/check-codex-auth-permissions.sh"
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
owner=$(id -un)
group=$(id -gn)
secret='oauth-secret-must-not-be-printed'

run_checker() {
  local case_dir=$1 expected_user=${2:-$owner} expected_group=${3:-$group}
  FACTORY_CODEX_DATA_HOME="$case_dir" \
    FACTORY_CODEX_USER="$expected_user" \
    FACTORY_CODEX_GROUP="$expected_group" \
    bash "$CHECKER"
}

assert_no_secret() {
  local output=$1
  ! grep -F "$secret" "$output" >/dev/null \
    || fail "checker printed the OAuth secret"
}

safe="$temporary/safe"
mkdir -p "$safe/.codex" "$safe/.codex-worker"
printf '%s\n' "$secret" >"$safe/.codex/auth.json"
chmod 600 "$safe/.codex/auth.json"
ln -s "$safe/.codex/auth.json" "$safe/.codex-worker/auth.json"
safe_link="$safe/.codex-worker/auth.json"
safe_target="$safe/.codex/auth.json"

# Linux reports the link inode itself as mode 777. The checker must inspect its
# target instead, so this is the regression that fails when -L is removed.
[ "$(stat -c '%a' -- "$safe_link")" = 777 ] \
  || fail "fixture symlink does not expose Linux mode 777"
safe_target_before=$(sha256sum "$safe_target")
safe_mode_before=$(stat -c '%a' -- "$safe_target")
safe_target_link_before=$(readlink -- "$safe_link")
run_checker "$safe" >"$safe/output" 2>&1 \
  || fail "safe target behind a 777 symlink was rejected"
grep -F "$safe_link: regular file 600 $owner $group" "$safe/output" >/dev/null \
  || fail "safe target metadata was not reported"
assert_no_secret "$safe/output"
[ "$(sha256sum "$safe_target")" = "$safe_target_before" ] \
  || fail "safe target contents changed"
[ "$(stat -c '%a' -- "$safe_target")" = "$safe_mode_before" ] \
  || fail "safe target mode changed"
[ "$(readlink -- "$safe_link")" = "$safe_target_link_before" ] \
  || fail "safe link target changed"

expect_rejected() {
  local name=$1 case_dir=$2 expected=$3 expected_user=${4:-$owner}
  local expected_group=${5:-$group} output="$case_dir/output" status=0
  run_checker "$case_dir" "$expected_user" "$expected_group" >"$output" 2>&1 || status=$?
  [ "$status" -ne 0 ] || fail "$name unexpectedly passed"
  grep -F "$expected" "$output" >/dev/null \
    || fail "$name did not report safe metadata"
  assert_no_secret "$output"
}

for mode in 644 660 777; do
  chmod "$mode" "$safe_target"
  expect_rejected "target mode $mode" "$safe" \
    "$safe_link: regular file $mode $owner $group"
done
chmod 600 "$safe_target"

wrong_owner='checker-user-that-cannot-match'
expect_rejected "wrong owner" "$safe" \
  "$safe_link: regular file 600 $owner $group (expected regular file 600 $wrong_owner $group)" \
  "$wrong_owner" "$group"

wrong_group='checker-group-that-cannot-match'
expect_rejected "wrong group" "$safe" \
  "$safe_link: regular file 600 $owner $group (expected regular file 600 $owner $wrong_group)" \
  "$owner" "$wrong_group"

dangling="$temporary/dangling"
mkdir -p "$dangling/.codex-worker"
ln -s "$dangling/missing-auth.json" "$dangling/.codex-worker/auth.json"
expect_rejected "dangling link" "$dangling" \
  "$dangling/.codex-worker/auth.json: target metadata unavailable"

directory="$temporary/directory"
mkdir -p "$directory/.codex-worker" "$directory/auth-target"
ln -s "$directory/auth-target" "$directory/.codex-worker/auth.json"
expect_rejected "directory target" "$directory" \
  "$directory/.codex-worker/auth.json: directory"

nested="$temporary/nested"
mkdir -p "$nested/.codex-worker/nested"
printf '%s\n' "$secret" >"$nested/.codex-worker/nested/target"
chmod 777 "$nested/.codex-worker/nested/target"
ln -s "$nested/.codex-worker/nested/target" \
  "$nested/.codex-worker/nested/auth.json"
run_checker "$nested" >"$nested/output" 2>&1 \
  || fail "nested non-worker path was checked"
[ ! -s "$nested/output" ] || fail "nested path produced a finding"

empty="$temporary/no-workers"
mkdir -p "$empty"
run_checker "$empty" >"$empty/output" 2>&1 \
  || fail "absence of Codex workers was rejected"
[ ! -s "$empty/output" ] || fail "no-worker check produced output"

missing="$temporary/missing-data-home"
run_checker "$missing" >"$missing.output" 2>&1 \
  || fail "missing data home was rejected"
[ ! -s "$missing.output" ] || fail "missing data home produced output"

unreadable="$temporary/unreadable"
mkdir -p "$unreadable/.codex-worker" "$unreadable/shared"
printf '%s\n' "$secret" >"$unreadable/shared/auth.json"
chmod 777 "$unreadable/shared/auth.json"
ln -s "$unreadable/shared/auth.json" "$unreadable/.codex-worker/auth.json"
chmod 000 "$unreadable/.codex-worker"
scan_status=0
run_checker "$unreadable" >"$unreadable.output" 2>&1 || scan_status=$?
chmod 700 "$unreadable/.codex-worker"
[ "$scan_status" -ne 0 ] \
  || fail "unreadable worker directory unexpectedly passed"
grep -F "unable to scan Codex worker directories under $unreadable" \
  "$unreadable.output" >/dev/null \
  || fail "unreadable worker directory did not report scan failure"
assert_no_secret "$unreadable.output"

echo "PASS: Codex auth checker validates link targets without reading or changing secrets"
