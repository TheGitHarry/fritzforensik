#!/usr/bin/env bash
# Lokaler PyInstaller-Build (Linux). stdlib-only → keine Laufzeit-Deps.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m pip install --quiet --upgrade 'pyinstaller>=6'
exec python3 scripts/build.py
