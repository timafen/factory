#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
PROVISIONER="$SCRIPT_DIR/provision-codex-auth.sh"
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
owner=$(id -un)
group=$(id -gn)

run_provisioner() {
  case_dir=$1
  shift
  CODEX_HOME= FACTORY_CODEX_DATA_HOME="$case_dir" \
    FACTORY_CODEX_USER="$owner" FACTORY_CODEX_GROUP="$group" \
    bash "$PROVISIONER" "$@"
}

valid="$temporary/valid"
mkdir -p "$valid/.codex" "$valid/.codex-sol-high" "$valid/.codex-terra-low"
printf 'secret-value-must-not-be-logged\n' >"$valid/.codex/auth.json"
chmod 600 "$valid/.codex/auth.json"
ln -s /wrong/target "$valid/.codex-terra-low/auth.json"
run_provisioner "$valid" "$valid/.codex-sol-high" \
  "$valid/.codex-terra-low" >"$valid/output" 2>&1 \
  || fail "valid protected target was rejected"
for home in .codex-sol-high .codex-terra-low; do
  link="$valid/$home/auth.json"
  [ -L "$link" ] || fail "$link is not a symlink"
  [ "$(readlink "$link")" = "$valid/.codex/auth.json" ] \
    || fail "$link does not point to the shared target"
  [ "$(stat -c '%U:%G' "$link")" = "$owner:$group" ] \
    || fail "$link has the wrong owner"
  cmp -s "$link" "$valid/.codex/auth.json" \
    || fail "$link cannot read the shared auth file"
done
! grep -F 'secret-value-must-not-be-logged' "$valid/output" >/dev/null \
  || fail "provisioner printed auth contents"

discovery="$temporary/discovery"
mkdir -p "$discovery/.codex" "$discovery/.codex-medium" \
  "$discovery/.codex-auth-backup"
printf 'another-secret\n' >"$discovery/.codex/auth.json"
chmod 600 "$discovery/.codex/auth.json"
ln -s /wrong/target "$discovery/.codex-medium/auth.json"
run_provisioner "$discovery" >"$discovery/output" 2>&1 \
  || fail "existing auth link discovery failed"
[ "$(readlink "$discovery/.codex-medium/auth.json")" = \
  "$discovery/.codex/auth.json" ] || fail "discovered link was not updated"
[ ! -e "$discovery/.codex-auth-backup/auth.json" ] \
  || fail "discovery created an auth link in an unrelated directory"

no_workers="$temporary/no-workers"
mkdir -p "$no_workers"
run_provisioner "$no_workers" >"$no_workers/output" 2>&1 \
  || fail "installation without Codex workers was rejected"
[ ! -s "$no_workers/output" ] || fail "no-op provisioning produced output"

assert_rejected_without_link_change() {
  name=$1
  expected=$2
  setup=$3
  case_dir="$temporary/$name"
  mkdir -p "$case_dir/.codex" "$case_dir/.codex-low"
  ln -s /must/remain "$case_dir/.codex-low/auth.json"
  "$setup" "$case_dir/.codex/auth.json"
  status=0
  run_provisioner "$case_dir" "$case_dir/.codex-low" \
    >"$case_dir/output" 2>&1 || status=$?
  [ "$status" -ne 0 ] || fail "$name target unexpectedly passed"
  grep -F "$expected" "$case_dir/output" >/dev/null \
    || fail "$name did not explain the rejected metadata"
  [ "$(readlink "$case_dir/.codex-low/auth.json")" = /must/remain ] \
    || fail "$name changed a link before validation completed"
}

make_missing() { :; }
make_directory() { mkdir "$1"; }
make_symlink() { ln -s /dev/null "$1"; }
make_open_mode() { printf x >"$1"; chmod 644 "$1"; }
make_wrong_owner() { printf x >"$1"; chmod 600 "$1"; }
make_wrong_group() { printf x >"$1"; chmod 600 "$1"; }

assert_rejected_without_link_change missing 'is missing' make_missing
assert_rejected_without_link_change directory 'is not a regular file' make_directory
assert_rejected_without_link_change symlink 'must be a regular file, not a symlink' make_symlink
assert_rejected_without_link_change mode 'must have mode 600' make_open_mode

wrong_owner="$temporary/wrong-owner"
mkdir -p "$wrong_owner/.codex" "$wrong_owner/.codex-low"
printf x >"$wrong_owner/.codex/auth.json"
chmod 600 "$wrong_owner/.codex/auth.json"
status=0
FACTORY_CODEX_DATA_HOME="$wrong_owner" FACTORY_CODEX_USER=root \
  FACTORY_CODEX_GROUP="$group" bash "$PROVISIONER" "$wrong_owner/.codex-low" \
  >"$wrong_owner/output" 2>&1 || status=$?
