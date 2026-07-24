#!/usr/bin/env python3
"""PyInstaller-Build für legacy_report (Linux/Windows/macOS x86_64/arm).

Single-file Binary, stdlib-only — keine gebündelten Daten nötig. runtime-tmpdir
neben das Binary (zero host trace beim USB-Stick-Einsatz, außer Windows).
"""
from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    sys.path.insert(0, str(REPO_ROOT))
    from legacy_report import __version__

    if sys.platform.startswith("linux"):
        os_tag = f"linux-{platform.machine()}"
    elif sys.platform.startswith("win"):
        os_tag = "windows-x86_64"
    elif sys.platform == "darwin":
        os_tag = f"macos-{platform.machine()}"
    else:
        os_tag = f"unknown-{platform.machine()}"

    name = f"legacy_report-{__version__}-{os_tag}"
    target = REPO_ROOT / "legacy_report" / "__main__.py"

    cmd = [
        sys.executable, "-m", "PyInstaller", "--onefile", "--name", name,
        "--distpath", str(REPO_ROOT / "dist"),
        "--workpath", str(REPO_ROOT / "build"),
        "--specpath", str(REPO_ROOT / "build"),
        "--clean", "--noconfirm",
    ]
    if not sys.platform.startswith("win"):
        cmd += ["--runtime-tmpdir", "."]
    cmd.append(str(target))
    print(" ".join(cmd))
    return subprocess.call(cmd, cwd=REPO_ROOT)


if __name__ == "__main__":
    sys.exit(main())
