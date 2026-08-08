#!/bin/bash
# Ставит пилот и приёмник из репозитория на сервер. Вызывается из
# fx-factory-release после успешного выката сервера. Запускается от root.
# Логика: проверить синтаксис -> сохранить рабочее -> поставить -> перезапустить
# -> проверить живьём -> при беде вернуть как было.
set -uo pipefail
SRC="${1:?путь к исходникам}"
LIVE=/opt/factory-data
step() { echo "== $*"; }
fail() { echo "!! $*" >&2; }

changed=""
install_one() {  # $1 файл в репо, $2 живой путь, $3 py|txt
  local s="$SRC/$1" d="$2"
  [ -f "$s" ] || { echo "   $1: в репозитории нет — пропускаю"; return 0; }
  if [ "$3" = py ]; then
    python3 -m py_compile "$s" || { fail "$1 не компилируется — мозг не трогаю"; return 1; }
  fi
  if cmp -s "$s" "$d"; then echo "   $1: без изменений"; return 0; fi
  cp -f "$d" "$d.prev" 2>/dev/null || true
  install -o factory -g factory -m 644 "$s" "$d" || { fail "не смог поставить $1"; return 1; }
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
case "$changed" in *"/pilot/"*)  restart="$restart factory-pilot";;  esac
case "$changed" in *"/intake/"*) restart="$restart factory-intake";; esac
step "перезапускаю:$restart"
# shellcheck disable=SC2086
systemctl restart $restart
sleep 6

ok=1
for u in $restart; do systemctl -q is-active "$u" || ok=0; done
if [ "$ok" = 1 ] && echo "$restart" | grep -q intake; then
  code=$(curl -sS --max-time 20 -o /dev/null -w '%{http_code}' http://127.0.0.1:7338/health || echo 000)
  [ "$code" = 200 ] || ok=0
fi
if [ "$ok" != 1 ]; then
  fail "мозг после обновления не поднялся — возвращаю прежние файлы"
  for d in $changed; do [ -f "$d.prev" ] && cp -f "$d.prev" "$d"; done
  # shellcheck disable=SC2086
  systemctl restart $restart
  exit 7
fi
echo "   мозг обновлён и жив"
exit 0
