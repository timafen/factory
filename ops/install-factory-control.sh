#!/bin/bash
# Atomically installs the root-owned Factory control entrypoint and release
# driver from one checked-out revision. A partial update is rolled back.
set -euo pipefail

SRC=${1:?путь к исходникам Factory}
FX_TARGET=${FACTORY_FX_BIN:-/usr/local/bin/fx}
RELEASE_TARGET=${FACTORY_RELEASE_DRIVER:-/usr/local/lib/fx-factory-release}
CGROUP_TARGET=${FACTORY_GATE_CGROUP_HELPER:-/usr/local/libexec/factory-gate-cgroup}
OWNER=${FACTORY_CONTROL_OWNER-root:root}

fx_source=$SRC/ops/fx
release_source=$SRC/ops/fx-factory-release
cgroup_source=$SRC/ops/factory-gate-cgroup
[ -f "$fx_source" ]
[ -f "$release_source" ]
[ -f "$cgroup_source" ]
bash -n "$fx_source"
bash -n "$release_source"
bash -n "$cgroup_source"

declare -a targets=("$FX_TARGET" "$RELEASE_TARGET" "$CGROUP_TARGET")
declare -a sources=("$fx_source" "$release_source" "$cgroup_source")
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

for ((i=0; i<${#targets[@]}; i++)); do
  target=${targets[$i]}
  source=${sources[$i]}
  directory=$(dirname "$target")
  mkdir -p "$directory"
  temporary=$(mktemp "$directory/.factory-control.XXXXXX")
  prepared[$i]=$temporary
  if [ -n "$OWNER" ]; then
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

committed=1
printf 'Factory control tools updated from one revision\n'
