#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
INSTALLER=$SCRIPT_DIR/install-factory-control.sh
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

source_dir=$temporary/source
target_dir=$temporary/target
mkdir -p "$source_dir/ops" "$target_dir/bin" "$target_dir/lib" "$target_dir/libexec"
cp "$SCRIPT_DIR/fx" "$source_dir/ops/fx"
cp "$SCRIPT_DIR/fx-factory-release" "$source_dir/ops/fx-factory-release"
cp "$SCRIPT_DIR/factory-gate-cgroup" "$source_dir/ops/factory-gate-cgroup"
cp "$SCRIPT_DIR/factory-cgroup-bootstrap.sh" "$source_dir/ops/factory-cgroup-bootstrap.sh"
printf 'old fx\n' >"$target_dir/bin/fx"
printf 'old release\n' >"$target_dir/lib/fx-factory-release"

FACTORY_FX_BIN="$target_dir/bin/fx" \
FACTORY_RELEASE_DRIVER="$target_dir/lib/fx-factory-release" \
FACTORY_CONTROL_OWNER='' \
  bash "$INSTALLER" "$source_dir"

cmp -s "$source_dir/ops/fx" "$target_dir/bin/fx" \
  || fail "fx was not updated"
cmp -s "$source_dir/ops/fx-factory-release" "$target_dir/lib/fx-factory-release" \
  || fail "release driver was not updated"
[ -x "$target_dir/bin/fx" ] && [ -x "$target_dir/lib/fx-factory-release" ] \
  || fail "installed control tools are not executable"
[ ! -e "$target_dir/libexec/factory-gate-cgroup" ] \
  || fail "ordinary candidate update provisioned a privileged helper"

if [ "$(id -u)" = 0 ]; then
  FACTORY_FX_BIN="$target_dir/bin/fx" \
  FACTORY_RELEASE_DRIVER="$target_dir/lib/fx-factory-release" \
  FACTORY_CONTROL_INSTALLER="$target_dir/libexec/factory-install-control" \
  FACTORY_GATE_CGROUP_HELPER="$target_dir/libexec/factory-gate-cgroup" \
  FACTORY_CGROUP_BOOTSTRAP="$target_dir/libexec/factory-cgroup-bootstrap" \
  FACTORY_CONTROL_OWNER='' FACTORY_CONTROL_BOOTSTRAP=1 \
    bash "$INSTALLER" "$source_dir"
  for installed in factory-install-control factory-gate-cgroup factory-cgroup-bootstrap; do
    [ "$(stat -Lc '%u %a' "$target_dir/libexec/$installed")" = '0 755' ] \
      || fail "$installed is not root-owned mode 755"
  done
  printf '\n# malicious candidate helper\n' >>"$source_dir/ops/factory-gate-cgroup"
  if FACTORY_FX_BIN="$target_dir/bin/fx" FACTORY_RELEASE_DRIVER="$target_dir/lib/fx-factory-release" \
     FACTORY_CONTROL_INSTALLER="$target_dir/libexec/factory-install-control" \
     FACTORY_GATE_CGROUP_HELPER="$target_dir/libexec/factory-gate-cgroup" \
     FACTORY_CGROUP_BOOTSTRAP="$target_dir/libexec/factory-cgroup-bootstrap" \
     FACTORY_CONTROL_OWNER='' FACTORY_CONTROL_BOOTSTRAP=1 \
       bash "$INSTALLER" "$source_dir" >/dev/null 2>&1; then
    fail "altered helper passed the pinned bootstrap hash"
  fi
  ! grep -F 'malicious candidate helper' "$target_dir/libexec/factory-gate-cgroup" >/dev/null \
    || fail "rejected bootstrap replaced the trusted helper"
  cp "$SCRIPT_DIR/factory-gate-cgroup" "$source_dir/ops/factory-gate-cgroup"
else
  if FACTORY_FX_BIN="$target_dir/bin/fx" FACTORY_RELEASE_DRIVER="$target_dir/lib/fx-factory-release" \
     FACTORY_CONTROL_INSTALLER="$target_dir/libexec/factory-install-control" \
     FACTORY_GATE_CGROUP_HELPER="$target_dir/libexec/factory-gate-cgroup" \
     FACTORY_CGROUP_BOOTSTRAP="$target_dir/libexec/factory-cgroup-bootstrap" \
     FACTORY_CONTROL_OWNER='' FACTORY_CONTROL_BOOTSTRAP=1 \
       bash "$INSTALLER" "$source_dir" >"$temporary/bootstrap-output" 2>&1; then
    fail "unprivileged bootstrap unexpectedly succeeded"
  fi
  grep -F 'root is required for control bootstrap' "$temporary/bootstrap-output" >/dev/null \
    || fail "unprivileged bootstrap did not fail clearly"
fi

printf '#!/bin/bash\necho still-valid\n' >"$source_dir/ops/fx"
printf 'not valid shell: (\n' >"$source_dir/ops/fx-factory-release"
cp "$target_dir/bin/fx" "$temporary/fx.before"
cp "$target_dir/lib/fx-factory-release" "$temporary/release.before"
if FACTORY_FX_BIN="$target_dir/bin/fx" \
   FACTORY_RELEASE_DRIVER="$target_dir/lib/fx-factory-release" \
   FACTORY_CONTROL_OWNER='' \
     bash "$INSTALLER" "$source_dir" >/dev/null 2>&1; then
  fail "invalid release driver was accepted"
fi
cmp -s "$temporary/fx.before" "$target_dir/bin/fx" \
  || fail "fx changed after a rejected pair"
cmp -s "$temporary/release.before" "$target_dir/lib/fx-factory-release" \
  || fail "release driver changed after a rejected pair"

echo "PASS: invalid control pair is preserved and helper requires pinned root bootstrap"
