#!/usr/bin/env python3
"""Shim für direkten Skript-Aufruf — Logik liegt in fritzreport/cli.py."""
from __future__ import annotations

import sys

from fritzreport.cli import main

if __name__ == "__main__":
    sys.exit(main())
