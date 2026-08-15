#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
TMP=$(mktemp -d)
SERVER_PID=
export FACTORY_JANITOR_CACHE_ROOT="$TMP/cache"
export FACTORY_JANITOR_BROWSER_ROOT="$TMP/cache/ms-playwright"
export FACTORY_JANITOR_RELEASES_ROOT="$TMP/releases"
export FACTORY_JANITOR_MANIFEST="$TMP/state/candidates.json"
export FACTORY_JANITOR_LOCK="$TMP/janitor.lock"
cleanup() {
  [ -z "$SERVER_PID" ] || kill "$SERVER_PID" 2>/dev/null || true
  rm -rf "$TMP"
}
trap cleanup EXIT

mkdir -p "$TMP/bin" \
  "$TMP/worker/worktrees/retained" "$TMP/worker/worktrees/unmoved" "$TMP/worker/repositories/repo" \
  "$TMP/unhealthy/worktrees/current" "$TMP/unhealthy/repositories/repo" \
  "$TMP/unhealthy-retained/worktrees/retained" "$TMP/unhealthy-retained/repositories/repo" \
  "$TMP/healthy/worktrees/retained" "$TMP/healthy/repositories/repo" \
  "$TMP/active/worktrees/current" "$TMP/active/repositories/repo" \
  "$TMP/quarantine" "$TMP/cache/ms-playwright" "$TMP/releases"
printf 'name = "claude-haiku"\ndata_directory = "%s/worker"\n' "$TMP" >"$TMP/worker.toml"
printf 'name = "online-unhealthy"\ndata_directory = "%s/unhealthy"\n' "$TMP" >"$TMP/unhealthy.toml"
printf 'name = "online-unhealthy-retained"\ndata_directory = "%s/unhealthy-retained"\n' "$TMP" >"$TMP/unhealthy-retained.toml"
printf 'name = "online-healthy"\ndata_directory = "%s/healthy"\n' "$TMP" >"$TMP/healthy.toml"
printf 'name = "active-run"\ndata_directory = "%s/active"\n' "$TMP" >"$TMP/active.toml"
printf '#!/usr/bin/env bash\ncase "$1" in\n  list-units)\n    echo "factory-claude.service loaded active running"\n    echo "factory-unhealthy.service loaded active running"\n    echo "factory-unhealthy-retained.service loaded active running"\n    echo "factory-healthy.service loaded active running"\n    echo "factory-active.service loaded active running"\n    ;;\n  cat)\n    case "$2" in\n      factory-claude.service) config=worker.toml ;;\n      factory-unhealthy.service) config=unhealthy.toml ;;\n      factory-unhealthy-retained.service) config=unhealthy-retained.toml ;;\n      factory-healthy.service) config=healthy.toml ;;\n      factory-active.service) config=active.toml ;;\n    esac\n    echo "ExecStart=/bin/factory-worker --config %s/$config"\n    ;;\nesac\n' "$TMP" >"$TMP/bin/systemctl"
printf '#!/usr/bin/env bash\nexit 0\n' >"$TMP/bin/sleep"
printf '#!/usr/bin/env bash\nexit 0\n' >"$TMP/bin/su"
printf '#!/usr/bin/env bash\nif [ "$1" = "%s/worker/worktrees/unmoved" ]; then exit 1; fi\nexec /bin/mv "$@"\n' "$TMP" >"$TMP/bin/mv"
chmod +x "$TMP/bin/systemctl" "$TMP/bin/sleep" "$TMP/bin/su" "$TMP/bin/mv"
sed -i '2i echo "$*" >> "'$TMP'/systemctl.log"' "$TMP/bin/systemctl"
printf 'done\n' >"$TMP/healthy-reason"
printf '#!/usr/bin/env bash\npayload=\nprevious=\nfor arg in "$@"; do\n  if [ "$previous" = data ]; then payload=$arg; fi\n  [ "$arg" = --data-binary ] && previous=data || previous=\ndone\nlast=${!#}\nif [ "$last" = "$ESCALATION_TARGET" ]; then echo "$payload" >>"$ESCALATION_LOG"; exit 0; fi\nexec /usr/bin/curl "$@"\n' >"$TMP/bin/curl"
chmod +x "$TMP/bin/curl"

