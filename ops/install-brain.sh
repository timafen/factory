#!/bin/bash
# Ставит пилот и приёмник из репозитория на сервер. Вызывается из
# fx-factory-release после успешного выката сервера. Запускается от root.
# Логика: проверить синтаксис -> сохранить рабочее -> поставить -> перезапустить
# -> проверить живьём -> при беде вернуть как было.
set -uo pipefail
SRC="${1:?путь к исходникам}"
LIVE="${FACTORY_BRAIN_LIVE:-/opt/factory-data}"
INTAKE_URL="${FACTORY_BRAIN_INTAKE_URL:-http://127.0.0.1:7338}"
INSTALL_OWNER="${FACTORY_BRAIN_OWNER:-factory}"
INSTALL_GROUP="${FACTORY_BRAIN_GROUP:-factory}"
step() { echo "== $*"; }
fail() { echo "!! $*" >&2; }

validate_sources() {
  python3 - "$SRC" pilot/pilot.py pilot/context.md intake/app.py intake/plan.py <<'PY'
import os
import stat
import sys

root = os.path.abspath(sys.argv[1])
paths = sys.argv[2:]

def checked_lstat(path, label):
    try:
        value = os.lstat(path)
    except FileNotFoundError:
        return None
    except OSError as error:
        print("!! не смог проверить %s через lstat: %s" % (label, error), file=sys.stderr)
        raise SystemExit(1)
    if stat.S_ISLNK(value.st_mode):
        print("!! источник содержит симлинк: %s" % label, file=sys.stderr)
        raise SystemExit(1)
    return value

current = os.path.sep
for component in [part for part in root.split(os.path.sep) if part]:
    current = os.path.join(current, component)
    value = checked_lstat(current, current)
    if value is None or not stat.S_ISDIR(value.st_mode):
        print("!! источник не является обычным каталогом: %s" % current, file=sys.stderr)
        raise SystemExit(1)

for relative in paths:
    current = root
    components = relative.split("/")
    for index, component in enumerate(components):
        current = os.path.join(current, component)
        value = checked_lstat(current, relative)
        if value is None:
            break
        final = index == len(components) - 1
        if final and not stat.S_ISREG(value.st_mode):
            print("!! источник не является обычным файлом: %s" % relative, file=sys.stderr)
            raise SystemExit(1)
        if not final and not stat.S_ISDIR(value.st_mode):
            print("!! путь источника не является каталогом: %s" % relative, file=sys.stderr)
            raise SystemExit(1)
PY
}

validate_sources || exit 7

changed=""
install_one() {  # $1 файл в репо, $2 живой путь, $3 py|txt
  local s="$SRC/$1" d="$2"
  [ -f "$s" ] || { echo "   $1: в репозитории нет — пропускаю"; return 0; }
  if [ "$3" = py ]; then
    python3 -m py_compile "$s" || { fail "$1 не компилируется — мозг не трогаю"; return 1; }
  fi
  if cmp -s "$s" "$d"; then echo "   $1: без изменений"; return 0; fi
  cp -f "$d" "$d.prev" 2>/dev/null || true
  install -o "$INSTALL_OWNER" -g "$INSTALL_GROUP" -m 644 "$s" "$d" \
    || { fail "не смог поставить $1"; return 1; }
  changed="$changed $d"
  echo "   $1: обновлён"
}

step "ставлю мозг (пилот и приёмник) из репозитория"
install_one pilot/pilot.py   "$LIVE/pilot/pilot.py"   py || exit 7
install_one pilot/context.md "$LIVE/pilot/context.md" txt || exit 7
install_one intake/app.py    "$LIVE/intake/app.py"    py || exit 7
install_one intake/plan.py   "$LIVE/intake/plan.py"   py || exit 7

[ -z "$changed" ] && { echo "   мозг совпадает с репозиторием — перезапуск не нужен"; exit 0; }

restart=""
case "$changed" in
  *"/pilot/"*) restart="$restart factory-pilot factory-intake";;
  *"/intake/"*) restart="$restart factory-intake";;
esac
step "перезапускаю:$restart"
# shellcheck disable=SC2086
systemctl restart $restart
sleep 6

ok=1
for u in $restart; do systemctl -q is-active "$u" || ok=0; done
if [ "$ok" = 1 ] && echo "$restart" | grep -q intake; then
  code=000
  for _ in 1 2 3 4 5 6 7 8; do
    code=$(curl -sS --max-time 10 -o /dev/null -w '%{http_code}' http://127.0.0.1:7338/health || echo 000)
    [ "$code" = 200 ] && break
    sleep 5
  done
  [ "$code" = 200 ] || ok=0
fi
if [ "$ok" = 1 ]; then
  step "задаю мозгу один контрольный вопрос"
  smoke_body=$(mktemp)
  code=$(curl -sS --max-time 180 -o "$smoke_body" -w '%{http_code}' \
    -H 'Content-Type: application/json' \
    --data '{"question":"Как безопасно продолжить выкат?","situation":"Контрольная проверка нового мозга после установки.","title":"Дымовая проверка выката","stage":"release","repository_id":""}' \
    "$INTAKE_URL/suggest-answer" || echo 000)
  if [ "$code" != 200 ] || ! python3 - "$smoke_body" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as stream:
        value = json.load(stream)
    ok = (isinstance(value, dict) and set(value) == {"answer"}
          and isinstance(value["answer"], str) and bool(value["answer"].strip()))
except (OSError, UnicodeError, json.JSONDecodeError):
    ok = False
raise SystemExit(not ok)
PY
  then
    ok=0
  fi
  rm -f "$smoke_body"
fi
if [ "$ok" != 1 ]; then
  fail "мозг после обновления не ответил правильно — возвращаю прежние файлы"
  for d in $changed; do [ -f "$d.prev" ] && cp -f "$d.prev" "$d"; done
  # shellcheck disable=SC2086
  systemctl restart $restart
  exit 7
fi
echo "   мозг обновлён и жив"
exit 0
