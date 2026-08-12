#!/bin/bash
# Проверяет права конечных файлов Codex, не меняя ссылки или секреты.
set -euo pipefail

DATA_HOME=${FACTORY_CODEX_DATA_HOME:-/opt/factory-data}
EXPECTED_USER=${FACTORY_CODEX_USER:-factory}
EXPECTED_GROUP=${FACTORY_CODEX_GROUP:-factory}

# Отсутствие каталога означает, что на этой машине нет Codex-воркеров.
[ -d "$DATA_HOME" ] || exit 0

scan_output=$(mktemp)
trap 'rm -f "$scan_output"' EXIT

# Do not use process substitution here: it hides find's exit status and can
# turn an unreadable worker directory into an empty, apparently safe result.
if ! find "$DATA_HOME" -mindepth 2 -maxdepth 2 \
  -path "$DATA_HOME/.codex-*/auth.json" -type l -print0 >"$scan_output"; then
  printf 'unable to scan Codex worker directories under %s\n' "$DATA_HOME" >&2
  exit 1
fi

links=()
while IFS= read -r -d '' link; do
  links+=("$link")
done <"$scan_output"

# Проверяем только auth.json, являющиеся симлинками непосредственных .codex-*
# каталогов. Обычный stat ссылки намеренно не используется: его режим 777 не
# описывает доступ к конечному файлу.
[ "${#links[@]}" -gt 0 ] || exit 0

status=0
for link in "${links[@]}"; do
  if [ ! -L "$link" ]; then
    printf '%s: not a symlink\n' "$link"
    status=1
    continue
  fi

  metadata=$(stat -Lc '%F %a %U %G' -- "$link" 2>/dev/null) || {
    printf '%s: target metadata unavailable\n' "$link"
    status=1
    continue
  }

  if [ "$metadata" != "regular file 600 $EXPECTED_USER $EXPECTED_GROUP" ]; then
    printf '%s: %s (expected regular file 600 %s %s)\n' \
      "$link" "$metadata" "$EXPECTED_USER" "$EXPECTED_GROUP"
    status=1
  else
    printf '%s: %s\n' "$link" "$metadata"
  fi
done

exit "$status"