python3 -c '
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
requests, request_path = sys.argv[1:3]
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = {"workers": [
            {"id": "worker-1", "name": "claude-haiku", "online": False, "active_count": 0, "health": "healthy", "retained_worktrees": [{"attempt_id": "attempt-moved", "repository_id": "repo-1", "path": sys.argv[3], "reason": "failed", "cleanup_command": "cleanup moved"}, {"attempt_id": "attempt-missing", "repository_id": "repo-1", "path": sys.argv[4], "reason": "failed", "cleanup_command": "cleanup missing"}, {"attempt_id": "attempt-unmoved", "repository_id": "repo-1", "path": sys.argv[5], "reason": "failed", "cleanup_command": "cleanup unmoved"}]},
            {"id": "worker-2", "name": "online-unhealthy", "online": True, "active_count": 0, "health": "unhealthy", "retained_worktrees": []},
            {"id": "worker-3", "name": "online-unhealthy-retained", "online": True, "active_count": 0, "health": "unhealthy", "retained_worktrees": [{"attempt_id": "attempt-unhealthy", "repository_id": "repo-1", "path": sys.argv[6], "reason": "failed", "cleanup_command": "cleanup unhealthy"}]},
            {"id": "worker-4", "name": "online-healthy", "online": True, "active_count": 0, "health": "healthy", "retained_worktrees": [{"attempt_id": "attempt-healthy", "repository_id": "repo-1", "path": sys.argv[7], "reason": open(sys.argv[8]).read().strip(), "cleanup_command": "keep"}]},
            {"id": "worker-5", "name": "active-run", "online": True, "active_count": 1, "health": "healthy", "capacity": 1, "retained_worktrees": []}
        ]}
        encoded = json.dumps(body).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", len(encoded)); self.end_headers(); self.wfile.write(encoded)
    def do_POST(self):
        size = int(self.headers["Content-Length"])
        try: records = json.load(open(requests))
        except (FileNotFoundError, json.JSONDecodeError): records = []
        records.append({"path": self.path, "payload": json.loads(self.rfile.read(size))})
        json.dump(records, open(requests, "w"))
        self.send_response(200); self.end_headers()
    def log_message(self, *args): pass
server = HTTPServer(("127.0.0.1", 0), Handler)
print(server.server_port, flush=True)
server.serve_forever()
' "$TMP/request.json" "$TMP/request-path" "$TMP/worker/worktrees/retained" "$TMP/worker/worktrees/missing" "$TMP/worker/worktrees/unmoved" "$TMP/unhealthy-retained/worktrees/retained" "$TMP/healthy/worktrees/retained" "$TMP/healthy-reason" >"$TMP/server.log" 2>&1 &
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
FACTORY_JANITOR_CACHE_ROOT="$TMP/cache" \
FACTORY_JANITOR_BROWSER_ROOT="$TMP/cache/ms-playwright" \
FACTORY_JANITOR_RELEASES_ROOT="$TMP/releases" \
FACTORY_JANITOR_MANIFEST="$TMP/state/candidates.json" \
FACTORY_JANITOR_LOCK="$TMP/janitor.lock" \
FACTORY_JANITOR_API="http://127.0.0.1:$PORT/api/v1" \
ESCALATION_TARGET="https://ntfy.sh/timafen-a8523d037f21" \
ESCALATION_LOG="$TMP/escalations.log" \
bash "$ROOT/ops/factory-janitor.sh"

