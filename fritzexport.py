#!/usr/bin/env python3
"""Shim für direkten Skript-Aufruf — Logik liegt in fritzexport/cli.py."""
from __future__ import annotations

import sys

from fritzexport.cli import main

if __name__ == "__main__":
    sys.exit(main())
