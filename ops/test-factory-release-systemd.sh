#!/bin/bash
set -euo pipefail

fail() { echo "FAIL: $*" >&2; exit 1; }

if [ ! -d /run/systemd/system ] || ! systemctl show-environment >/dev/null 2>&1; then
  [ "${CI:-}" != true ] || fail "systemd fixture is required in CI"
  echo "SKIP: systemd is not PID 1 in this development environment"
  exit 0
fi
[ "$(id -u)" -eq 0 ] || { [ "${CI:-}" != true ] || fail "systemd fixture requires root in CI"; echo "SKIP: systemd fixture requires root"; exit 0; }

temporary=$(mktemp -d)
unit="factory-release-deleted-$RANDOM.service"
cleanup() {
  systemctl stop "$unit" >/dev/null 2>&1 || true
  systemctl reset-failed "$unit" >/dev/null 2>&1 || true
  rm -rf "$temporary"
}
trap cleanup EXIT

cp /bin/sleep "$temporary/factory-worker"
chmod 755 "$temporary/factory-worker"
systemd-run --unit "$unit" --property=Type=simple "$temporary/factory-worker" 300 >/dev/null
for _ in $(seq 1 100); do
  pid=$(systemctl show -p MainPID --value "$unit")
  [ "${pid:-0}" -gt 0 ] 2>/dev/null && break
  sleep 0.05
done
[ "${pid:-0}" -gt 0 ] 2>/dev/null || fail "transient unit has no MainPID"
exe_before=$(readlink "/proc/$pid/exe")
[ "$exe_before" = "$temporary/factory-worker" ] || fail "MainPID executable does not match ExecStart"

mv "$temporary/factory-worker" "$temporary/factory-worker.replaced"
cp /bin/true "$temporary/factory-worker"
chmod 755 "$temporary/factory-worker"
exe_after=$(readlink "/proc/$pid/exe")
case "$exe_after" in
  *' (deleted)') ;;
  *) fail "replaced executable was not exposed as deleted inode: $exe_after" ;;
esac
[ "$(sha256sum "$temporary/factory-worker" | awk '{print $1}')" != \
  "$(sha256sum "/proc/$pid/exe" | awk '{print $1}')" ] \
  || fail "replacement unexpectedly has the running process hash"

echo "PASS: real systemd MainPID exposes deleted inode and mismatched installed hash"