python3 - "$TMP/request.json" <<'PY'
import json, sys
requests = json.load(open(sys.argv[1]))
assert [request["path"] for request in requests] == [
    "/api/v1/workers/worker-1/retained-worktrees/clear",
    "/api/v1/workers/worker-3/retained-worktrees/clear",
], requests
retained = requests[0]["payload"]["retained_worktrees"]
assert [item["attempt_id"] for item in retained] == [
    "attempt-moved", "attempt-missing"
], retained
assert requests[1]["payload"]["retained_worktrees"][0]["attempt_id"] == "attempt-unhealthy", requests
PY
test ! -e "$TMP/worker/worktrees/retained"
test -e "$TMP/worker/worktrees/unmoved"
test -e "$TMP/quarantine/worker-retained."* 2>/dev/null
test ! -e "$TMP/unhealthy-retained/worktrees/retained"
test -e "$TMP/quarantine/unhealthy-retained-retained."* 2>/dev/null
test -e "$TMP/healthy/worktrees/retained"
test ! -e "$TMP/quarantine/healthy-retained."* 2>/dev/null
grep -q 'подтверждена очистка retained worktree: claude-haiku' "$TMP/janitor.log"
test "$(grep -c 'stop factory-unhealthy.service\|start factory-unhealthy.service' "$TMP/systemctl.log" || true)" -eq 0
test "$(grep -c 'stop factory-unhealthy-retained.service\|start factory-unhealthy-retained.service' "$TMP/systemctl.log" || true)" -eq 2
test "$(python3 -c 'import json; print("online-unhealthy" in json.load(open("'$TMP'/state/heals.json")))')" = False
test "$(grep -c 'ОСВОБОЖДАЮ online-healthy' "$TMP/janitor.log" || true)" -eq 0
test "$(grep -c 'stop factory-healthy.service\|start factory-healthy.service' "$TMP/systemctl.log" || true)" -eq 0
test "$(wc -l <"$TMP/escalations.log")" -eq 1
grep -q 'online-healthy.*attempt-healthy.*healthy/worktrees/retained.*reason=done' "$TMP/escalations.log"

# The exact snapshot is durable across runs, while a changed reason is new.
PATH="$TMP/bin:$PATH" FACTORY_JANITOR_LOG="$TMP/janitor.log" \
FACTORY_JANITOR_STATE="$TMP/state/heals.json" FACTORY_JANITOR_QUARANTINE="$TMP/quarantine" \
FACTORY_JANITOR_API="http://127.0.0.1:$PORT/api/v1" \
FACTORY_JANITOR_ESCALATION_URL="mock://owner" ESCALATION_TARGET="mock://owner" \
ESCALATION_LOG="$TMP/escalations.log" bash "$ROOT/ops/factory-janitor.sh"
test "$(wc -l <"$TMP/escalations.log")" -eq 1
printf 'owner-review\n' >"$TMP/healthy-reason"
PATH="$TMP/bin:$PATH" FACTORY_JANITOR_LOG="$TMP/janitor.log" \
FACTORY_JANITOR_STATE="$TMP/state/heals.json" FACTORY_JANITOR_QUARANTINE="$TMP/quarantine" \
FACTORY_JANITOR_API="http://127.0.0.1:$PORT/api/v1" \
FACTORY_JANITOR_ESCALATION_URL="mock://owner" ESCALATION_TARGET="mock://owner" \
ESCALATION_LOG="$TMP/escalations.log" bash "$ROOT/ops/factory-janitor.sh"
test "$(wc -l <"$TMP/escalations.log")" -eq 2

# A failed owner channel is logged, stays retryable, and never harms the result.
printf 'channel-down\n' >"$TMP/healthy-reason"
printf '#!/usr/bin/env bash\necho "notification unavailable" >&2\nexit 22\n' >"$TMP/bin/curl"
chmod +x "$TMP/bin/curl"
PATH="$TMP/bin:$PATH" FACTORY_JANITOR_LOG="$TMP/janitor.log" \
FACTORY_JANITOR_STATE="$TMP/state/heals.json" FACTORY_JANITOR_QUARANTINE="$TMP/quarantine" \
FACTORY_JANITOR_API="http://127.0.0.1:$PORT/api/v1" \
FACTORY_JANITOR_ESCALATION_URL="mock://owner" bash "$ROOT/ops/factory-janitor.sh"
test -e "$TMP/healthy/worktrees/retained"
grep -q 'не удалось отправить эскалацию healthy retained.*attempt=attempt-healthy' "$TMP/janitor.log"
test "$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))["healthy_retained_escalations"]))' "$TMP/state/heals.json")" -eq 2

