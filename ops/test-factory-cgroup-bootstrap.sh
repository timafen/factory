#!/bin/bash
set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
fail() { echo "FAIL: $*" >&2; exit 1; }
helper_sha=$(/usr/bin/sha256sum -- "$SCRIPT_DIR/factory-gate-cgroup" | /usr/bin/awk '{print $1}')
bootstrap_sha=$(sed -n 's/^EXPECTED=//p' "$SCRIPT_DIR/factory-cgroup-bootstrap.sh")
installer_sha=$(sed -n 's/^GATE_HELPER_SHA256=//p' "$SCRIPT_DIR/install-factory-control.sh")
release_sha=$(sed -n 's/^TRUSTED_GATE_CGROUP_SHA256=//p' "$SCRIPT_DIR/fx-factory-release")
[ "$bootstrap_sha" = "$helper_sha" ] || fail 'bootstrap helper digest is stale'
[ "$installer_sha" = "$helper_sha" ] || fail 'installer helper digest is stale'
[ "$release_sha" = "$helper_sha" ] || fail 'release helper digest is stale'
if [ "$(id -u)" != 0 ]; then
  echo 'SKIP: cgroup helper bootstrap requires a real root runner with writable cgroup v2'
  exit 0
fi
temporary=$(mktemp -d /run/factory-cgroup-bootstrap-test.XXXXXX); trap 'rm -rf "$temporary"' EXIT
chmod 700 "$temporary"
source_root="$temporary/source"; source_dir="$source_root/bootstrap-1"; target="$temporary/target"
mkdir -m 700 "$source_root" "$source_dir" "$source_dir/ops" "$target" "$target/libexec" "$target/var"
for file in fx fx-factory-release factory-gate-cgroup factory-cgroup-bootstrap.sh; do cp "$SCRIPT_DIR/$file" "$source_dir/ops/$file"; done
chown -R root:root "$temporary"
chmod 755 "$source_dir/ops/"*
cp "$SCRIPT_DIR/install-factory-control.sh" "$target/libexec/factory-install-control"; chmod 755 "$target/libexec/factory-install-control"

run_bootstrap() {
  FACTORY_CGROUP_SOURCE_ROOT="$source_root" FACTORY_CONTROL_INSTALLER="$target/libexec/factory-install-control" \
  FACTORY_GATE_CGROUP_HELPER="$target/libexec/factory-gate-cgroup" FACTORY_CGROUP_BOOTSTRAP="$target/libexec/factory-cgroup-bootstrap" \
  FACTORY_CGROUP_BOOTSTRAP_MARKER="${1:-$target/var/done}" bash "$SCRIPT_DIR/factory-cgroup-bootstrap.sh" "${2:-$source_dir}"
}

if run_bootstrap "$target/var/done" "$source_root/bootstrap-1/../../../tmp" >/dev/null 2>&1; then
  fail 'lexical traversal escaped the trusted source root'
fi
chmod 777 "$source_dir"
if run_bootstrap >/dev/null 2>&1; then fail 'group/world-writable source directory was accepted'; fi
chmod 700 "$source_dir"
chmod 777 "$source_dir/ops/factory-gate-cgroup"
if run_bootstrap >/dev/null 2>&1; then fail 'group/world-writable source file was accepted'; fi
chmod 755 "$source_dir/ops/factory-gate-cgroup"

printf 'old helper\n' >"$target/libexec/factory-gate-cgroup"
printf 'old installer\n' >"$target/libexec/factory-install-control.before"
cp "$target/libexec/factory-install-control" "$target/libexec/factory-install-control.before"
printf 'old bootstrap\n' >"$target/libexec/factory-cgroup-bootstrap"
if run_bootstrap "/proc/factory-cgroup-bootstrap-test-$$" >/dev/null 2>&1; then
  fail 'bootstrap unexpectedly wrote marker in /proc'
fi
grep -Fx 'old helper' "$target/libexec/factory-gate-cgroup" >/dev/null || fail 'helper was not rolled back'
cmp -s "$target/libexec/factory-install-control.before" "$target/libexec/factory-install-control" \
  || fail 'installer was not rolled back'
grep -Fx 'old bootstrap' "$target/libexec/factory-cgroup-bootstrap" >/dev/null || fail 'bootstrap was not rolled back'

run_bootstrap
[ -f "$target/var/done" ] || fail 'bootstrap marker missing'
[ "$(stat -Lc '%u %a' "$target/libexec/factory-gate-cgroup")" = '0 755' ] || fail 'helper unsafe'
if run_bootstrap >/dev/null 2>&1; then fail 'one-shot rerun succeeded'; fi
echo 'PASS: root bootstrap rejects unsafe paths, rolls back failure, installs, probes, and is one-shot'
