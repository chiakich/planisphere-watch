#!/usr/bin/env bash
# Fetch band10-toolkit at the tested commit, add pointer support, install deps, and create the Python venv.
set -euo pipefail
cd "$(dirname "$0")/.."

TOOLKIT_REPO=https://github.com/utsabfdahal/band10-toolkit.git
TOOLKIT_COMMIT=549abf5046ce207327ca82fdc20b0320c27a3830

if [ ! -d vendor/band10-toolkit ]; then
  git clone --quiet "$TOOLKIT_REPO" vendor/band10-toolkit
  git -C vendor/band10-toolkit checkout --quiet "$TOOLKIT_COMMIT"
  git -C vendor/band10-toolkit apply ../../patches/band10-toolkit-widge-pointer.patch
fi
npm --prefix vendor/band10-toolkit install --no-audit --no-fund --silent

python3 -m venv .venv
.venv/bin/pip install --quiet -r requirements.txt
echo "setup done"
