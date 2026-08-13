#!/usr/bin/env bash
# Освобождает остановленные рабочие копии, не удаляя их сразу: сначала
# переносит их в карантин, откуда оператор может восстановить результат.
set -uo pipefail

LOG=${FACTORY_JANITOR_LOG:-/var/log/factory-janitor.log}
STATE=${FACTORY_JANITOR_STATE:-/var/lib/factory-janitor/heals.json}
QUAR=${FACTORY_JANITOR_QUARANTINE:-/opt/factory-data/quarantine}
API=${FACTORY_JANITOR_API:-http://127.0.0.1:7337/api/v1}
LOCK=${FACTORY_JANITOR_LOCK:-/run/factory-janitor.lock}
CACHE_ROOT=${FACTORY_JANITOR_CACHE_ROOT:-/opt/factory-data/.cache}
BROWSER_ROOT=${FACTORY_JANITOR_BROWSER_ROOT:-/opt/factory-data/.cache/ms-playwright}
RELEASES_ROOT=${FACTORY_JANITOR_RELEASES_ROOT:-/opt/factory-data/releases}
MANIFEST=${FACTORY_JANITOR_MANIFEST:-/var/lib/factory-janitor/cleanup-candidates.json}
mkdir -p "$(dirname "$STATE")" "$QUAR"
[ -f "$LOG" ] && [ "$(stat -c%s "$LOG")" -gt 5000000 ] \
  && tail -c 1000000 "$LOG" >"$LOG.tmp" && mv "$LOG.tmp" "$LOG"
say() { echo "$(date -Is) $*" >>"$LOG"; }

mkdir -p "$(dirname "$LOCK")"
exec 9>"$LOCK"
if ! flock -n 9; then
  say "другой janitor уже работает — ежедневная уборка пропущена"
  exit 0
fi

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
    offline_with_retained = not worker.get("online") and retained
    if not worker.get("active_count") and offline_with_retained:
        print(worker["name"], worker["id"], b64encode(json.dumps(retained).encode()).decode(), sep="\t")
PY
)

# Ежедневная фаза намеренно вынесена в один fail-closed проход. Первый запуск
# только фиксирует точный набор; удаление разрешено лишь если второй снимок
# совпал с записанным манифестом.
active_file=$(mktemp)
trap 'rm -f "$active_file"' EXIT
if ! python3 - "$API" >"$active_file" <<'PY'
import json, sys, urllib.request
try:
    data = json.loads(urllib.request.urlopen(sys.argv[1] + "/workers", timeout=20).read())
    for worker in data.get("workers", []):
        if worker.get("active_count"):
            for key in ("path", "worktree_path", "data_directory"):
                if worker.get(key): print(worker[key])
            for item in worker.get("retained_worktrees") or []:
                if item.get("path"): print(item["path"])
except Exception as exc:
    print(f"не удалось определить активные прогоны: {exc}", file=sys.stderr)
    raise SystemExit(1)
PY
then
  say "ежедневная уборка пропущена: API активных прогонов недоступен"
  exit 1
fi

if ! python3 - "$LOG" "$MANIFEST" "$CACHE_ROOT" "$BROWSER_ROOT" "$QUAR" \
  "$RELEASES_ROOT" "$active_file" "${FACTORY_JANITOR_CACHE_DAYS:-3}" \
  "${FACTORY_JANITOR_QUARANTINE_DAYS:-7}" "${FACTORY_JANITOR_KEEP_RELEASES:-2}" <<'PY'
import json, os, shutil, sys, time
log, manifest, cache, browser, quarantine, releases, active_file, cache_days, quarantine_days, keep = sys.argv[1:]
cache_days, quarantine_days, keep = int(cache_days), int(quarantine_days), int(keep)
now = int(time.time())

def write(message):
    with open(log, "a") as out:
        out.write(time.strftime("%Y-%m-%dT%H:%M:%S%z ") + message + "\n")

def valid_root(path):
    return os.path.isabs(path) and os.path.normpath(path) != "/" and not os.path.islink(path)

roots = [cache, browser, quarantine, releases]
if not all(valid_root(path) for path in roots):
    raise RuntimeError("небезопасный корень ежедневной уборки")
active = [os.path.realpath(line.strip()) for line in open(active_file) if line.strip()]
def protected(path):
    real = os.path.realpath(path)
    return any(real == item or real.startswith(item + os.sep) or item.startswith(real + os.sep) for item in active)

candidates = []
def scan(category, root, days):
    if not os.path.isdir(root): return
    boundary = now - days * 86400
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if os.path.islink(path) or protected(path): continue
        info = os.lstat(path)
        if int(info.st_mtime) < boundary:
            candidates.append({"category": category, "path": path, "size": info.st_size,
                               "mtime": int(info.st_mtime), "retention_days": days})

# Browser is its own category; do not also nominate it through its parent cache.
scan("cache", cache, cache_days)
candidates[:] = [c for c in candidates if os.path.realpath(c["path"]) != os.path.realpath(browser)]
scan("browser", browser, cache_days)
scan("quarantine", quarantine, quarantine_days)

if os.path.isdir(releases):
    protected_releases = set()
    for link in ("current", "previous"):
        path = os.path.join(releases, link)
        if os.path.islink(path): protected_releases.add(os.path.realpath(path))
    successful = []
    for name in os.listdir(releases):
        path = os.path.join(releases, name)
        if os.path.isdir(path) and not os.path.islink(path) and os.path.isfile(os.path.join(path, ".successful")):
            successful.append((os.lstat(path).st_mtime, path))
    protected_releases.update(path for _, path in sorted(successful, reverse=True)[:keep])
    for _, path in successful:
        if os.path.realpath(path) not in protected_releases and not protected(path):
            info = os.lstat(path)
            candidates.append({"category": "release", "path": path, "size": info.st_size,
                               "mtime": int(info.st_mtime), "retention_days": 0})

policy = {"cache_days": cache_days, "quarantine_days": quarantine_days, "keep_releases": keep,
          "roots": roots}
snapshot = {"policy": policy, "candidates": sorted(candidates, key=lambda x: (x["category"], x["path"]))}
previous = None
try:
    previous = json.load(open(manifest))
except FileNotFoundError:
    pass
if previous != snapshot:
    os.makedirs(os.path.dirname(manifest), exist_ok=True)
    tmp = manifest + ".tmp"
    with open(tmp, "w") as out: json.dump(snapshot, out, ensure_ascii=False, indent=2)
    os.replace(tmp, manifest)
    for item in snapshot["candidates"]:
        write("DRY-RUN категория={category} путь={path} размер={size} mtime={mtime} retention={retention_days}d".format(**item))
    write(f"DRY-RUN сохранён манифест: кандидатов={len(candidates)}")
else:
    for item in snapshot["candidates"]:
        path = item["path"]
        if protected(path) or os.path.islink(path): raise RuntimeError("кандидат стал небезопасным: " + path)
        if os.path.isdir(path): shutil.rmtree(path)
        else: os.unlink(path)
        write("УДАЛЕНО категория={category} путь={path}".format(**item))
    os.unlink(manifest)
PY
then
  say "ежедневная уборка завершилась ошибкой; широкое удаление остановлено"
  exit 1
fi
exit 0
