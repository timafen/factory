#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
SERVICE_DIRECTORY="$SCRIPT_DIR/systemd"
expected_cwd='WorkingDirectory=/opt/factory'
checked=0

for service in "$SERVICE_DIRECTORY"/*.service; do
  grep -Fqx 'EnvironmentFile=/opt/factory-data/.claude/oauth.env' "$service" >/dev/null || continue
  checked=$((checked + 1))
  grep -Fqx "$expected_cwd" "$service" >/dev/null || {
    echo "FAIL: $(basename "$service") must use $expected_cwd" >&2
    exit 1
  }
done

[ "$checked" -gt 0 ] || {
  echo "FAIL: no Claude services found" >&2
  exit 1
}

echo "PASS: $checked Claude services use /opt/factory"
