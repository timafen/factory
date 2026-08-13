#!/bin/bash
# One-shot, root-only installation and live check of the Factory gate helper.
# SOURCE_DIR must first be created as a root-owned mode-0700 direct child named
# /run/factory-release-gate/bootstrap-*; ops/README.md contains exact commands.
set -euo pipefail
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

SOURCE_ROOT=${FACTORY_CGROUP_SOURCE_ROOT:-/run/factory-release-gate}
INSTALLER=${FACTORY_CONTROL_INSTALLER:-/usr/local/libexec/factory-install-control}
TARGET=${FACTORY_GATE_CGROUP_HELPER:-/usr/local/libexec/factory-gate-cgroup}
BOOTSTRAP_TARGET=${FACTORY_CGROUP_BOOTSTRAP:-/usr/local/libexec/factory-cgroup-bootstrap}
MARKER=${FACTORY_CGROUP_BOOTSTRAP_MARKER:-/var/lib/factory/cgroup-helper-bootstrap.done}
EXPECTED=b241be54c609c4c172dab0796f4408081fa5e9d7f429eba694712ffd03f109ac

fail() { echo "factory-cgroup-bootstrap: $*" >&2; exit 1; }
[ "$(/usr/bin/id -u)" = 0 ] || fail 'root is required'
[ "$(/usr/bin/stat -fc %T /sys/fs/cgroup)" = cgroup2fs ] || fail 'cgroup v2 is required'
[ "$#" = 1 ] || fail 'usage: factory-cgroup-bootstrap SOURCE_DIR'
source_dir=$1

canonical_dir() {
  local path=$1 canonical
  [ -d "$path" ] && [ ! -L "$path" ] || return 1
  canonical=$(/usr/bin/readlink -e -- "$path") || return 1
  [ "$canonical" = "$path" ] || return 1
  printf '%s\n' "$canonical"
}

