#!/bin/bash
# Proves that systemd's IPAddress* policy is enforced by the running kernel.
set -euo pipefail

SYSTEMD_RUN=${FACTORY_BROWSER_SYSTEMD_RUN:-systemd-run}
temporary=$(mktemp -d)
server_pid=
cleanup() {
  [ -z "$server_pid" ] || kill "$server_pid" 2>/dev/null || true
  rm -rf "$temporary"
}
trap cleanup EXIT

check_scope_properties() {
  local output status=0
  output=$("$SYSTEMD_RUN" --no-ask-password --scope --quiet --collect --expand-environment=no \
    -p IPAddressDeny=any -p IPAddressAllow=localhost true 2>&1) || status=$?
  if grep -Fq 'Unknown assignment:' <<<"$output"; then
    printf '%s\n' "$output" >&2
    echo "browser firewall uses a property unsupported by transient scopes" >&2
    return 1
  fi
  if [ "$status" -ne 0 ] && ! grep -Eq \
    'Interactive authentication required|Access denied|Failed to connect to bus|System has not been booted with systemd' \
    <<<"$output"; then
    printf '%s\n' "$output" >&2
    echo "cannot validate transient scope properties with systemd-run" >&2
    return 1
  fi
  echo "PASS: systemd-run accepts browser firewall scope properties"
}

if [ "${1:-}" = --check-properties ]; then
  check_scope_properties
  exit
fi

[ "$(id -u)" -eq 0 ] || { echo "browser firewall probe must run as root" >&2; exit 1; }
host_ip=$(ip -o route get 1.1.1.1 2>/dev/null | awk '{for (i=1;i<=NF;i++) if ($i=="src") {print $(i+1); exit}}')
[ -n "$host_ip" ] || { echo "cannot find a non-loopback address for browser firewall probe" >&2; exit 1; }

python3 - "$temporary/port" <<'PY' &
import socket, sys
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("0.0.0.0", 0))
s.listen()
open(sys.argv[1], "w").write(str(s.getsockname()[1]))
while True:
    connection, _ = s.accept()
    connection.close()
PY
server_pid=$!
for _ in $(seq 1 50); do [ -s "$temporary/port" ] && break; sleep 0.02; done
[ -s "$temporary/port" ] || { echo "browser firewall probe listener did not start" >&2; exit 1; }
port=$(cat "$temporary/port")

# Establish that the non-loopback endpoint is reachable before applying policy.
python3 - "$host_ip" "$port" <<'PY'
import socket, sys
socket.create_connection((sys.argv[1], int(sys.argv[2])), 2).close()
PY

cat >"$temporary/probe.py" <<'PY'
import socket, sys
port = int(sys.argv[2])
socket.create_connection(("127.0.0.1", port), 2).close()
try:
    socket.create_connection((sys.argv[1], port), 1).close()
except OSError:
    raise SystemExit(0)
raise SystemExit("systemd IPAddressDeny=any did not block the host address")
PY

"$SYSTEMD_RUN" --scope --collect --quiet \
  -p IPAddressDeny=any -p IPAddressAllow=localhost \
  python3 "$temporary/probe.py" "$host_ip" "$port"

# The same assertion must fail without IPAddress* properties. Besides proving
# the endpoint remains reachable, this makes the smoke sensitive to a runner
# that accepts but silently ignores the firewall properties.
control_status=0
"$SYSTEMD_RUN" --scope --collect --quiet \
  python3 "$temporary/probe.py" "$host_ip" "$port" \
  >"$temporary/control-output" 2>&1 || control_status=$?
[ "$control_status" -ne 0 ] \
  || { echo "browser firewall control unexpectedly reported isolation" >&2; exit 1; }
grep -Fq 'systemd IPAddressDeny=any did not block the host address' \
  "$temporary/control-output" \
  || { cat "$temporary/control-output" >&2; echo "browser firewall control did not reach the host address" >&2; exit 1; }

kill "$server_pid"
wait "$server_pid" 2>/dev/null || true
server_pid=
echo "PASS: systemd BPF firewall blocks non-loopback traffic and the unfiltered control reaches it"
