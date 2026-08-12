#!/bin/bash
set -euo pipefail
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

source_file=${1:-"$(/usr/bin/dirname -- "$0")/factory-gate-cgroup"}
target=${FACTORY_GATE_CGROUP_HELPER:-/usr/local/libexec/factory-gate-cgroup}

[ "$(/usr/bin/id -u)" = 0 ] || { printf 'root is required\n' >&2; exit 1; }
[ -f "$source_file" ] && [ ! -L "$source_file" ] || { printf 'invalid helper source\n' >&2; exit 1; }
/usr/bin/install -o root -g root -m 0755 -- "$source_file" "$target"
