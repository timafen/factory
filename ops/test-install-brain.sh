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

  cat >"$case_dir/bin/systemctl" <<'EOF'
#!/bin/bash
echo "$*" >>"$TEST_EVENTS"
exit 0
EOF
  cat >"$case_dir/bin/sleep" <<'EOF'
#!/bin/bash
exit 0
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
  TEST_EVENTS="$case_dir/events" TEST_MODE="$mode" PATH="$case_dir/bin:$PATH" \
    FACTORY_BRAIN_LIVE="$case_dir/live" FACTORY_BRAIN_INTAKE_URL=http://intake \
    FACTORY_BRAIN_OWNER="$(id -un)" FACTORY_BRAIN_GROUP="$(id -gn)" \
    bash "$INSTALLER" "$case_dir/src" >"$case_dir/output" 2>&1
}

success="$temporary/success"
make_fixture "$success" success
run_case "$success" success || fail "корректный ответ отклонён"
[ "$(grep -c '^smoke$' "$success/events")" = 1 ] || fail "задан не один вопрос"
grep -Fx 'new = True' "$success/live/pilot/pilot.py" >/dev/null \
  || fail "успешный мозг не принят"

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

unchanged="$temporary/unchanged"
make_fixture "$unchanged" success
cp "$unchanged/src/pilot/pilot.py" "$unchanged/live/pilot/pilot.py"
cp "$unchanged/src/pilot/context.md" "$unchanged/live/pilot/context.md"
cp "$unchanged/src/intake/app.py" "$unchanged/live/intake/app.py"
cp "$unchanged/src/intake/plan.py" "$unchanged/live/intake/plan.py"
run_case "$unchanged" success || fail "быстрый путь без изменений завершился ошибкой"
[ ! -s "$unchanged/events" ] || fail "без изменений были перезапуск или платный запрос"

echo "PASS: один ответ принимает мозг, отклонения возвращают прежнюю версию"
