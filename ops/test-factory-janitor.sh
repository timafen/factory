#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
TMP=$(mktemp -d)
SERVER_PID=
cleanup() {
  [ -z "$SERVER_PID" ] || kill "$SERVER_PID" 2>/dev/null || true
  rm -rf "$TMP"
}
trap cleanup EXIT

mkdir -p "$TMP/bin" "$TMP/worker/worktrees/retained" "$TMP/worker/repositories/repo" "$TMP/quarantine"
printf 'name = "claude-haiku"\ndata_directory = "%s/worker"\n' "$TMP" >"$TMP/worker.toml"
printf '#!/usr/bin/env bash\ncase "$1" in\n  list-units) echo "factory-claude.service loaded active running" ;;\n  cat) echo "ExecStart=/bin/factory-worker --config %s/worker.toml" ;;\nesac\n' "$TMP" >"$TMP/bin/systemctl"
printf '#!/usr/bin/env bash\nexit 0\n' >"$TMP/bin/sleep"
printf '#!/usr/bin/env bash\nexit 0\n' >"$TMP/bin/su"
chmod +x "$TMP/bin/systemctl" "$TMP/bin/sleep" "$TMP/bin/su"

python3 -c '
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
requests = sys.argv[1]
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = {"workers": [{"id": "worker-1", "name": "claude-haiku", "online": True, "active_count": 0, "health": "unhealthy", "retained_worktrees": [{"attempt_id": "attempt-moved", "repository_id": "repo-1", "path": sys.argv[2], "reason": "failed", "cleanup_command": "cleanup moved"}, {"attempt_id": "attempt-missing", "repository_id": "repo-1", "path": sys.argv[3], "reason": "failed", "cleanup_command": "cleanup missing"}]}]}
        encoded = json.dumps(body).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", len(encoded)); self.end_headers(); self.wfile.write(encoded)
    def do_POST(self):
        size = int(self.headers["Content-Length"])
        open(requests, "wb").write(self.rfile.read(size))
        self.send_response(200); self.end_headers()
    def log_message(self, *args): pass
server = HTTPServer(("127.0.0.1", 0), Handler)
print(server.server_port, flush=True)
server.serve_forever()
' "$TMP/request.json" "$TMP/worker/worktrees/retained" "$TMP/worker/worktrees/missing" >"$TMP/server.log" 2>&1 &
SERVER_PID=$!
for _ in {1..100}; do
  PORT=$(head -1 "$TMP/server.log" || true)
  [ -n "$PORT" ] && break
  command sleep 0.01
done
test -n "$PORT"

PATH="$TMP/bin:$PATH" \
FACTORY_JANITOR_LOG="$TMP/janitor.log" \
FACTORY_JANITOR_STATE="$TMP/state/heals.json" \
FACTORY_JANITOR_QUARANTINE="$TMP/quarantine" \
FACTORY_JANITOR_API="http://127.0.0.1:$PORT/api/v1" \
bash "$ROOT/ops/factory-janitor.sh"

python3 - "$TMP/request.json" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1]))
retained = payload["retained_worktrees"]
assert len(retained) == 1, retained
assert retained[0]["attempt_id"] == "attempt-moved", retained
PY
test ! -e "$TMP/worker/worktrees/retained"
test -e "$TMP/quarantine/worker-retained."* 2>/dev/null
grep -q 'подтверждена очистка retained worktree: claude-haiku' "$TMP/janitor.log"

mkdir -p "$TMP/worker/worktrees/missing"
printf '#!/usr/bin/env bash\necho "confirmation unavailable" >&2\nexit 22\n' >"$TMP/bin/curl"
chmod +x "$TMP/bin/curl"
PATH="$TMP/bin:$PATH" \
FACTORY_JANITOR_LOG="$TMP/janitor.log" \
FACTORY_JANITOR_STATE="$TMP/state/heals.json" \
FACTORY_JANITOR_QUARANTINE="$TMP/quarantine" \
FACTORY_JANITOR_API="http://127.0.0.1:$PORT/api/v1" \
bash "$ROOT/ops/factory-janitor.sh"

test ! -e "$TMP/worker/worktrees/missing"
test -e "$TMP/quarantine/worker-missing."* 2>/dev/null
grep -q 'не удалось подтвердить очистку retained worktree: claude-haiku' "$TMP/janitor.log"

echo 'TestJanitorClearsRetainedWorktreeAfterQuarantine: PASS'
