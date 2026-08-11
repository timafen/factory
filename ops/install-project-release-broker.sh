#!/bin/bash
set -euo pipefail

SOURCE_BINARY=${1:?путь к собранному factory-release-broker}
SOURCE_UNIT=${2:?путь к factory-release-broker.service}
BINARY_TARGET=${FACTORY_RELEASE_BROKER_BIN:-/opt/factory-data/bin/factory-release-broker}
UNIT_TARGET=${FACTORY_RELEASE_BROKER_UNIT:-/etc/systemd/system/factory-release-broker.service}
SERVER_DROPIN_TARGET=${FACTORY_RELEASE_BROKER_SERVER_DROPIN:-/etc/systemd/system/factory-server.service.d/50-project-release-broker.conf}
OWNER=${FACTORY_RELEASE_BROKER_OWNER-root:root}
SYSTEMCTL=${FACTORY_RELEASE_BROKER_SYSTEMCTL:-systemctl}
GETENT=${FACTORY_RELEASE_BROKER_GETENT:-getent}
GROUPADD=${FACTORY_RELEASE_BROKER_GROUPADD:-groupadd}
BROKER_GROUP=${FACTORY_RELEASE_BROKER_GROUP:-factory-release}

[ -x "$SOURCE_BINARY" ]
[ -f "$SOURCE_UNIT" ]
grep -qx 'User=root' "$SOURCE_UNIT"
grep -qx "Group=$BROKER_GROUP" "$SOURCE_UNIT"
grep -qx 'NoNewPrivileges=true' "$SOURCE_UNIT"
grep -qx 'ExecStart=/opt/factory-data/bin/factory-release-broker' "$SOURCE_UNIT"

if ! "$GETENT" group "$BROKER_GROUP" >/dev/null 2>&1; then
  "$GROUPADD" --system "$BROKER_GROUP"
fi

mkdir -p "$(dirname "$BINARY_TARGET")" "$(dirname "$UNIT_TARGET")" "$(dirname "$SERVER_DROPIN_TARGET")"
binary_tmp=$(mktemp "$(dirname "$BINARY_TARGET")/.factory-release-broker.XXXXXX")
unit_tmp=$(mktemp "$(dirname "$UNIT_TARGET")/.factory-release-broker-service.XXXXXX")
dropin_tmp=$(mktemp "$(dirname "$SERVER_DROPIN_TARGET")/.factory-release-broker-dropin.XXXXXX")
cleanup() { rm -f -- "$binary_tmp" "$unit_tmp" "$dropin_tmp"; }
trap cleanup EXIT HUP INT TERM

printf '[Service]\nSupplementaryGroups=%s\n' "$BROKER_GROUP" >"$dropin_tmp"

if [ -n "$OWNER" ]; then
  install -o "${OWNER%:*}" -g "${OWNER#*:}" -m 755 "$SOURCE_BINARY" "$binary_tmp"
  install -o "${OWNER%:*}" -g "${OWNER#*:}" -m 644 "$SOURCE_UNIT" "$unit_tmp"
  chown "${OWNER%:*}:${OWNER#*:}" "$dropin_tmp"
else
  install -m 755 "$SOURCE_BINARY" "$binary_tmp"
  install -m 644 "$SOURCE_UNIT" "$unit_tmp"
fi
chmod 644 "$dropin_tmp"
mv -f -- "$binary_tmp" "$BINARY_TARGET"
mv -f -- "$unit_tmp" "$UNIT_TARGET"
mv -f -- "$dropin_tmp" "$SERVER_DROPIN_TARGET"

"$SYSTEMCTL" daemon-reload
if "$SYSTEMCTL" is-active --quiet factory-release-broker.service; then
  "$SYSTEMCTL" restart factory-release-broker.service
else
  "$SYSTEMCTL" enable --now factory-release-broker.service
fi

printf 'Privileged project release broker installed\n'
