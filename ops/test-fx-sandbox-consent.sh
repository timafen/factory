#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT
mkdir -p "$temporary/bin" "$temporary/staging/current/django" "$temporary/staging/current/.venv/bin"
printf '{"ui_toggleable":["staging"]}\n' >"$temporary/policy.json"
printf '{"staging":{"enabled":true}}\n' >"$temporary/grants.json"
: >"$temporary/staging.env"
: >"$temporary/log"

sed \
  -e "s#^POLICY=.*#POLICY=$temporary/policy.json#" \
  -e "s#^GRANTS=.*#GRANTS=$temporary/grants.json#" \
  -e "s#^LOG=.*#LOG=$temporary/log#" \
  -e "s#^STAGING_ROOT=.*#STAGING_ROOT=$temporary/staging#" \
  -e "s#^STAGING_ENV=.*#STAGING_ENV=$temporary/staging.env#" \
  "$root/ops/fx" >"$temporary/fx"
chmod +x "$temporary/fx"

cat >"$temporary/bin/runuser" <<'EOF'
#!/bin/sh
printf '%s\n' "$*"
EOF
cat >"$temporary/bin/id" <<'EOF'
#!/bin/sh
[ "${1:-}" = -u ] && { echo 0; exit 0; }
exec /usr/bin/id "$@"
EOF
chmod +x "$temporary/bin/runuser" "$temporary/bin/id"

accept() {
  PATH="$temporary/bin:/usr/bin:/bin" "$temporary/fx" "$@" >/dev/null
}
reject() {
  if PATH="$temporary/bin:/usr/bin:/bin" "$temporary/fx" "$@" >"$temporary/output" 2>&1; then
    echo "fx accepted forbidden arguments: $*" >&2
    exit 1
  fi
  grep -q "согласие допускает только" "$temporary/output"
}

accept staging sandbox bootstrap-accounts --interactive-bootstrap --role=seller
accept staging sandbox bootstrap-accounts --consent-status=operation-1

reject staging sandbox bootstrap-accounts --interactive-bootstrap --role=seller --tenant-id=t1
reject staging sandbox bootstrap-accounts --tenant-id=t1 --interactive-bootstrap --role=seller
reject staging sandbox bootstrap-accounts --interactive-bootstrap --role=seller --force
reject staging sandbox bootstrap-accounts --consent-status=operation-1 --account-id=a1
reject staging sandbox bootstrap-accounts --consent-status=operation-1 --force
reject staging sandbox bootstrap-accounts --consent-status=
