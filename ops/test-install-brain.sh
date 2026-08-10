#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
INSTALLER="$SCRIPT_DIR/install-brain.sh"
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }

make_fixture() {
  case_dir=$1 mode=$2
  mkdir -p "$case_dir/src/pilot" "$case_dir/src/intake" \
    "$case_dir/live/pilot" "$case_dir/live/intake" "$case_dir/bin"
  for file in pilot/pilot.py intake/app.py intake/plan.py; do
    printf 'old = True\n' >"$case_dir/live/$file"
    printf 'new = True\n' >"$case_dir/src/$file"
  done
  printf 'old context\n' >"$case_dir/live/pilot/context.md"
  printf 'new context\n' >"$case_dir/src/pilot/context.md"
  : >"$case_dir/events"
  : >"$case_dir/backup-events"

  cat >"$case_dir/bin/systemctl" <<'EOF'
#!/bin/bash
echo "$*" >>"$TEST_EVENTS"
exit 0
EOF
  cat >"$case_dir/bin/sleep" <<'EOF'
#!/bin/bash
exit 0
EOF
  cat >"$case_dir/bin/cp" <<'EOF'
#!/bin/bash
target=${@: -1}
case "$target" in
  /tmp/factory-brain-backup-*/pilot_*|/tmp/factory-brain-backup-*/intake_*)
    printf 'backup=%s mode=%s\n' "$target" "$(stat -c %a "$(dirname "$target")")" >>"$TEST_BACKUP_EVENTS"
    ;;
esac
exec /bin/cp "$@"
EOF
  cat >"$case_dir/bin/curl" <<'EOF'
#!/bin/bash
output=
url=${@: -1}
while [ "$#" -gt 0 ]; do
  if [ "$1" = -o ]; then output=$2; shift 2; else shift; fi
done
case "$url" in
  */health) printf 200 ;;
  */suggest-answer)
    echo smoke >>"$TEST_EVENTS"
    case "$TEST_MODE" in
      success) printf '{"answer":"Продолжить с наблюдением."}' >"$output"; printf 200 ;;
      timeout) exit 28 ;;
      http-error) printf '{"detail":"bad"}' >"$output"; printf 502 ;;
      invalid-json) printf 'not json' >"$output"; printf 200 ;;
      empty-answer) printf '{"answer":"  "}' >"$output"; printf 200 ;;
      extra-field) printf '{"answer":"ok","extra":true}' >"$output"; printf 200 ;;
    esac
    ;;
esac
EOF
  chmod +x "$case_dir/bin/"*
}

run_case() {
  case_dir=$1 mode=$2
  TEST_EVENTS="$case_dir/events" TEST_BACKUP_EVENTS="$case_dir/backup-events" \
    TEST_MODE="$mode" PATH="$case_dir/bin:$PATH" \
    FACTORY_BRAIN_LIVE="$case_dir/live" FACTORY_BRAIN_INTAKE_URL=http://intake \
    FACTORY_BRAIN_OWNER="$(id -un)" FACTORY_BRAIN_GROUP="$(id -gn)" \
    bash "$INSTALLER" "$case_dir/src" >"$case_dir/output" 2>&1
}

leave_only_pilot_py_changed() {
  case_dir=$1
  cp "$case_dir/src/pilot/context.md" "$case_dir/live/pilot/context.md"
  cp "$case_dir/src/intake/app.py" "$case_dir/live/intake/app.py"
  cp "$case_dir/src/intake/plan.py" "$case_dir/live/intake/plan.py"
}

success="$temporary/success"
make_fixture "$success" success
run_case "$success" success || fail "корректный ответ отклонён"
[ "$(grep -c '^smoke$' "$success/events")" = 1 ] || fail "задан не один вопрос"
grep -Fx 'new = True' "$success/live/pilot/pilot.py" >/dev/null \
  || fail "успешный мозг не принят"
grep -E 'backup=/tmp/factory-brain-backup-.+ mode=700' "$success/backup-events" >/dev/null \
  || fail "rollback-копии мозга не были закрыты mode 0700"
