#!/bin/bash
set -euo pipefail

SOURCE_BINARY=${1:?путь к собранному factory-release-broker}
SOURCE_UNIT=${2:?путь к factory-release-broker.service}
BINARY_TARGET=${FACTORY_RELEASE_BROKER_BIN:-/opt/factory-data/bin/factory-release-broker}
UNIT_TARGET=${FACTORY_RELEASE_BROKER_UNIT:-/etc/systemd/system/factory-release-broker.service}
OWNER=${FACTORY_RELEASE_BROKER_OWNER-root:root}
SYSTEMCTL=${FACTORY_RELEASE_BROKER_SYSTEMCTL:-systemctl}

[ -x "$SOURCE_BINARY" ]
[ -f "$SOURCE_UNIT" ]
grep -qx 'User=root' "$SOURCE_UNIT"
grep -qx 'Group=factory' "$SOURCE_UNIT"
grep -qx 'NoNewPrivileges=true' "$SOURCE_UNIT"
grep -qx 'ExecStart=/opt/factory-data/bin/factory-release-broker' "$SOURCE_UNIT"

mkdir -p "$(dirname "$BINARY_TARGET")" "$(dirname "$UNIT_TARGET")"
binary_tmp=$(mktemp "$(dirname "$BINARY_TARGET")/.factory-release-broker.XXXXXX")
unit_tmp=$(mktemp "$(dirname "$UNIT_TARGET")/.factory-release-broker-service.XXXXXX")
cleanup() { rm -f -- "$binary_tmp" "$unit_tmp"; }
trap cleanup EXIT HUP INT TERM

if [ -n "$OWNER" ]; then
  install -o "${OWNER%:*}" -g "${OWNER#*:}" -m 755 "$SOURCE_BINARY" "$binary_tmp"
  install -o "${OWNER%:*}" -g "${OWNER#*:}" -m 644 "$SOURCE_UNIT" "$unit_tmp"
else
  install -m 755 "$SOURCE_BINARY" "$binary_tmp"
  install -m 644 "$SOURCE_UNIT" "$unit_tmp"
fi
mv -f -- "$binary_tmp" "$BINARY_TARGET"
mv -f -- "$unit_tmp" "$UNIT_TARGET"

"$SYSTEMCTL" daemon-reload
if ! "$SYSTEMCTL" is-active --quiet factory-release-broker.service; then
  "$SYSTEMCTL" enable --now factory-release-broker.service
fi

printf 'Privileged project release broker installed\n'