[ "$status" -ne 0 ] || fail "wrong owner unexpectedly passed"
grep -F 'must be owned by root' "$wrong_owner/output" >/dev/null \
  || fail "wrong owner was not diagnosed"

wrong_group="$temporary/wrong-group"
mkdir -p "$wrong_group/.codex" "$wrong_group/.codex-low"
printf x >"$wrong_group/.codex/auth.json"
chmod 600 "$wrong_group/.codex/auth.json"
status=0
FACTORY_CODEX_DATA_HOME="$wrong_group" FACTORY_CODEX_USER="$owner" \
  FACTORY_CODEX_GROUP=root bash "$PROVISIONER" "$wrong_group/.codex-low" \
  >"$wrong_group/output" 2>&1 || status=$?
[ "$status" -ne 0 ] || fail "wrong group unexpectedly passed"
grep -F 'must belong to group root' "$wrong_group/output" >/dev/null \
  || fail "wrong group was not diagnosed"

regular_link="$temporary/regular-link"
mkdir -p "$regular_link/.codex" "$regular_link/.codex-high"
printf secret >"$regular_link/.codex/auth.json"
chmod 600 "$regular_link/.codex/auth.json"
printf local-copy >"$regular_link/.codex-high/auth.json"
status=0
run_provisioner "$regular_link" "$regular_link/.codex-high" \
  >"$regular_link/output" 2>&1 || status=$?
[ "$status" -ne 0 ] || fail "an existing auth copy was overwritten"
grep -Fx local-copy "$regular_link/.codex-high/auth.json" >/dev/null \
  || fail "existing auth copy was changed"

rollback="$temporary/rollback"
mkdir -p "$rollback/.codex" "$rollback/.codex-first" \
  "$rollback/.codex-second" "$rollback/bin"
printf secret >"$rollback/.codex/auth.json"
chmod 600 "$rollback/.codex/auth.json"
ln -s /original/first "$rollback/.codex-first/auth.json"
ln -s /original/second "$rollback/.codex-second/auth.json"
first_target=$(readlink "$rollback/.codex-first/auth.json")
first_owner=$(stat -c '%U:%G' "$rollback/.codex-first/auth.json")
first_inode=$(stat -c '%i' "$rollback/.codex-first/auth.json")
second_target=$(readlink "$rollback/.codex-second/auth.json")
second_owner=$(stat -c '%U:%G' "$rollback/.codex-second/auth.json")
second_inode=$(stat -c '%i' "$rollback/.codex-second/auth.json")
real_mv=$(command -v mv)
printf '%s\n' \
  '#!/bin/bash' \
  'if [[ $1 = -Tf && $2 = -- && $4 = */auth.json && $3 = */.auth.json.provision.* ]]; then' \
  '  count=0' \
  "  [ ! -f '$rollback/mv-count' ] || count=\$(<'$rollback/mv-count')" \
  '  count=$((count + 1))' \
  "  printf '%s\\n' \"\$count\" >'$rollback/mv-count'" \
  '  [ "$count" -ne 2 ] || exit 1' \
  'fi' \
  "exec '$real_mv' \"\$@\"" \
  >"$rollback/bin/mv"
chmod +x "$rollback/bin/mv"
status=0
PATH="$rollback/bin:$PATH" run_provisioner "$rollback" \
  "$rollback/.codex-first" "$rollback/.codex-second" \
  >"$rollback/output" 2>&1 || status=$?
[ "$status" -ne 0 ] || fail "failure while installing the second link passed"
grep -F 'previous links restored' "$rollback/output" >/dev/null \
  || fail "second-link failure did not report rollback"
[ "$(readlink "$rollback/.codex-first/auth.json")" = "$first_target" ] \
  || fail "first link was not restored after second-link failure"
[ "$(stat -c '%U:%G' "$rollback/.codex-first/auth.json")" = "$first_owner" ] \
  || fail "first link owner changed during rollback"
[ "$(stat -c '%i' "$rollback/.codex-first/auth.json")" = "$first_inode" ] \
  || fail "first link inode changed during rollback"
[ "$(readlink "$rollback/.codex-second/auth.json")" = "$second_target" ] \
  || fail "second link changed despite its failed installation"
[ "$(stat -c '%U:%G' "$rollback/.codex-second/auth.json")" = "$second_owner" ] \
  || fail "second link owner changed during rollback"
[ "$(stat -c '%i' "$rollback/.codex-second/auth.json")" = "$second_inode" ] \
  || fail "second link inode changed during rollback"

echo "PASS: Codex auth links are owned by the worker and unsafe targets fail closed"
