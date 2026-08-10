#!/bin/bash
# Проверяет общий auth.json и создаёт ссылки CODEX_HOME от имени factory.
# Без аргументов обновляет только уже существующие auth-ссылки .codex-*.
set -euo pipefail

DATA_HOME=${FACTORY_CODEX_DATA_HOME:-/opt/factory-data}
FACTORY_USER=${FACTORY_CODEX_USER:-factory}
FACTORY_GROUP=${FACTORY_CODEX_GROUP:-factory}
AUTH_TARGET=${FACTORY_CODEX_AUTH_TARGET:-$DATA_HOME/.codex/auth.json}

fail() { echo "Codex auth provisioning: $*" >&2; exit 1; }

id "$FACTORY_USER" >/dev/null 2>&1 || fail "unknown user: $FACTORY_USER"
getent group "$FACTORY_GROUP" >/dev/null 2>&1 || fail "unknown group: $FACTORY_GROUP"

homes=()
if [ "$#" -gt 0 ]; then
  homes=("$@")
elif [ -n "${CODEX_HOME:-}" ]; then
  homes=("$CODEX_HOME")
else
  while IFS= read -r -d '' link; do
    homes+=("$(dirname "$link")")
  done < <(find "$DATA_HOME" -maxdepth 2 -path "$DATA_HOME/.codex-*/auth.json" \
    -type l -print0 2>/dev/null)
fi

# A Factory installation without Codex workers has nothing to provision.
[ "${#homes[@]}" -gt 0 ] || exit 0

[ -e "$AUTH_TARGET" ] || fail "$AUTH_TARGET is missing"
[ ! -L "$AUTH_TARGET" ] || fail "$AUTH_TARGET must be a regular file, not a symlink"
[ -f "$AUTH_TARGET" ] || fail "$AUTH_TARGET is not a regular file"
read -r target_mode target_user target_group < <(stat -c '%a %U %G' "$AUTH_TARGET") \
  || fail "cannot inspect $AUTH_TARGET"
[ "$target_mode" = 600 ] \
  || fail "$AUTH_TARGET must have mode 600 (found $target_mode)"
[ "$target_user" = "$FACTORY_USER" ] \
  || fail "$AUTH_TARGET must be owned by $FACTORY_USER (found $target_user)"
[ "$target_group" = "$FACTORY_GROUP" ] \
  || fail "$AUTH_TARGET must belong to group $FACTORY_GROUP (found $target_group)"

current_uid=$(id -u)
factory_uid=$(id -u "$FACTORY_USER")
if [ "$current_uid" != 0 ] && [ "$current_uid" != "$factory_uid" ]; then
  fail "run as root or $FACTORY_USER"
fi

as_factory() {
  if [ "$current_uid" = "$factory_uid" ]; then
    "$@"
  else
    runuser -u "$FACTORY_USER" -g "$FACTORY_GROUP" -- "$@"
  fi
}

for home in "${homes[@]}"; do
  [ "$(dirname "$home")" = "$DATA_HOME" ] \
    || fail "CODEX_HOME must be a direct .codex-* child of $DATA_HOME: $home"
  case "$(basename "$home")" in
    .codex-?*) ;;
    *) fail "CODEX_HOME must be a direct .codex-* child of $DATA_HOME: $home" ;;
  esac

  if [ ! -d "$home" ]; then
    as_factory mkdir -m 755 -- "$home" \
      || fail "cannot create CODEX_HOME: $home"
  fi
  link=$home/auth.json
  if [ -e "$link" ] && [ ! -L "$link" ]; then
    fail "$link exists and is not a symlink"
  fi

  temporary=$home/.auth.json.provision.$$
  as_factory ln -s -- "$AUTH_TARGET" "$temporary" \
    || fail "cannot prepare auth link in $home"
  if ! as_factory mv -Tf -- "$temporary" "$link"; then
    as_factory rm -f -- "$temporary" 2>/dev/null || true
    fail "cannot install auth link: $link"
  fi

  read -r link_user link_group < <(stat -c '%U %G' "$link") \
    || fail "cannot inspect auth link: $link"
  [ "$link_user:$link_group" = "$FACTORY_USER:$FACTORY_GROUP" ] \
    || fail "$link must be owned by $FACTORY_USER:$FACTORY_GROUP"
done

printf 'Codex auth ready: %d link(s), protected shared target\n' "${#homes[@]}"
