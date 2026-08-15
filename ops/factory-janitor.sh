#!/usr/bin/env bash
# Освобождает остановленные рабочие копии, не удаляя их сразу: сначала
# переносит их в карантин, откуда оператор может восстановить результат.
set -uo pipefail

LOG=${FACTORY_JANITOR_LOG:-/var/log/factory-janitor.log}
STATE=${FACTORY_JANITOR_STATE:-/var/lib/factory-janitor/heals.json}
QUAR=${FACTORY_JANITOR_QUARANTINE:-/opt/factory-data/quarantine}
API=${FACTORY_JANITOR_API:-http://127.0.0.1:7337/api/v1}
ESCALATION_URL=${FACTORY_JANITOR_ESCALATION_URL-https://ntfy.sh/timafen-a8523d037f21}
mkdir -p "$(dirname "$STATE")" "$QUAR"
[ -f "$LOG" ] && [ "$(stat -c%s "$LOG")" -gt 5000000 ] \
  && tail -c 1000000 "$LOG" >"$LOG.tmp" && mv "$LOG.tmp" "$LOG"
say() { echo "$(date -Is) $*" >>"$LOG"; }

# Healthy workers own their retained results.  Never feed these records into
# the quarantine path below; notify the owner and remember the exact snapshot.
while IFS=$'\t' read -r name attempt_id repository_id path reason snapshot; do
  [ -n "$name" ] || continue
  seen=$(python3 - "$STATE" "$snapshot" <<'PY'
import json, os, sys
state, snapshot = sys.argv[1:]
data = json.load(open(state)) if os.path.exists(state) else {}
print(int(snapshot in data.get("healthy_retained_escalations", [])))
PY
  )
  [ "$seen" = 0 ] || continue

  message="ТРЕБУЕТ ПРОВЕРКИ: healthy воркер $name удерживает результат attempt=$attempt_id repository=$repository_id path=$path reason=$reason. Проверьте результат и выполните cleanup вручную."
  delivered=0
  if [ -z "$ESCALATION_URL" ]; then
    say "$message Канал эскалации не настроен; уведомление зафиксировано только в журнале."
    delivered=1
  elif curl --fail --silent --show-error --data-binary "$message" \
      "$ESCALATION_URL" >>"$LOG" 2>&1; then
    say "эскалация healthy retained отправлена: воркер=$name attempt=$attempt_id path=$path"
    delivered=1
  else
    say "не удалось отправить эскалацию healthy retained: воркер=$name attempt=$attempt_id path=$path"
  fi

  if [ "$delivered" = 1 ]; then
    python3 - "$STATE" "$snapshot" <<'PY'
import json, os, sys, tempfile
state, snapshot = sys.argv[1:]
data = json.load(open(state)) if os.path.exists(state) else {}
items = data.setdefault("healthy_retained_escalations", [])
if snapshot not in items:
    items.append(snapshot)
os.makedirs(os.path.dirname(state), exist_ok=True)
fd, tmp = tempfile.mkstemp(dir=os.path.dirname(state))
with os.fdopen(fd, "w") as stream:
    json.dump(data, stream)
os.replace(tmp, state)
PY
  fi
done < <(python3 - "$API" <<'PY'
import hashlib, json, sys, urllib.request
try:
    data = json.loads(urllib.request.urlopen(sys.argv[1] + "/workers", timeout=20).read())
except Exception:
    raise SystemExit
for worker in data.get("workers", []):
    if not worker.get("online") or worker.get("health") != "healthy":
        continue
    for retained in worker.get("retained_worktrees") or []:
        fields = [worker.get("name", ""), retained.get("attempt_id", ""),
                  retained.get("repository_id", ""), retained.get("path", ""),
                  retained.get("reason", "")]
        snapshot = hashlib.sha256(json.dumps(fields, separators=(",", ":")).encode()).hexdigest()
        print(*fields, snapshot, sep="\t")
PY
)

declare -A UNIT
while read -r unit; do
  toml=$(systemctl cat "$unit" 2>/dev/null | grep -m1 ExecStart \
    | grep -oE '[^ ]*\.toml' | tr -d "'\"")
  [ -n "$toml" ] && [ -f "$toml" ] || continue
  name=$(grep -oE '^name *= *"[^"]+"' "$toml" | head -1 \
    | sed -E 's/.*"([^"]+)"/\1/')
  dir=$(grep -oE '^data_directory *= *"[^"]+"' "$toml" | head -1 \
    | sed -E 's/.*"([^"]+)"/\1/')
  [ -z "$dir" ] && dir="/opt/factory-data/workers/$(basename "${toml%.toml}")"
  [ -n "$name" ] && UNIT["$name"]="$unit|$dir"
done < <(systemctl list-units 'factory*' --no-legend --no-pager | awk '{print $1}')

while IFS=$'\t' read -r name worker_id retained_b64; do
  [ -n "$name" ] || continue
  entry="${UNIT[$name]:-}"
  if [ -z "$entry" ]; then
    say "воркер $name требует освобождения, но служба не найдена"
    continue
  fi
  unit="${entry%%|*}"
  dir="${entry##*|}"
  now=$(date +%s)
  # Важно: отказ из-за лимита не считается новой попыткой. Раньше запись
  # добавлялась при каждом двухминутном осмотре, поэтому счётчик рос бесконечно
  # и санитар больше никогда не мог вернуться к воркеру.
  reservation=$(python3 - "$STATE" "$name" "$now" <<'PY'
import json, os, sys
path, name, now = sys.argv[1], sys.argv[2], int(sys.argv[3])
data = json.load(open(path)) if os.path.exists(path) else {}
recent = [stamp for stamp in data.get(name, []) if now - stamp < 3600]
allowed = len(recent) < 3
before = len(recent)
if allowed:
    recent.append(now)
data[name] = recent
os.makedirs(os.path.dirname(path), exist_ok=True)
json.dump(data, open(path, "w"))
print(before, int(allowed))
PY
)
  count=${reservation%% *}
  allowed=${reservation##* }
  if [ "$allowed" != 1 ]; then
    say "воркер $name: уже освобождал $count раз(а) за час — жду свободного окна"
    continue
  fi

  say "ОСВОБОЖДАЮ $name (служба=$unit), попытка $((count + 1))/3 за час"
  systemctl stop "$unit"
  sleep 2
  stamp=$(date +%s)
  moved=()
  for worktree in "$dir"/worktrees/*; do
    [ -e "$worktree" ] || continue
    if mv "$worktree" "$QUAR/$(basename "$dir")-$(basename "$worktree").$stamp"; then
      moved+=("$worktree")
      say "  результат сохранён в карантине: $(basename "$worktree")"
    fi
  done
  for attempt in "$dir"/attempts/*.json; do
    [ -e "$attempt" ] || continue
    mv "$attempt" "$QUAR/$(basename "$dir")-attempt-$(basename "$attempt").$stamp"
  done
  for repository in "$dir"/repositories/*/; do
    [ -d "$repository" ] || continue
    su -s /bin/bash factory -c \
      "git -c safe.directory='*' -C '$repository' worktree prune" >>"$LOG" 2>&1
  done
  confirmed=$(python3 - "$retained_b64" "${moved[@]}" <<'PY'
import base64, json, os, sys
retained = json.loads(base64.b64decode(sys.argv[1]))
moved = set(sys.argv[2:])
confirmed = []
for worktree in retained:
    path = worktree.get("path")
    if path and (path in moved or not os.path.exists(path)):
        confirmed.append(worktree)
print(json.dumps({"retained_worktrees": confirmed}, separators=(",", ":")))
PY
  )
  if [ "$confirmed" != '{"retained_worktrees":[]}' ]; then
    if curl --fail --silent --show-error -X POST \
      -H 'Content-Type: application/json' \
      --data "$confirmed" \
      "$API/workers/$worker_id/retained-worktrees/clear" >>"$LOG" 2>&1; then
      say "  подтверждена очистка retained worktree: $name"
    else
      say "  не удалось подтвердить очистку retained worktree: $name"
    fi
  fi
  chown -R factory:factory "$dir" 2>/dev/null
  systemctl start "$unit"
  say "  $name снова запущен; сохранённые результаты лежат в $QUAR"
done < <(python3 - "$API" <<'PY'
import json, sys, urllib.request
from base64 import b64encode
try:
    data = json.loads(urllib.request.urlopen(sys.argv[1] + "/workers", timeout=20).read())
except Exception:
    raise SystemExit
for worker in data.get("workers", []):
    retained = worker.get("retained_worktrees") or []
    cleanup_with_retained = retained and (
        not worker.get("online") or worker.get("health") != "healthy"
    )
    if not worker.get("active_count") and cleanup_with_retained:
        print(worker["name"], worker["id"], b64encode(json.dumps(retained).encode()).decode(), sep="\t")
PY
)

find "$QUAR" -maxdepth 1 -mtime +3 -exec rm -rf {} + 2>/dev/null
exit 0
