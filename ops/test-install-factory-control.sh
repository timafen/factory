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
printf 'old fx\n' >"$target_dir/bin/fx"
printf 'old release\n' >"$target_dir/lib/fx-factory-release"

FACTORY_FX_BIN="$target_dir/bin/fx" \
FACTORY_RELEASE_DRIVER="$target_dir/lib/fx-factory-release" \
FACTORY_GATE_CGROUP_HELPER="$target_dir/libexec/factory-gate-cgroup" \
FACTORY_CONTROL_OWNER='' \
  bash "$INSTALLER" "$source_dir"

cmp -s "$source_dir/ops/fx" "$target_dir/bin/fx" \
  || fail "fx was not updated"
cmp -s "$source_dir/ops/fx-factory-release" "$target_dir/lib/fx-factory-release" \
  || fail "release driver was not updated"
cmp -s "$source_dir/ops/factory-gate-cgroup" "$target_dir/libexec/factory-gate-cgroup" \
  || fail "cgroup helper was not installed during upgrade"
[ -x "$target_dir/bin/fx" ] && [ -x "$target_dir/lib/fx-factory-release" ] \
  && [ -x "$target_dir/libexec/factory-gate-cgroup" ] \
  || fail "installed control tools are not executable"

printf '#!/bin/bash\necho still-valid\n' >"$source_dir/ops/fx"
printf 'not valid shell: (\n' >"$source_dir/ops/fx-factory-release"
cp "$target_dir/bin/fx" "$temporary/fx.before"
cp "$target_dir/lib/fx-factory-release" "$temporary/release.before"
cp "$target_dir/libexec/factory-gate-cgroup" "$temporary/cgroup.before"
if FACTORY_FX_BIN="$target_dir/bin/fx" \
   FACTORY_RELEASE_DRIVER="$target_dir/lib/fx-factory-release" \
   FACTORY_GATE_CGROUP_HELPER="$target_dir/libexec/factory-gate-cgroup" \
   FACTORY_CONTROL_OWNER='' \
     bash "$INSTALLER" "$source_dir" >/dev/null 2>&1; then
  fail "invalid release driver was accepted"
fi
cmp -s "$temporary/fx.before" "$target_dir/bin/fx" \
  || fail "fx changed after a rejected pair"
cmp -s "$temporary/release.before" "$target_dir/lib/fx-factory-release" \
  || fail "release driver changed after a rejected pair"
cmp -s "$temporary/cgroup.before" "$target_dir/libexec/factory-gate-cgroup" \
  || fail "cgroup helper changed after a rejected set"

cp "$SCRIPT_DIR/fx" "$source_dir/ops/fx"
cp "$SCRIPT_DIR/fx-factory-release" "$source_dir/ops/fx-factory-release"
cp "$SCRIPT_DIR/factory-gate-cgroup" "$source_dir/ops/factory-gate-cgroup"
printf 'sentinel fx\n' >"$target_dir/bin/fx"
printf 'sentinel release\n' >"$target_dir/lib/fx-factory-release"
printf 'sentinel cgroup\n' >"$target_dir/libexec/factory-gate-cgroup"
mkdir -p "$temporary/fail-bin"
cat >"$temporary/fail-bin/mv" <<'SH'
#!/bin/bash
target=${@: -1}
if [ "$target" = "$TEST_FAIL_TARGET" ] && [ ! -e "$TEST_FAIL_MARK" ]; then
  : >"$TEST_FAIL_MARK"
  exit 1
fi
exec /bin/mv "$@"
SH
chmod 755 "$temporary/fail-bin/mv"
if PATH="$temporary/fail-bin:$PATH" \
   TEST_FAIL_TARGET="$target_dir/libexec/factory-gate-cgroup" \
   TEST_FAIL_MARK="$temporary/move-failed" \
   FACTORY_FX_BIN="$target_dir/bin/fx" \
   FACTORY_RELEASE_DRIVER="$target_dir/lib/fx-factory-release" \
   FACTORY_GATE_CGROUP_HELPER="$target_dir/libexec/factory-gate-cgroup" \
   FACTORY_CONTROL_OWNER='' \
     bash "$INSTALLER" "$source_dir" >/dev/null 2>&1; then
  fail "partial installation unexpectedly succeeded"
fi
grep -Fx 'sentinel fx' "$target_dir/bin/fx" >/dev/null \
  || fail "fx was not restored after partial installation"
grep -Fx 'sentinel release' "$target_dir/lib/fx-factory-release" >/dev/null \
  || fail "release driver was not restored after partial installation"
grep -Fx 'sentinel cgroup' "$target_dir/libexec/factory-gate-cgroup" >/dev/null \
  || fail "cgroup helper was not restored after partial installation"

echo "PASS: fx, release driver and cgroup helper update atomically"