validate_secure_chain() {
  local path=$1 owner mode
  while :; do
    [ ! -L "$path" ] || return 1
    owner=$(/usr/bin/stat -c %u -- "$path") || return 1
    mode=$(/usr/bin/stat -c %a -- "$path") || return 1
    [ "$owner" = 0 ] && (( (8#$mode & 0022) == 0 )) || return 1
    [ "$path" = / ] && break
    path=${path%/*}; [ -n "$path" ] || path=/
  done
}

validate_secure_file() {
  local path=$1 canonical owner mode
  [ -f "$path" ] && [ ! -L "$path" ] || return 1
  canonical=$(/usr/bin/readlink -e -- "$path") || return 1
  [ "$canonical" = "$path" ] || return 1
  owner=$(/usr/bin/stat -c %u -- "$path") || return 1
  mode=$(/usr/bin/stat -c %a -- "$path") || return 1
  [ "$owner" = 0 ] && (( (8#$mode & 0022) == 0 ))
}

source_root=$(canonical_dir "$SOURCE_ROOT") || fail 'trusted source root is not canonical'
source_dir=$(canonical_dir "$source_dir") || fail 'bootstrap directory is not canonical'
[ "${source_dir%/*}" = "$source_root" ] || fail 'source must be a direct child of trusted root'
case "${source_dir##*/}" in bootstrap-[a-zA-Z0-9_.-]*) ;; *) fail 'invalid bootstrap directory name' ;; esac
validate_secure_chain "$source_dir" || fail 'bootstrap directory chain has unsafe owner or mode'
[ -d "$source_dir/ops" ] && [ ! -L "$source_dir/ops" ] \
  && [ "$(/usr/bin/readlink -e -- "$source_dir/ops")" = "$source_dir/ops" ] \
  && validate_secure_chain "$source_dir/ops" \
  || fail 'bootstrap ops chain has unsafe owner or mode'
[ ! -e "$MARKER" ] || fail 'one-shot bootstrap was already completed'
validate_secure_file "$INSTALLER" && [ -x "$INSTALLER" ] \
  || fail 'trusted control installer has unsafe path, owner, or mode'

for parent in "$(/usr/bin/dirname -- "$TARGET")" "$(/usr/bin/dirname -- "$BOOTSTRAP_TARGET")"; do
  parent=$(canonical_dir "$parent") && validate_secure_chain "$parent" \
    || fail 'installation target chain has unsafe owner or mode'
done
marker_parent=$(/usr/bin/dirname -- "$MARKER")
if [ ! -e "$marker_parent" ]; then
  marker_base=$(/usr/bin/dirname -- "$marker_parent")
  marker_base=$(canonical_dir "$marker_base") && validate_secure_chain "$marker_base" \
    || fail 'marker parent chain has unsafe owner or mode'
  /usr/bin/mkdir -- "$marker_parent"
  /usr/bin/chown root:root "$marker_parent"
  /bin/chmod 700 "$marker_parent"
fi
marker_parent=$(canonical_dir "$marker_parent") && validate_secure_chain "$marker_parent" \
  || fail 'marker chain has unsafe owner or mode'

for file in fx fx-factory-release factory-gate-cgroup factory-cgroup-bootstrap.sh; do
  path="$source_dir/ops/$file"
  validate_secure_file "$path" || fail "source has unsafe path, owner, or mode: $file"
done
[ "$(/usr/bin/sha256sum -- "$source_dir/ops/factory-gate-cgroup" | /usr/bin/awk '{print $1}')" = "$EXPECTED" ] \
  || fail 'cgroup helper source hash mismatch'

temporary=$(/usr/bin/mktemp -d)
had_target=0; had_installer=0; had_bootstrap=0
restore() {
  status=$?
  if [ "$status" -ne 0 ]; then
    if [ "$had_target" = 1 ]; then /bin/cp -f "$temporary/helper" "$TARGET"; else /bin/rm -f "$TARGET"; fi
    if [ "$had_installer" = 1 ]; then /bin/cp -f "$temporary/installer" "$INSTALLER"; else /bin/rm -f "$INSTALLER"; fi
    if [ "$had_bootstrap" = 1 ]; then /bin/cp -f "$temporary/bootstrap" "$BOOTSTRAP_TARGET"; else /bin/rm -f "$BOOTSTRAP_TARGET"; fi
  fi
  /bin/rm -rf "$temporary"
  exit "$status"
}
trap restore EXIT
if [ -e "$TARGET" ] || [ -L "$TARGET" ]; then /bin/cp -a "$TARGET" "$temporary/helper"; had_target=1; fi
if [ -e "$INSTALLER" ] || [ -L "$INSTALLER" ]; then /bin/cp -a "$INSTALLER" "$temporary/installer"; had_installer=1; fi
if [ -e "$BOOTSTRAP_TARGET" ] || [ -L "$BOOTSTRAP_TARGET" ]; then /bin/cp -a "$BOOTSTRAP_TARGET" "$temporary/bootstrap"; had_bootstrap=1; fi

FACTORY_CONTROL_BOOTSTRAP=1 \
FACTORY_GATE_CGROUP_HELPER="$TARGET" \
FACTORY_CONTROL_INSTALLER="$INSTALLER" \
FACTORY_CGROUP_BOOTSTRAP="$BOOTSTRAP_TARGET" \
  /bin/bash "$INSTALLER" "$source_dir" >/dev/null
[ "$(/usr/bin/stat -Lc '%u %a' -- "$TARGET")" = '0 755' ] || fail 'installed helper has unsafe owner or mode'
[ "$(/usr/bin/sha256sum -- "$TARGET" | /usr/bin/awk '{print $1}')" = "$EXPECTED" ] || fail 'installed helper hash mismatch'
probe="factory-bootstrap-$$"
"$TARGET" create "$probe"
"$TARGET" empty "$probe"
"$TARGET" remove "$probe"

/usr/bin/mkdir -p "$(/usr/bin/dirname -- "$MARKER")"
tmp_marker="$MARKER.tmp.$$"
printf 'completed\n' >"$tmp_marker"
/usr/bin/chown root:root "$tmp_marker"
/bin/chmod 600 "$tmp_marker"
/bin/mv -f "$tmp_marker" "$MARKER"
trap - EXIT
/bin/rm -rf "$temporary"
echo 'cgroup helper installed, live-checked, and bootstrap is now one-shot'
