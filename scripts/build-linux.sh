#!/usr/bin/env bash
# Lokaler PyInstaller-Build (Linux).
#   ./scripts/build-linux.sh [export|report|all]   (Default: all)
set -euo pipefail
cd "$(dirname "$0")/.."
TOOL="${1:-all}"
python3 -m pip install --quiet --upgrade 'pyinstaller>=6' 'certifi' 'requests>=2.31'
exec python3 scripts/build.py --tool "$TOOL"
