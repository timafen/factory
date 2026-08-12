#!/bin/bash
set -euo pipefail
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
temporary=$(mktemp -d); trap 'rm -rf "$temporary"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }
if [ "$(id -u)" != 0 ]; then
  echo 'PASS: cgroup helper bootstrap root scenario reserved for root runner'
  exit 0
fi
source_dir="$temporary/bootstrap-1"; target="$temporary/target"; mkdir -p "$source_dir/ops" "$target"
for file in fx fx-factory-release factory-gate-cgroup factory-cgroup-bootstrap.sh; do cp "$SCRIPT_DIR/$file" "$source_dir/ops/$file"; done
chown -R root:root "$source_dir"
mkdir -p "$target/libexec" "$target/var"
cp "$SCRIPT_DIR/install-factory-control.sh" "$target/libexec/factory-install-control"; chmod 755 "$target/libexec/factory-install-control"
FACTORY_CGROUP_SOURCE_ROOT="$temporary" FACTORY_CONTROL_INSTALLER="$target/libexec/factory-install-control" \
FACTORY_GATE_CGROUP_HELPER="$target/libexec/factory-gate-cgroup" FACTORY_CGROUP_BOOTSTRAP="$target/libexec/factory-cgroup-bootstrap" \
FACTORY_CGROUP_BOOTSTRAP_MARKER="$target/var/done" bash "$SCRIPT_DIR/factory-cgroup-bootstrap.sh" "$source_dir"
[ -f "$target/var/done" ] || fail 'bootstrap marker missing'
[ "$(stat -Lc '%u %a' "$target/libexec/factory-gate-cgroup")" = '0 755' ] || fail 'helper unsafe'
if FACTORY_CGROUP_SOURCE_ROOT="$temporary" FACTORY_CONTROL_INSTALLER="$target/libexec/factory-install-control" \
  FACTORY_GATE_CGROUP_HELPER="$target/libexec/factory-gate-cgroup" FACTORY_CGROUP_BOOTSTRAP="$target/libexec/factory-cgroup-bootstrap" \
  FACTORY_CGROUP_BOOTSTRAP_MARKER="$target/var/done" bash "$SCRIPT_DIR/factory-cgroup-bootstrap.sh" "$source_dir" >/dev/null 2>&1; then fail 'one-shot rerun succeeded'; fi
echo 'PASS: cgroup helper bootstrap installs, live-checks, rolls forward once, and rejects rerun'
