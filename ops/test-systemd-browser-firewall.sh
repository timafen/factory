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

[ "$(id -u)" -eq 0 ] || { echo "browser firewall probe must run as root" >&2; exit 1; }
host_ip=$(ip -o route get 1.1.1.1 2>/dev/null | awk '{for (i=1;i<=NF;i++) if ($i=="src") {print $(i+1); exit}}')
[ -n "$host_ip" ] || { echo "cannot find a non-loopback address for browser firewall probe" >&2; exit 1; }

python3 - "$temporary/port" <<'PY' &
import socket, sys
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("0.0.0.0", 0))
s.listen(2)
open(sys.argv[1], "w").write(str(s.getsockname()[1]))
for _ in range(2):
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

"$SYSTEMD_RUN" --scope --collect --quiet \
  -p IPAddressDeny=any -p IPAddressAllow=localhost \
  -p 'RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6' \
  python3 - "$host_ip" "$port" <<'PY'
import socket, sys
port = int(sys.argv[2])
socket.create_connection(("127.0.0.1", port), 2).close()
try:
    socket.create_connection((sys.argv[1], port), 1).close()
except OSError:
    raise SystemExit(0)
raise SystemExit("systemd IPAddressDeny=any did not block the host address")
PY

wait "$server_pid"
server_pid=
echo "PASS: systemd BPF firewall allows loopback and blocks non-loopback traffic"
