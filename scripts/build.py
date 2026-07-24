#!/usr/bin/env python3
"""PyInstaller-Build für fritzexport und fritzreport.

    python scripts/build.py --tool export
    python scripts/build.py --tool report
    python scripts/build.py --tool all

Erzeugt je ein single-file Binary. Der runtime-tmpdir liegt neben dem Binary,
damit der Bootstrap-Extract beim USB-Stick-Einsatz keine Spuren auf dem Host
hinterlässt. fritzexport bekommt zusätzlich den certifi-CA-Store gebündelt
(TLS gegen Boxen mit selbstsigniertem Zertifikat sonst kaputt); fritzreport
braucht das nicht — es spricht mit keinem Netz.
"""
from __future__ import annotations

import argparse
import importlib
import platform
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Werkzeug → (Paketname, PyInstaller-Zusatzargumente)
TOOLS: dict[str, tuple[str, list[str]]] = {
    "export": ("fritzexport", ["--collect-data", "certifi"]),
    "report": ("fritzreport", []),
}


def os_tag() -> str:
    if sys.platform.startswith("linux"):
        return f"linux-{platform.machine()}"
    if sys.platform.startswith("win"):
        return "windows-x86_64"
    if sys.platform == "darwin":
        return f"macos-{platform.machine()}"
    return f"unknown-{platform.machine()}"


def build(tool: str) -> int:
    package, extra_args = TOOLS[tool]
    version = importlib.import_module(package).__version__
    name = f"{package}-{version}-{os_tag()}"
    target = REPO_ROOT / package / "__main__.py"

    cmd = [
        sys.executable, "-m", "PyInstaller", "--onefile", "--name", name,
        *extra_args,
        "--distpath", str(REPO_ROOT / "dist"),
        "--workpath", str(REPO_ROOT / "build"),
        "--specpath", str(REPO_ROOT / "build"),
        "--clean", "--noconfirm",
    ]
    # `--runtime-tmpdir .` legt den Bootstrap-Extract neben das Binary statt in
    # den OS-Default. Auf Linux/macOS unproblematisch und gibt zero host trace
    # beim USB-Stick-Einsatz. Auf Windows bricht es im Drive-Root (F:\) wegen
    # Permissions, daher dort weglassen — %TEMP% wird ohnehin beim Reboot leer.
    if not sys.platform.startswith("win"):
        cmd += ["--runtime-tmpdir", "."]
    cmd.append(str(target))

    print(" ".join(cmd))
    return subprocess.call(cmd, cwd=REPO_ROOT)


def main() -> int:
    p = argparse.ArgumentParser(description="PyInstaller-Build für die fritzforensik-Werkzeuge.")
    p.add_argument("--tool", choices=[*TOOLS, "all"], required=True,
                   help="Welches Werkzeug gebaut wird ('all' = beide nacheinander)")
    args = p.parse_args()

    sys.path.insert(0, str(REPO_ROOT))
    tools = list(TOOLS) if args.tool == "all" else [args.tool]
    for tool in tools:
        rc = build(tool)
        if rc != 0:
            return rc
    return 0


if __name__ == "__main__":
    sys.exit(main())
