#!/usr/bin/env bash
# Lokaler PyInstaller-Build (Linux x86_64).
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m pip install --quiet --upgrade 'pyinstaller>=6' 'certifi' 'requests>=2.31'
exec python3 scripts/build.py
