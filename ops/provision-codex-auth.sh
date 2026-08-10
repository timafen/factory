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

original_targets=()
had_original=()
temporaries=()

# Validate every destination before changing any auth link.
for i in "${!homes[@]}"; do
  home=${homes[$i]}
  [ "$(dirname "$home")" = "$DATA_HOME" ] \
    || fail "CODEX_HOME must be a direct .codex-* child of $DATA_HOME: $home"
  case "$(basename "$home")" in
    .codex-?*) ;;
    *) fail "CODEX_HOME must be a direct .codex-* child of $DATA_HOME: $home" ;;
  esac

  for previous in "${homes[@]:0:$i}"; do
    [ "$previous" != "$home" ] || fail "duplicate CODEX_HOME: $home"
  done
  [ ! -e "$home" ] || [ -d "$home" ] \
    || fail "CODEX_HOME is not a directory: $home"
  link=$home/auth.json
  if [ -e "$link" ] && [ ! -L "$link" ]; then
    fail "$link exists and is not a symlink"
  fi

  if [ -L "$link" ]; then
    original_targets[$i]=$(readlink -- "$link") \
      || fail "cannot inspect auth link: $link"
    had_original[$i]=yes
  else
    original_targets[$i]=
    had_original[$i]=no
  fi
done

# Prepare every replacement before changing the first auth link.
for i in "${!homes[@]}"; do
  home=${homes[$i]}
  if [ ! -d "$home" ]; then
    as_factory mkdir -m 755 -- "$home" \
      || fail "cannot create CODEX_HOME: $home"
  fi
  temporary=$home/.auth.json.provision.$$
  temporaries[$i]=$temporary
  as_factory ln -s -- "$AUTH_TARGET" "$temporary" \
    || {
      for prepared in "${temporaries[@]}"; do
        as_factory rm -f -- "$prepared" 2>/dev/null || true
      done
      fail "cannot prepare auth link in $home"
    }
done

rollback_links() {
  local last=$1 rollback_failed=no j rollback_tmp rollback_link
  for ((j=last; j>=0; j--)); do
    rollback_link=${homes[$j]}/auth.json
    if [ "${had_original[$j]}" = yes ]; then
      rollback_tmp=${homes[$j]}/.auth.json.rollback.$$
      as_factory rm -f -- "$rollback_tmp" 2>/dev/null || true
      if ! as_factory ln -s -- "${original_targets[$j]}" "$rollback_tmp" ||
         ! as_factory mv -Tf -- "$rollback_tmp" "$rollback_link"; then
        rollback_failed=yes
      fi
    elif ! as_factory rm -f -- "$rollback_link"; then
      rollback_failed=yes
    fi
  done
  for prepared in "${temporaries[@]}"; do
    as_factory rm -f -- "$prepared" 2>/dev/null || true
  done
  [ "$rollback_failed" = no ] || fail "rollback failed; inspect auth links"
}

for i in "${!homes[@]}"; do
  home=${homes[$i]}
  link=$home/auth.json
  if ! as_factory mv -Tf -- "${temporaries[$i]}" "$link"; then
    rollback_links "$i"
    fail "cannot install auth link: $link; previous links restored"
  fi
done

for i in "${!homes[@]}"; do
  link=${homes[$i]}/auth.json
  read -r link_user link_group < <(stat -c '%U %G' "$link") \
    || {
      rollback_links "$((${#homes[@]} - 1))"
      fail "cannot inspect auth link: $link; previous links restored"
    }
  if [ "$link_user:$link_group" != "$FACTORY_USER:$FACTORY_GROUP" ]; then
    rollback_links "$((${#homes[@]} - 1))"
    fail "$link must be owned by $FACTORY_USER:$FACTORY_GROUP; previous links restored"
  fi
done

printf 'Codex auth ready: %d link(s), protected shared target\n' "${#homes[@]}"
