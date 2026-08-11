#!/bin/bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT
mkdir -p "$temporary/bin"

cat >"$temporary/bin/systemctl" <<'EOF'
#!/bin/bash
set -euo pipefail
printf '%s\n' "$*" >>"$FACTORY_BROKER_SYSTEMCTL_LOG"
if [ "$1" = is-active ]; then exit 3; fi
EOF
chmod +x "$temporary/bin/systemctl"
cat >"$temporary/broker" <<'EOF'
#!/bin/sh
exit 0
EOF
chmod +x "$temporary/broker"

FACTORY_RELEASE_BROKER_BIN="$temporary/out/factory-release-broker" \
FACTORY_RELEASE_BROKER_UNIT="$temporary/systemd/factory-release-broker.service" \
FACTORY_RELEASE_BROKER_OWNER= \
FACTORY_RELEASE_BROKER_SYSTEMCTL="$temporary/bin/systemctl" \
FACTORY_BROKER_SYSTEMCTL_LOG="$temporary/systemctl.log" \
  "$root/ops/install-project-release-broker.sh" \
    "$temporary/broker" "$root/ops/systemd/factory-release-broker.service"

test -x "$temporary/out/factory-release-broker"
grep -qx 'User=root' "$temporary/systemd/factory-release-broker.service"
grep -qx 'Group=factory' "$temporary/systemd/factory-release-broker.service"
grep -qx 'NoNewPrivileges=true' "$temporary/systemd/factory-release-broker.service"
grep -qx 'daemon-reload' "$temporary/systemctl.log"
grep -qx 'enable --now factory-release-broker.service' "$temporary/systemctl.log"
