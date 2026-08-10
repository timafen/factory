#!/usr/bin/env bash
# Освобождает остановленные рабочие копии, не удаляя их сразу: сначала
# переносит их в карантин, откуда оператор может восстановить результат.
set -uo pipefail

LOG=${FACTORY_JANITOR_LOG:-/var/log/factory-janitor.log}
STATE=${FACTORY_JANITOR_STATE:-/var/lib/factory-janitor/heals.json}
QUAR=${FACTORY_JANITOR_QUARANTINE:-/opt/factory-data/quarantine}
API=${FACTORY_JANITOR_API:-http://127.0.0.1:7337/api/v1}
mkdir -p "$(dirname "$STATE")" "$QUAR"
[ -f "$LOG" ] && [ "$(stat -c%s "$LOG")" -gt 5000000 ] \
  && tail -c 1000000 "$LOG" >"$LOG.tmp" && mv "$LOG.tmp" "$LOG"
say() { echo "$(date -Is) $*" >>"$LOG"; }

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

SICK=$(python3 - "$API" <<'PY'
import json, sys, urllib.request
try:
    data = json.loads(urllib.request.urlopen(sys.argv[1] + "/workers", timeout=20).read())
except Exception:
    raise SystemExit
for worker in data.get("workers", []):
    retained = worker.get("retained_worktrees") or []
    if worker.get("online") and not worker.get("active_count") and (
            worker.get("health") != "healthy" or retained):
        print(worker["name"])
PY
)

for name in $SICK; do
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
  for worktree in "$dir"/worktrees/*; do
    [ -e "$worktree" ] || continue
    mv "$worktree" "$QUAR/$(basename "$dir")-$(basename "$worktree").$stamp" \
      && say "  результат сохранён в карантине: $(basename "$worktree")"
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
  chown -R factory:factory "$dir" 2>/dev/null
  systemctl start "$unit"
  say "  $name снова запущен; сохранённые результаты лежат в $QUAR"
done

find "$QUAR" -maxdepth 1 -mtime +3 -exec rm -rf {} + 2>/dev/null
exit 0
