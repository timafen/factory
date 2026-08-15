#!/bin/bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT
mkdir -p "$temporary/bin"
mkdir -p "$temporary/systemd/factory-server.service.d"
printf 'legacy\n' >"$temporary/systemd/factory-server.service.d/50-project-release-broker.conf"

cat >"$temporary/bin/systemctl" <<'EOF'
#!/bin/bash
set -euo pipefail
printf '%s\n' "$*" >>"$FACTORY_BROKER_SYSTEMCTL_LOG"
if [ "$1" = is-active ]; then
  [ "${FACTORY_BROKER_ACTIVE:-0}" = 1 ]
  exit
fi
if [ "$1" = restart ] && [ "$2" = factory-release-broker.service ]; then
  grep -qx '# broker version 2' "$FACTORY_RELEASE_BROKER_BIN"
fi
EOF
chmod +x "$temporary/bin/systemctl"
cat >"$temporary/bin/getent" <<'EOF'
#!/bin/sh
exit 1
EOF
chmod +x "$temporary/bin/getent"
cat >"$temporary/bin/groupadd" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >>"$FACTORY_BROKER_GROUPADD_LOG"
EOF
chmod +x "$temporary/bin/groupadd"
cat >"$temporary/bin/sync" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >>"$FACTORY_BROKER_SYNC_LOG"
EOF
chmod +x "$temporary/bin/sync"
cat >"$temporary/broker" <<'EOF'
#!/bin/sh
# broker version 1
exit 0
EOF
chmod +x "$temporary/broker"

FACTORY_RELEASE_BROKER_BIN="$temporary/out/factory-release-broker" \
FACTORY_LIVE_ACCEPTANCE_BIN="$temporary/out/factory-live-acceptance" \
FACTORY_RELEASE_BROKER_UNIT="$temporary/systemd/factory-release-broker.service" \
FACTORY_RELEASE_BROKER_PILOT_DROPIN="$temporary/systemd/factory-pilot.service.d/50-project-release-broker.conf" \
FACTORY_RELEASE_BROKER_LEGACY_SERVER_DROPIN="$temporary/systemd/factory-server.service.d/50-project-release-broker.conf" \
FACTORY_RELEASE_BROKER_OWNER= \
FACTORY_RELEASE_BROKER_SYSTEMCTL="$temporary/bin/systemctl" \
FACTORY_RELEASE_BROKER_GETENT="$temporary/bin/getent" \
FACTORY_RELEASE_BROKER_GROUPADD="$temporary/bin/groupadd" \
FACTORY_RELEASE_BROKER_SYNC="$temporary/bin/sync" \
FACTORY_BROKER_SYSTEMCTL_LOG="$temporary/systemctl.log" \
FACTORY_BROKER_GROUPADD_LOG="$temporary/groupadd.log" \
FACTORY_BROKER_SYNC_LOG="$temporary/sync.log" \
  "$root/ops/install-project-release-broker.sh" \
    "$temporary/broker" "$root/ops/systemd/factory-release-broker.service"

test -x "$temporary/out/factory-release-broker"
grep -qx 'User=root' "$temporary/systemd/factory-release-broker.service"
grep -qx 'Group=factory-release' "$temporary/systemd/factory-release-broker.service"
grep -qx 'NoNewPrivileges=false' "$temporary/systemd/factory-release-broker.service"
grep -qx 'StateDirectory=factory/release-broker' "$temporary/systemd/factory-release-broker.service"
grep -qx 'SupplementaryGroups=factory-release' "$temporary/systemd/factory-pilot.service.d/50-project-release-broker.conf"
test ! -e "$temporary/systemd/factory-server.service.d/50-project-release-broker.conf"
grep -qx -- '--system factory-release' "$temporary/groupadd.log"
grep -qx 'daemon-reload' "$temporary/systemctl.log"
grep -qx 'enable --now factory-release-broker.service' "$temporary/systemctl.log"
grep -qx 'restart factory-pilot.service' "$temporary/systemctl.log"
test "$(grep -nE 'enable --now factory-release-broker|restart factory-pilot' "$temporary/systemctl.log" | cut -d: -f1 | tr '\n' ' ')" = "3 4 "
test "$(wc -l <"$temporary/sync.log")" -eq 2
grep -q -- '-f .*/\.factory-release-broker\.' "$temporary/sync.log"
grep -q -- "-f $temporary/out $temporary/systemd $temporary/systemd/factory-pilot.service.d" "$temporary/sync.log"

cat >"$temporary/broker" <<'EOF'
#!/bin/sh
# broker version 2
exit 0
EOF
chmod +x "$temporary/broker"
: >"$temporary/systemctl.log"

FACTORY_RELEASE_BROKER_BIN="$temporary/out/factory-release-broker" \
FACTORY_LIVE_ACCEPTANCE_BIN="$temporary/out/factory-live-acceptance" \
FACTORY_RELEASE_BROKER_UNIT="$temporary/systemd/factory-release-broker.service" \
FACTORY_RELEASE_BROKER_PILOT_DROPIN="$temporary/systemd/factory-pilot.service.d/50-project-release-broker.conf" \
FACTORY_RELEASE_BROKER_LEGACY_SERVER_DROPIN="$temporary/systemd/factory-server.service.d/50-project-release-broker.conf" \
FACTORY_RELEASE_BROKER_OWNER= \
FACTORY_RELEASE_BROKER_SYSTEMCTL="$temporary/bin/systemctl" \
FACTORY_RELEASE_BROKER_GETENT="$temporary/bin/getent" \
FACTORY_RELEASE_BROKER_GROUPADD="$temporary/bin/groupadd" \
FACTORY_RELEASE_BROKER_SYNC="$temporary/bin/sync" \
FACTORY_BROKER_SYSTEMCTL_LOG="$temporary/systemctl.log" \
FACTORY_BROKER_GROUPADD_LOG="$temporary/groupadd.log" \
FACTORY_BROKER_SYNC_LOG="$temporary/sync.log" \
FACTORY_BROKER_ACTIVE=1 \
  "$root/ops/install-project-release-broker.sh" \
    "$temporary/broker" "$root/ops/systemd/factory-release-broker.service"

grep -qx '# broker version 2' "$temporary/out/factory-release-broker"
test "$(sed -n '1,4p' "$temporary/systemctl.log" | tr '\n' ' ')" = "daemon-reload is-active --quiet factory-release-broker.service restart factory-release-broker.service restart factory-pilot.service "
if grep -q 'enable --now factory-release-broker.service' "$temporary/systemctl.log"; then
  echo 'active broker was enabled instead of restarted' >&2
  exit 1
fi
