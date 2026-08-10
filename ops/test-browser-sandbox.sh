#!/bin/bash
# Cheap release-time guard: the installed launcher must remain executable and
# must not reintroduce Chromium's sandbox bypass flag.
set -euo pipefail

launcher=${FACTORY_BROWSER_LAUNCHER:-/usr/local/libexec/factory/factory-browser-sandbox}
[ -x "$launcher" ]
if grep -Eq -- '--no-sandbox|--disable-setuid-sandbox' "$launcher"; then
  echo "Factory browser launcher disables Chromium sandbox" >&2
  exit 1
fi
