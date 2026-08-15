#!/bin/bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT
mkdir -p "$temporary/bin"
printf '%s\n' '0123456789abcdef0123456789abcdef01234567' >"$temporary/current"
cat >"$temporary/bin/curl" <<'EOF'
#!/bin/sh
case "$*" in
  *healthz*) exit 0 ;;
  *api/v1/workers*) printf '%s\n' "$FACTORY_TEST_WORKERS" ;;
  *) exit 1 ;;
esac
EOF
chmod +x "$temporary/bin/curl"

run() {
  PATH="$temporary/bin:$PATH" FACTORY_CURRENT_RELEASE="$temporary/current" \
    FACTORY_CONTROL_PLANE_API=http://fixture FACTORY_TEST_WORKERS="$1" \
    "$root/ops/factory-live-acceptance" --generation-id acceptance-1 --commit-sha 0123456789abcdef0123456789abcdef01234567
}

test "$(run '[{"online":true}]')" = '{"status":"passed"}'
test "$(run '[{"online":false,"retained_worktrees":[{"attempt":"old"}]}]')" = '{"status":"failed","reason":"offline_retained_worktree"}'
