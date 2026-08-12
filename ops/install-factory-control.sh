#!/bin/bash
# Atomically installs root-owned Factory control tools from a trusted bootstrap
# revision. Releases use the already-installed helper and never provision it
# from a candidate checkout.
set -euo pipefail
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

SRC=${1:?путь к исходникам Factory}
FX_TARGET=${FACTORY_FX_BIN:-/usr/local/bin/fx}
RELEASE_TARGET=${FACTORY_RELEASE_DRIVER:-/usr/local/lib/fx-factory-release}
INSTALLER_TARGET=${FACTORY_CONTROL_INSTALLER:-/usr/local/libexec/factory-install-control}
GATE_TARGET=${FACTORY_GATE_CGROUP_HELPER:-/usr/local/libexec/factory-gate-cgroup}
BOOTSTRAP_TARGET=${FACTORY_CGROUP_BOOTSTRAP:-/usr/local/libexec/factory-cgroup-bootstrap}
OWNER=${FACTORY_CONTROL_OWNER-root:root}
BOOTSTRAP=${FACTORY_CONTROL_BOOTSTRAP:-0}
GATE_HELPER_SHA256=b241be54c609c4c172dab0796f4408081fa5e9d7f429eba694712ffd03f109ac

fx_source=$SRC/ops/fx
release_source=$SRC/ops/fx-factory-release
gate_source=$SRC/ops/factory-gate-cgroup
[ -f "$fx_source" ]
[ -f "$release_source" ]
bash -n "$fx_source"
bash -n "$release_source"

declare -a targets=("$FX_TARGET" "$RELEASE_TARGET")
declare -a sources=("$fx_source" "$release_source")
declare -a prepared=()
declare -a backups=()
committed=0

cleanup() {
  local status=$?
  if [ "$committed" -ne 1 ]; then
    for ((i=${#targets[@]}-1; i>=0; i--)); do
      target=${targets[$i]}
      backup=${backups[$i]:-}
      if [ -n "$backup" ] && [ -e "$backup" ]; then
        mv -f -- "$backup" "$target"
      elif [ "${prepared[$i]:-}" = installed ]; then
        rm -f -- "$target"
      fi
    done
  fi
  for path in "${backups[@]:-}"; do
    [ -z "$path" ] || rm -f -- "$path"
  done
  for path in "${prepared[@]:-}"; do
    [ -z "$path" ] || [ "$path" = installed ] || rm -f -- "$path"
  done
  exit "$status"
}
trap cleanup EXIT HUP INT TERM

validate_root_owned_path() {
  local path=$1 canonical owner mode
  canonical=$(/usr/bin/readlink -e -- "$path") || return 1
  [ "$canonical" = "$path" ] || return 1
  while :; do
    [ ! -L "$path" ] || return 1
    owner=$(/usr/bin/stat -c %u -- "$path") || return 1
    mode=$(/usr/bin/stat -c %a -- "$path") || return 1
    [ "$owner" = 0 ] && (( (8#$mode & 0022) == 0 )) || return 1
    [ "$path" = / ] && break
    path=${path%/*}; [ -n "$path" ] || path=/
  done
}

case "$BOOTSTRAP" in
  0) ;;
  1)
    [ "$(/usr/bin/id -u)" = 0 ] || { echo 'root is required for control bootstrap' >&2; exit 1; }
    canonical_src=$(/usr/bin/readlink -e -- "$SRC") \
      && [ "$canonical_src" = "$SRC" ] && validate_root_owned_path "$SRC" \
      && validate_root_owned_path "$SRC/ops" \
      || { echo 'bootstrap source chain has unsafe path, owner, or mode' >&2; exit 1; }
    for bootstrap_source in "$fx_source" "$release_source" "$gate_source" "$SRC/ops/factory-cgroup-bootstrap.sh"; do
      [ -f "$bootstrap_source" ] && validate_root_owned_path "$bootstrap_source" \
        || { echo "unsafe bootstrap source: $bootstrap_source" >&2; exit 1; }
    done
    [ -f "$gate_source" ] && [ ! -L "$gate_source" ] \
      || { echo 'invalid cgroup helper source' >&2; exit 1; }
    [ "$(/usr/bin/sha256sum -- "$gate_source" | /usr/bin/awk '{print $1}')" = "$GATE_HELPER_SHA256" ] \
      || { echo 'cgroup helper hash does not match trusted bootstrap release' >&2; exit 1; }
    bash -n "$gate_source"
    targets+=("$INSTALLER_TARGET" "$GATE_TARGET")
    sources+=("$0" "$gate_source")
    [ -f "$SRC/ops/factory-cgroup-bootstrap.sh" ] && [ ! -L "$SRC/ops/factory-cgroup-bootstrap.sh" ] \
      || { echo 'invalid cgroup bootstrap source' >&2; exit 1; }
    bash -n "$SRC/ops/factory-cgroup-bootstrap.sh"
    targets+=("$BOOTSTRAP_TARGET")
    sources+=("$SRC/ops/factory-cgroup-bootstrap.sh")
    ;;
  *) echo 'FACTORY_CONTROL_BOOTSTRAP must be 0 or 1' >&2; exit 1 ;;
esac

for ((i=0; i<${#targets[@]}; i++)); do
  target=${targets[$i]}
  source=${sources[$i]}
  directory=$(dirname "$target")
  mkdir -p "$directory"
  temporary=$(mktemp "$directory/.factory-control.XXXXXX")
  prepared[$i]=$temporary
  if [ "$target" = "$GATE_TARGET" ] || [ "$target" = "$INSTALLER_TARGET" ] || [ "$target" = "$BOOTSTRAP_TARGET" ]; then
    install -o root -g root -m 755 "$source" "$temporary"
  elif [ -n "$OWNER" ]; then
    install -o "${OWNER%:*}" -g "${OWNER#*:}" -m 755 "$source" "$temporary"
  else
    install -m 755 "$source" "$temporary"
  fi
  backups[$i]=
done

for ((i=0; i<${#targets[@]}; i++)); do
  target=${targets[$i]}
  temporary=${prepared[$i]}
  if [ -e "$target" ] || [ -L "$target" ]; then
    backup=$(mktemp "$(dirname "$target")/.factory-control.previous.XXXXXX")
    rm -f -- "$backup"
    mv -- "$target" "$backup"
    backups[$i]=$backup
  fi
  mv -- "$temporary" "$target"
  prepared[$i]=installed
done

if [ "$BOOTSTRAP" = 1 ]; then
  for target in "$INSTALLER_TARGET" "$GATE_TARGET" "$BOOTSTRAP_TARGET"; do
    owner=$(stat -Lc %u -- "$target")
    mode=$(stat -Lc %a -- "$target")
    [ "$owner" = 0 ] && [ "$mode" = 755 ] \
      || { echo "unsafe installed control tool: $target" >&2; exit 1; }
  done
  [ "$(sha256sum -- "$GATE_TARGET" | awk '{print $1}')" = "$GATE_HELPER_SHA256" ] \
    || { echo 'installed cgroup helper hash mismatch' >&2; exit 1; }
fi
committed=1
printf 'Factory control tools updated from one revision\n'
