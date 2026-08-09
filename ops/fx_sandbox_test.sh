#!/usr/bin/env bash
# Проверяет, что OAuth-согласие не расширяет общий мост fx произвольными флагами.
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
printf '%s\n' '{"ui_toggleable":["staging"]}' > "$tmp/policy.json"
printf '%s\n' '{"staging":{"enabled":true}}' > "$tmp/access.json"

sed \
  -e 's|if \[ "$(id -u)" -ne 0 \]; then|if false; then|' \
  -e "s|^POLICY=.*|POLICY=$tmp/policy.json|" \
  -e "s|^GRANTS=.*|GRANTS=$tmp/access.json|" \
  -e "s|^LOG=.*|LOG=$tmp/fx.log|" \
  -e '/^scope="${1:-help}"/i runuser() { printf "%s\\n" "$*"; }' \
  "$root/ops/fx" > "$tmp/fx"
chmod +x "$tmp/fx"

reject() {
  if "$tmp/fx" staging sandbox bootstrap-accounts "$@" >/dev/null 2>&1; then
    echo "fx accepted forbidden sandbox arguments: $*" >&2
    exit 1
  fi
}

reject --interactive-bootstrap
reject --role=seller
reject --interactive-bootstrap --role=buyer
reject --interactive-bootstrap --role=seller --tenant-id=other
reject --consent-status=op-1 --account-id=other

started=$("$tmp/fx" staging sandbox bootstrap-accounts --interactive-bootstrap --role=seller)
case "$started" in
  *"bootstrap_sandbox_accounts"*"--interactive-bootstrap --role=seller"*) ;;
  *) echo "fx did not invoke the fixed seller consent operation" >&2; exit 1 ;;
esac

status=$("$tmp/fx" staging sandbox bootstrap-accounts --consent-status=op-1)
case "$status" in
  *"bootstrap_sandbox_accounts"*"--consent-status=op-1"*) ;;
  *) echo "fx did not invoke the fixed consent status operation" >&2; exit 1 ;;
esac
