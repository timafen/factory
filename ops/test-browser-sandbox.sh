#!/bin/bash
# Root integration check: only the allowlist proxy is reachable from the
# browser namespace; firewall counters must observe denied TCP, UDP and DNS.
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "browser-sandbox check requires root" >&2; exit 3; }
launcher=${FACTORY_BROWSER_LAUNCHER:-/usr/local/libexec/factory-browser-sandbox}
[ -x "$launcher" ] || { echo "browser-sandbox launcher is not installed" >&2; exit 3; }

temporary=$(mktemp -d)
server_pid=
cancel_launcher_pid=
cleanup() {
  [ -z "$cancel_launcher_pid" ] || kill -KILL "$cancel_launcher_pid" >/dev/null 2>&1 || true
  [ -z "$server_pid" ] || kill "$server_pid" >/dev/null 2>&1 || true
  rm -rf "$temporary"
}
trap cleanup EXIT HUP INT TERM
chmod 755 "$temporary"

cat >"$temporary/proxy.py" <<'PY'
import errno, socket, sys, time
address, port_file = sys.argv[1:]
reservation = socket.socket()
reservation.bind(("127.0.0.1", 0))
port = reservation.getsockname()[1]
reservation.close()
open(port_file, "w").write(str(port))
while True:
    s = socket.socket()
    try:
        s.bind((address, port))
        break
    except OSError as error:
        s.close()
        if error.errno != errno.EADDRNOTAVAIL:
            raise
        time.sleep(.02)
s.listen()
while True:
    connection, _ = s.accept()
    connection.close()
PY
chmod 755 "$temporary/proxy.py"
proxy_address=169.254.254.1
python3 "$temporary/proxy.py" "$proxy_address" "$temporary/port" &
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

def attempt(socktype, port):
    sock = socket.socket(socket.AF_INET, socktype)
    sock.settimeout(0.25)
    try:
        if socktype == socket.SOCK_STREAM:
            sock.connect(("1.1.1.1", port))
        else:
            sock.sendto(b"\0factory-egress-check", ("1.1.1.1", port))
    except (OSError, TimeoutError):
        pass
    finally:
        sock.close()

attempt(socket.SOCK_STREAM, 443)
attempt(socket.SOCK_DGRAM, 443)
attempt(socket.SOCK_DGRAM, 53)
PY
chmod 755 "$temporary/probe.py"

result=$(FACTORY_BROWSER_USER=${FACTORY_BROWSER_USER:-factory} \
  "$launcher" run "--proxy-address=$proxy_address" "--proxy-port=$proxy_port" -- "$temporary/probe.py" 2>&1)
printf '%s\n' "$result"
denied=$(printf '%s\n' "$result" | sed -n 's/^FACTORY_BROWSER_DENIED_PACKETS=//p' | tail -1)
case "$denied" in ''|*[!0-9]*) echo "firewall denial counter is unavailable" >&2; exit 5 ;; esac
[ "$denied" -ge 3 ] || { echo "firewall saw only $denied denied packets, expected TCP, UDP and DNS" >&2; exit 5; }
echo "PASS: proxy allowed; firewall observed direct TCP, UDP and DNS denials ($denied packets)"

: >"$temporary/stubborn.pid"
chmod 666 "$temporary/stubborn.pid"
cat >"$temporary/stubborn.sh" <<'SH'
#!/bin/sh
trap '' TERM
for argument do case "$argument" in *.pid) pid_file=$argument ;; esac; done
printf '%s\n' "$$" >"$pid_file"
while :; do sleep 1; done
SH
chmod 755 "$temporary/stubborn.sh"
FACTORY_BROWSER_USER=${FACTORY_BROWSER_USER:-factory} \
  "$launcher" run "--proxy-address=$proxy_address" "--proxy-port=$proxy_port" -- "$temporary/stubborn.sh" "$temporary/stubborn.pid" \
  >"$temporary/cancel.out" 2>&1 &
cancel_launcher_pid=$!
namespace="factory-browser-$cancel_launcher_pid"
for _ in $(seq 1 100); do [ -s "$temporary/stubborn.pid" ] && break; sleep 0.02; done
[ -s "$temporary/stubborn.pid" ] || { echo "cancellation probe did not start" >&2; exit 6; }
browser_pid=$(cat "$temporary/stubborn.pid")
kill -TERM "$cancel_launcher_pid"
for _ in $(seq 1 100); do
  kill -0 "$cancel_launcher_pid" >/dev/null 2>&1 || break
  sleep 0.02
done
if kill -0 "$cancel_launcher_pid" >/dev/null 2>&1; then
  echo "sandbox launcher survived cancellation" >&2
  exit 6
fi
wait "$cancel_launcher_pid" >/dev/null 2>&1 || true
cancel_launcher_pid=
if kill -0 "$browser_pid" >/dev/null 2>&1; then
  echo "browser process $browser_pid survived cancellation" >&2
  exit 6
fi
if ip netns list | awk '{print $1}' | grep -Fx "$namespace" >/dev/null; then
  echo "network namespace $namespace survived cancellation" >&2
  exit 6
fi
echo "PASS: cancellation removed the browser process group and network namespace"
