"""Entry-Point: `python -m legacy_export` und PyInstaller-Target.

Absolute Import — relative würde im PyInstaller-Bundle brechen, weil
__main__.py dort als Top-Level-Skript ohne Package-Kontext läuft.
"""
from __future__ import annotations

import sys

from legacy_export.cli import main

if __name__ == "__main__":
    sys.exit(main())