while read -r entry _; do
  backup_path=${entry#backup=}
  [ ! -e "$(dirname "$backup_path")" ] || fail "папка rollback-копий мозга не удалена"
done <"$success/backup-events"

for mode in timeout http-error invalid-json empty-answer extra-field; do
  failed="$temporary/$mode"
  make_fixture "$failed" "$mode"
  status=0
  run_case "$failed" "$mode" || status=$?
  [ "$status" = 7 ] || fail "$mode завершился кодом $status вместо 7"
  [ "$(grep -c '^smoke$' "$failed/events")" = 1 ] || fail "$mode сделал не один запрос"
  grep -Fx 'old = True' "$failed/live/pilot/pilot.py" >/dev/null \
    || fail "$mode не вернул прежний мозг"
  [ "$(grep -c '^restart factory-pilot factory-intake$' "$failed/events")" = 2 ] \
    || fail "$mode не перезапустил службы при установке и откате"
done

pilot_only="$temporary/pilot-only"
make_fixture "$pilot_only" invalid-json
leave_only_pilot_py_changed "$pilot_only"
status=0
run_case "$pilot_only" invalid-json || status=$?
[ "$status" = 7 ] || fail "pilot-only завершился кодом $status вместо 7"
expected_events=$(printf '%s\n' \
  'restart factory-pilot factory-intake' \
  '-q is-active factory-pilot' \
  '-q is-active factory-intake' \
  'smoke' \
  'restart factory-pilot factory-intake')
[ "$(cat "$pilot_only/events")" = "$expected_events" ] \
  || fail "pilot-only не перезапустил intake до smoke и после отката"
grep -Fx 'old = True' "$pilot_only/live/pilot/pilot.py" >/dev/null \
  || fail "pilot-only не вернул прежний pilot.py"

unchanged="$temporary/unchanged"
make_fixture "$unchanged" success
cp "$unchanged/src/pilot/pilot.py" "$unchanged/live/pilot/pilot.py"
cp "$unchanged/src/pilot/context.md" "$unchanged/live/pilot/context.md"
cp "$unchanged/src/intake/app.py" "$unchanged/live/intake/app.py"
cp "$unchanged/src/intake/plan.py" "$unchanged/live/intake/plan.py"
run_case "$unchanged" success || fail "быстрый путь без изменений завершился ошибкой"
[ ! -s "$unchanged/events" ] || fail "без изменений были перезапуск или платный запрос"

symlinked="$temporary/symlinked"
make_fixture "$symlinked" success
printf 'root-only secret\n' >"$symlinked/secret"
rm "$symlinked/src/pilot/context.md"
ln -s "$symlinked/secret" "$symlinked/src/pilot/context.md"
status=0
run_case "$symlinked" success || status=$?
[ "$status" = 7 ] || fail "симлинк завершился кодом $status вместо 7"
grep -Fx 'old context' "$symlinked/live/pilot/context.md" >/dev/null \
  || fail "симлинк изменил рабочий context.md"
grep -Fx 'old = True' "$symlinked/live/pilot/pilot.py" >/dev/null \
  || fail "проверка симлинка началась после изменения мозга"
[ ! -s "$symlinked/events" ] || fail "симлинк привёл к перезапуску или smoke-запросу"
grep -F 'источник содержит симлинк: pilot/context.md' "$symlinked/output" >/dev/null \
  || fail "отказ не объяснил найденный симлинк"

previous_symlink="$temporary/previous-symlink"
make_fixture "$previous_symlink" success
printf 'do not overwrite\n' >"$previous_symlink/secret"
ln -s "$previous_symlink/secret" "$previous_symlink/live/pilot/pilot.py.prev"
run_case "$previous_symlink" success || fail "подложенный *.prev сломал безопасную установку"
grep -Fx 'do not overwrite' "$previous_symlink/secret" >/dev/null \
  || fail "installer проследовал по подложенному *.prev"
[ -L "$previous_symlink/live/pilot/pilot.py.prev" ] \
  || fail "installer использовал доступный рядом *.prev вместо закрытой копии"

destination_symlink="$temporary/destination-symlink"
make_fixture "$destination_symlink" success
printf 'destination secret\n' >"$destination_symlink/secret"
rm "$destination_symlink/live/pilot/context.md"
ln -s "$destination_symlink/secret" "$destination_symlink/live/pilot/context.md"
status=0
run_case "$destination_symlink" success || status=$?
[ "$status" = 7 ] || fail "симлинк назначения завершился кодом $status вместо 7"
grep -Fx 'destination secret' "$destination_symlink/secret" >/dev/null \
  || fail "installer проследовал по симлинку назначения"
grep -Fx 'old = True' "$destination_symlink/live/pilot/pilot.py" >/dev/null \
  || fail "назначения проверены после начала установки"
[ ! -s "$destination_symlink/events" ] \
  || fail "симлинк назначения привёл к перезапуску или smoke-запросу"
grep -F 'назначение содержит симлинк: pilot/context.md' "$destination_symlink/output" >/dev/null \
  || fail "отказ не объяснил симлинк назначения"

echo "PASS: мозг откатывается из закрытой папки, а симлинки источников и назначений отклоняются"
