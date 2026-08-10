#!/bin/bash
# Root integration check: only the allowlist proxy is reachable from the
# browser namespace; direct TCP, UDP and DNS packets must fail.
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "browser-sandbox check requires root" >&2; exit 3; }
launcher=${FACTORY_BROWSER_LAUNCHER:-/usr/local/libexec/factory-browser-sandbox}
[ -x "$launcher" ] || { echo "browser-sandbox launcher is not installed" >&2; exit 3; }

temporary=$(mktemp -d)
server_pid=
cleanup() {
  [ -z "$server_pid" ] || kill "$server_pid" >/dev/null 2>&1 || true
  rm -rf "$temporary"
}
trap cleanup EXIT HUP INT TERM
chmod 755 "$temporary"

cat >"$temporary/proxy.py" <<'PY'
import socket, sys
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("0.0.0.0", 0))
open(sys.argv[1], "w").write(str(s.getsockname()[1]))
s.listen()
while True:
    connection, _ = s.accept()
    connection.close()
PY
chmod 755 "$temporary/proxy.py"
python3 "$temporary/proxy.py" "$temporary/port" &
server_pid=$!
for _ in $(seq 1 50); do [ -s "$temporary/port" ] && break; sleep 0.02; done
[ -s "$temporary/port" ] || { echo "could not start check proxy" >&2; exit 4; }
proxy_port=$(cat "$temporary/port")

cat >"$temporary/probe.py" <<'PY'
#!/usr/bin/python3
import socket, sys, urllib.parse

proxy = next(value.split("=", 1)[1] for value in sys.argv[1:] if value.startswith("--proxy-server="))
parsed = urllib.parse.urlparse(proxy)
allowed = socket.create_connection((parsed.hostname, parsed.port), timeout=1)
allowed.close()

def blocked(socktype, port, label):
    sock = socket.socket(socket.AF_INET, socktype)
    sock.settimeout(0.25)
    try:
        if socktype == socket.SOCK_STREAM:
            sock.connect(("1.1.1.1", port))
        else:
            sock.sendto(b"\0factory-egress-check", ("1.1.1.1", port))
            sock.recvfrom(1)
    except (OSError, TimeoutError):
        return
    finally:
        sock.close()
    raise SystemExit(label + " direct egress unexpectedly succeeded")

blocked(socket.SOCK_STREAM, 443, "TCP")
blocked(socket.SOCK_DGRAM, 443, "UDP")
blocked(socket.SOCK_DGRAM, 53, "DNS")
print("PASS: proxy allowed; direct TCP, UDP and DNS denied")
PY
chmod 755 "$temporary/probe.py"

FACTORY_BROWSER_USER=${FACTORY_BROWSER_USER:-factory} \
  "$launcher" run "--proxy-port=$proxy_port" -- "$temporary/probe.py"
