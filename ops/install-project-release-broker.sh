#!/bin/bash
set -euo pipefail

SOURCE_BINARY=${1:?путь к собранному factory-release-broker}
SOURCE_UNIT=${2:?путь к factory-release-broker.service}
BINARY_TARGET=${FACTORY_RELEASE_BROKER_BIN:-/opt/factory-data/bin/factory-release-broker}
UNIT_TARGET=${FACTORY_RELEASE_BROKER_UNIT:-/etc/systemd/system/factory-release-broker.service}
PILOT_DROPIN_TARGET=${FACTORY_RELEASE_BROKER_PILOT_DROPIN:-/etc/systemd/system/factory-pilot.service.d/50-project-release-broker.conf}
LEGACY_SERVER_DROPIN=${FACTORY_RELEASE_BROKER_LEGACY_SERVER_DROPIN:-/etc/systemd/system/factory-server.service.d/50-project-release-broker.conf}
OWNER=${FACTORY_RELEASE_BROKER_OWNER-root:root}
SYSTEMCTL=${FACTORY_RELEASE_BROKER_SYSTEMCTL:-systemctl}
GETENT=${FACTORY_RELEASE_BROKER_GETENT:-getent}
GROUPADD=${FACTORY_RELEASE_BROKER_GROUPADD:-groupadd}
BROKER_GROUP=${FACTORY_RELEASE_BROKER_GROUP:-factory-release}
SYNC=${FACTORY_RELEASE_BROKER_SYNC:-sync}

[ -x "$SOURCE_BINARY" ]
[ -f "$SOURCE_UNIT" ]
grep -qx 'User=root' "$SOURCE_UNIT"
grep -qx "Group=$BROKER_GROUP" "$SOURCE_UNIT"
# The broker starts as root and the release driver drops to the factory user
# with setpriv. With the unit's isolation profile, NoNewPrivileges removes the
# CAP_SETUID needed for that transition; the unit documents this exception.
grep -qx 'NoNewPrivileges=false' "$SOURCE_UNIT"
grep -qx 'StateDirectory=factory/release-broker' "$SOURCE_UNIT"
grep -qx 'ExecStart=/opt/factory-data/bin/factory-release-broker --state-dir /var/lib/factory/release-broker' "$SOURCE_UNIT"

if ! "$GETENT" group "$BROKER_GROUP" >/dev/null 2>&1; then
  "$GROUPADD" --system "$BROKER_GROUP"
fi

mkdir -p "$(dirname "$BINARY_TARGET")" "$(dirname "$UNIT_TARGET")" "$(dirname "$PILOT_DROPIN_TARGET")"
binary_tmp=$(mktemp "$(dirname "$BINARY_TARGET")/.factory-release-broker.XXXXXX")
unit_tmp=$(mktemp "$(dirname "$UNIT_TARGET")/.factory-release-broker-service.XXXXXX")
dropin_tmp=$(mktemp "$(dirname "$PILOT_DROPIN_TARGET")/.factory-release-broker-dropin.XXXXXX")
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
"$SYNC" -f "$binary_tmp" "$unit_tmp" "$dropin_tmp"
mv -f -- "$binary_tmp" "$BINARY_TARGET"
mv -f -- "$unit_tmp" "$UNIT_TARGET"
mv -f -- "$dropin_tmp" "$PILOT_DROPIN_TARGET"
"$SYNC" -f "$(dirname "$BINARY_TARGET")" "$(dirname "$UNIT_TARGET")" "$(dirname "$PILOT_DROPIN_TARGET")"
# The real socket consumer is now safely configured; only then remove the old,
# ineffective server override left by previous installations.
if [ "$LEGACY_SERVER_DROPIN" != "$PILOT_DROPIN_TARGET" ]; then
  rm -f -- "$LEGACY_SERVER_DROPIN"
fi

"$SYSTEMCTL" daemon-reload
if "$SYSTEMCTL" is-active --quiet factory-release-broker.service; then
  "$SYSTEMCTL" restart factory-release-broker.service
else
  "$SYSTEMCTL" enable --now factory-release-broker.service
fi
"$SYSTEMCTL" restart factory-pilot.service

printf 'Privileged project release broker installed\n'
