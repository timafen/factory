#!/bin/bash
set -euo pipefail

fail() { echo "FAIL: $*" >&2; exit 1; }

if [ ! -d /run/systemd/system ] || ! systemctl show-environment >/dev/null 2>&1; then
  [ "${CI:-}" != true ] || fail "real systemd is required in CI"
  echo "SKIP: systemd is not PID 1 in this development environment"
  exit 0
fi
if [ "$(id -u)" -ne 0 ]; then
  [ "${CI:-}" != true ] || fail "root is required for the cgroup fixture in CI"
  echo "SKIP: cgroup fixture requires root"
  exit 0
fi

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
temporary=$(mktemp -d)
unit="factory-release-broker-cgroup-$RANDOM-$$.service"
socket="$temporary/broker.sock"
state_dir="$temporary/state"
operation_id=systemd-cgroup-interruption
state_file="$state_dir/$operation_id.json"
broker="$temporary/factory-release-broker"
driver="$temporary/factory-release-driver"
driver_pids="$temporary/driver-pids"

cleanup() {
  systemctl stop "$unit" >/dev/null 2>&1 || true
  systemctl reset-failed "$unit" >/dev/null 2>&1 || true
  rm -rf -- "$temporary"
}
trap cleanup EXIT

wait_for_socket() {
  local broker_pid
  for _ in $(seq 1 100); do
    if [ -S "$socket" ] && curl --silent --output /dev/null --unix-socket "$socket" http://localhost/; then
      return
    fi
    broker_pid=$(systemctl show -p MainPID --value "$unit" 2>/dev/null || true)
    [ "${broker_pid:-0}" -gt 0 ] 2>/dev/null || fail "broker service stopped before opening its socket"
    sleep 0.05
  done
  fail "broker service did not open its socket"
}

wait_for_running_operation() {
  for _ in $(seq 1 100); do
    if [ -s "$state_file" ] && grep -Fq '"status":"running"' "$state_file" && [ -s "$driver_pids" ]; then
      return
    fi
    sleep 0.05
  done
  fail "real driver did not reach the durable running state"
}

assert_terminal_failed() {
  local response
  response=$(curl --fail --silent --show-error --unix-socket "$socket" \
    "http://localhost/v1/operations/$operation_id") \
    || fail "restarted broker did not return the saved operation"
  [ "$response" = '{"status":"failed"}' ] \
    || fail "restarted broker returned $response instead of terminal failed"
}

go build -C "$root" -o "$broker" ./cmd/factory-release-broker
cat >"$driver" <<EOF
#!/bin/bash
set -eu
printf '%s\n' "\$\$" >>"$driver_pids"
while :; do sleep 1; done
EOF
chmod 755 "$driver"
mkdir -p "$state_dir"

# This is an isolated real service. KillMode=control-group and SIGKILL make
# systemctl stop kill both the broker and its release-driver child in the same
# cgroup, exactly at the boundary which previously left an operation running.
systemd-run --quiet --unit "$unit" \
  --property=Type=simple \
  --property=KillMode=control-group \
  --property=KillSignal=SIGKILL \
  --property=Restart=no \
  "$broker" -socket "$socket" -state-dir "$state_dir" \
    -factory-release-executable "$driver"
wait_for_socket

response=$(curl --fail --silent --show-error --unix-socket "$socket" \
  -H 'Content-Type: application/json' \
  --data '{"operation_id":"systemd-cgroup-interruption","adapter":"fx-factory-release","commit_sha":"0123456789abcdef0123456789abcdef01234567"}' \
  http://localhost/v1/operations)
[ "$response" = '{"status":"launching"}' ] \
  || fail "broker did not accept the real driver: $response"
wait_for_running_operation

broker_pid=$(systemctl show -p MainPID --value "$unit")
driver_pid=$(tail -n 1 "$driver_pids")
control_group=$(systemctl show -p ControlGroup --value "$unit")
[ "$(awk -F: '$1 == "0" { print $3 }' "/proc/$broker_pid/cgroup")" = "$control_group" ] \
  || fail "broker is not in the transient service cgroup"
[ "$(awk -F: '$1 == "0" { print $3 }' "/proc/$driver_pid/cgroup")" = "$control_group" ] \
  || fail "driver is not in the broker service cgroup"

systemctl stop "$unit"
kill -0 "$broker_pid" 2>/dev/null && fail "KillMode=control-group left broker alive"
kill -0 "$driver_pid" 2>/dev/null && fail "KillMode=control-group left driver alive"
grep -Fq '"status":"running"' "$state_file" \
  || fail "fixture did not interrupt the operation at its durable running boundary"

systemctl start "$unit"
wait_for_socket
assert_terminal_failed
[ "$(wc -l <"$driver_pids")" -eq 1 ] \
  || fail "broker re-executed the interrupted physical release"

# A second restart proves that failed is stored, rather than synthesized only
# in memory by the first recovery process.
systemctl restart "$unit"
wait_for_socket
assert_terminal_failed
[ "$(wc -l <"$driver_pids")" -eq 1 ] \
  || fail "saved terminal status caused a second physical release"

echo "PASS: real systemd cgroup killed broker and driver; two restarts kept one terminal failed result"
