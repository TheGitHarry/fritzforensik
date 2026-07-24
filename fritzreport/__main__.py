"""Entry-Point: `python -m fritzreport` und PyInstaller-Target.

Absolute Import — relative würde im PyInstaller-Bundle brechen, weil
__main__.py dort als Top-Level-Skript ohne Package-Kontext läuft.
"""
from __future__ import annotations

import sys

from fritzreport.cli import main

if __name__ == "__main__":
    sys.exit(main())
