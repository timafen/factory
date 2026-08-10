#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT
mkdir -p "$temporary/bin"
printf '{"enabled_dangerous":["factory"]}\n' >"$temporary/policy.json"
printf '{}\n' >"$temporary/grants.json"
: >"$temporary/log"
: >"$temporary/events"

sed \
  -e "s#^POLICY=.*#POLICY=$temporary/policy.json#" \
  -e "s#^GRANTS=.*#GRANTS=$temporary/grants.json#" \
  -e "s#^LOG=.*#LOG=$temporary/log#" \
  -e "s#/usr/local/share/factory/browser-sandbox/ops/install-server-browser.sh#$temporary/installer#" \
  -e "s#/usr/local/libexec/factory-browser-sandbox-check#$temporary/checker#" \
  -e "s#/usr/local/libexec/factory-browser-sandbox#$temporary/launcher#" \
  -e "s#/usr/local/lib/fx-factory-release-bootstrap#$temporary/bootstrap#" \
  "$root/ops/fx" >"$temporary/fx"
chmod 755 "$temporary/fx"

cat >"$temporary/bin/id" <<'EOF'
#!/bin/sh
[ "${1:-}" = -u ] && { echo 0; exit 0; }
exec /usr/bin/id "$@"
EOF
for command in installer checker launcher bootstrap; do
  cat >"$temporary/$command" <<EOF
#!/bin/sh
printf '$command %s\n' "\$*" >>'$temporary/events'
EOF
  chmod 755 "$temporary/$command"
done
chmod 755 "$temporary/bin/id"

PATH="$temporary/bin:/usr/bin:/bin" "$temporary/fx" factory browser-sandbox install
PATH="$temporary/bin:/usr/bin:/bin" "$temporary/fx" factory browser-sandbox check
PATH="$temporary/bin:/usr/bin:/bin" "$temporary/fx" factory browser-sandbox run --proxy-address=169.254.7.9 --proxy-port=1234 -- /bin/true
trusted_sha=1234567890abcdef1234567890abcdef12345678
PATH="$temporary/bin:/usr/bin:/bin" "$temporary/fx" factory install-release-helper "$trusted_sha"

if PATH="$temporary/bin:/usr/bin:/bin" "$temporary/fx" factory install-release-helper main \
  >/dev/null 2>&1; then
  echo "short branch name was accepted as a trusted transition" >&2
  exit 1
fi

expected=$(printf '%s\n' 'installer ' 'checker ' \
  'launcher run --proxy-address=169.254.7.9 --proxy-port=1234 -- /bin/true' \
  "bootstrap $trusted_sha")
[ "$(cat "$temporary/events")" = "$expected" ]
echo "PASS: fx принимает доверенный переход только для полного commit origin/main"