# With no channel configured, one explicit log entry is the durable fallback.
for _ in 1 2; do
  PATH="$TMP/bin:$PATH" FACTORY_JANITOR_LOG="$TMP/janitor.log" \
  FACTORY_JANITOR_STATE="$TMP/state/heals.json" FACTORY_JANITOR_QUARANTINE="$TMP/quarantine" \
  FACTORY_JANITOR_API="http://127.0.0.1:$PORT/api/v1" \
  FACTORY_JANITOR_ESCALATION_URL= bash "$ROOT/ops/factory-janitor.sh"
done
test "$(grep -c 'Канал эскалации не настроен' "$TMP/janitor.log")" -eq 1
test "$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))["healthy_retained_escalations"]))' "$TMP/state/heals.json")" -eq 3

# Keep the legacy confirmation-failure scenario independent of rate limiting.
python3 - "$TMP/state/heals.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
data["claude-haiku"] = []
json.dump(data, open(sys.argv[1], "w"))
PY

mkdir -p "$TMP/worker/worktrees/missing"
printf '#!/usr/bin/env bash\necho "confirmation unavailable" >&2\nexit 22\n' >"$TMP/bin/curl"
chmod +x "$TMP/bin/curl"
PATH="$TMP/bin:$PATH" \
FACTORY_JANITOR_LOG="$TMP/janitor.log" \
FACTORY_JANITOR_STATE="$TMP/state/heals.json" \
FACTORY_JANITOR_QUARANTINE="$TMP/quarantine" \
FACTORY_JANITOR_CACHE_ROOT="$TMP/cache" \
FACTORY_JANITOR_BROWSER_ROOT="$TMP/cache/ms-playwright" \
FACTORY_JANITOR_RELEASES_ROOT="$TMP/releases" \
FACTORY_JANITOR_MANIFEST="$TMP/state/candidates.json" \
FACTORY_JANITOR_LOCK="$TMP/janitor.lock" \
FACTORY_JANITOR_API="http://127.0.0.1:$PORT/api/v1" \
bash "$ROOT/ops/factory-janitor.sh"

test ! -e "$TMP/worker/worktrees/missing"
test -e "$TMP/quarantine/worker-missing."* 2>/dev/null
grep -q 'не удалось подтвердить очистку retained worktree: claude-haiku' "$TMP/janitor.log"

# Новая ежедневная фаза: старые разрешённые объекты сначала только попадают в
# журнал, а на неизменившемся втором снимке удаляются. Свежие, активные,
# неуспешные и две последние успешные версии сохраняются.
mkdir -p "$TMP/cache/old" "$TMP/cache/fresh" "$TMP/cache/ms-playwright/old-browser" \
  "$TMP/quarantine/old-quarantine" "$TMP/quarantine/fresh-quarantine" \
  "$TMP/releases/release-1" "$TMP/releases/release-2" "$TMP/releases/release-3" \
  "$TMP/releases/release-4" "$TMP/releases/failed"
touch "$TMP/releases/release-1/.successful" "$TMP/releases/release-2/.successful" \
  "$TMP/releases/release-3/.successful" "$TMP/releases/release-4/.successful"
ln -s release-4 "$TMP/releases/current"
ln -s release-3 "$TMP/releases/previous"
touch -d '8 days ago' "$TMP/cache/old" "$TMP/cache/ms-playwright/old-browser" \
  "$TMP/active" "$TMP/quarantine/old-quarantine" "$TMP/releases/release-1" "$TMP/releases/release-2"
