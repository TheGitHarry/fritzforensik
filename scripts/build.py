#!/usr/bin/env python3
"""PyInstaller-Build für legacy_export (Linux/Windows x86_64).

Erzeugt ein single-file Binary mit gebündeltem certifi-CA-Store und
runtime-tmpdir auf den Stick selbst, damit der Bootstrap-Extract bei
USB-Stick-Einsatz keine Spuren auf dem Host hinterlässt.
"""
from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    sys.path.insert(0, str(REPO_ROOT))
    from legacy_export import __version__

    if sys.platform.startswith("linux"):
        os_tag = "linux-x86_64"
    elif sys.platform.startswith("win"):
        os_tag = "windows-x86_64"
    elif sys.platform == "darwin":
        os_tag = f"macos-{platform.machine()}"
    else:
        os_tag = f"unknown-{platform.machine()}"

    name = f"legacy_export-{__version__}-{os_tag}"
    target = REPO_ROOT / "legacy_export" / "__main__.py"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--name",
        name,
        "--collect-data",
        "certifi",
        "--distpath",
        str(REPO_ROOT / "dist"),
        "--workpath",
        str(REPO_ROOT / "build"),
        "--specpath",
        str(REPO_ROOT / "build"),
        "--clean",
        "--noconfirm",
    ]
    # `--runtime-tmpdir .` legt den Bootstrap-Extract neben das Binary statt
    # in den OS-Default. Auf Linux/macOS unproblematisch und gibt zero
    # host trace beim USB-Stick-Einsatz. Auf Windows bricht es im
    # Drive-Root (F:\) wegen Permissions, daher dort weglassen — der
    # Default %TEMP% wird ohnehin beim Reboot aufgeräumt.
    if not sys.platform.startswith("win"):
        cmd += ["--runtime-tmpdir", "."]
    cmd.append(str(target))
    print(" ".join(cmd))
    return subprocess.call(cmd, cwd=REPO_ROOT)


if __name__ == "__main__":
    sys.exit(main())