run_daily() {
  PATH="$TMP/bin:$PATH" \
  FACTORY_JANITOR_LOG="$TMP/janitor.log" FACTORY_JANITOR_STATE="$TMP/state/heals.json" \
  FACTORY_JANITOR_QUARANTINE="$TMP/quarantine" FACTORY_JANITOR_CACHE_ROOT="$TMP/cache" \
  FACTORY_JANITOR_BROWSER_ROOT="$TMP/cache/ms-playwright" FACTORY_JANITOR_RELEASES_ROOT="$TMP/releases" \
  FACTORY_JANITOR_MANIFEST="$TMP/state/candidates.json" FACTORY_JANITOR_LOCK="$TMP/janitor.lock" \
  FACTORY_JANITOR_API="http://127.0.0.1:$PORT/api/v1" bash "$ROOT/ops/factory-janitor.sh"
}
rm -f "$TMP/bin/curl" "$TMP/state/candidates.json"
run_daily
test -e "$TMP/cache/old" && test -e "$TMP/quarantine/old-quarantine"
grep -q 'DRY-RUN категория=cache' "$TMP/janitor.log"
grep -q 'DRY-RUN категория=quarantine' "$TMP/janitor.log"
grep -q 'DRY-RUN категория=release' "$TMP/janitor.log"
run_daily
test ! -e "$TMP/cache/old" && test ! -e "$TMP/cache/ms-playwright/old-browser"
test ! -e "$TMP/quarantine/old-quarantine"
test -e "$TMP/cache/fresh" && test -e "$TMP/active/worktrees/current"
test -e "$TMP/quarantine/fresh-quarantine"
test ! -e "$TMP/releases/release-1" && test ! -e "$TMP/releases/release-2"
test -e "$TMP/releases/release-3" && test -e "$TMP/releases/release-4"
test -e "$TMP/releases/failed"

# Параллельный запуск ничего не делает, а недоступный API останавливает фазу
# до отбора и удаления кандидатов.
exec 8>"$TMP/janitor.lock"
flock -n 8
run_daily
grep -q 'другой janitor уже работает' "$TMP/janitor.log"
flock -u 8

# Фактический ответ /workers не содержит пути active run. Если конфигурация
# worker не найдена, уборка должна остановиться до удаления кандидатов.
sed -i '/factory-active.service) config=active.toml/d' "$TMP/bin/systemctl"
mkdir -p "$TMP/cache/unknown-active"
touch -d '8 days ago' "$TMP/cache/unknown-active"
if run_daily; then
  echo 'janitor unexpectedly cleaned with an unknown active worker path' >&2
  exit 1
fi
test -e "$TMP/cache/unknown-active"
grep -q 'путь активного прогона active-run неизвестен' "$TMP/janitor.log"

# Вернуть конфигурацию в тестовую заглушку для проверки отказа API ниже.
sed -i '/factory-healthy.service) config=healthy.toml ;;/a\\      factory-active.service) config=active.toml ;;' "$TMP/bin/systemctl"
mkdir -p "$TMP/cache/api-failure-candidate"
touch -d '8 days ago' "$TMP/cache/api-failure-candidate"
kill "$SERVER_PID"
wait "$SERVER_PID" 2>/dev/null || true
SERVER_PID=
if run_daily; then
  echo 'janitor unexpectedly ignored API failure' >&2
  exit 1
fi
test -e "$TMP/cache/api-failure-candidate"
grep -q 'API активных прогонов недоступен' "$TMP/janitor.log"

grep -q '^User=root$' "$ROOT/ops/systemd/factory-janitor.service"
grep -q '^ReadWritePaths=/opt/factory-data /var/lib/factory-janitor /var/log/factory-janitor.log /run/factory-janitor.lock$' "$ROOT/ops/systemd/factory-janitor.service"

echo 'TestJanitorSelectsOfflineRetainedWorker: PASS'
echo 'TestJanitorSkipsOnlineUnhealthyWorker: PASS'
echo 'TestJanitorCleansOnlineUnhealthyRetainedWorker: PASS'
echo 'TestJanitorSkipsOnlineHealthyRetainedWorker: PASS'
echo 'TestJanitorUsesDefaultEscalationChannel: PASS'
echo 'TestJanitorEscalatesHealthyRetainedSnapshotOnce: PASS'
echo 'TestJanitorRetriesFailedHealthyRetainedEscalation: PASS'
echo 'TestJanitorClearsRetainedWorktreeAfterQuarantine: PASS'
echo 'TestJanitorDryRunThenCleansSafeDailyCandidates: PASS'
echo 'TestJanitorLockAndApiFailureAreFailClosed: PASS'
echo 'TestJanitorUnknownActiveWorkerFailsClosed: PASS'
echo 'TestJanitorServiceHasRequiredRestrictedPrivileges: PASS'
