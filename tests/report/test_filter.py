"""jsdom-Smoke-Test der Filter-Logik — via Node, übersprungen wenn Node/jsdom fehlen."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from fritzreport.cli import main as cli_main

HERE = Path(__file__).parent
ROOT = HERE.parent


def _have_node_jsdom() -> bool:
    if not shutil.which("node"):
        return False
    r = subprocess.run(["node", "-e", "require.resolve('jsdom')"],
                       cwd=ROOT, capture_output=True)
    return r.returncode == 0


@pytest.mark.skipif(not _have_node_jsdom(), reason="node/jsdom nicht verfügbar")
def test_filter_logic_in_browser(synth_bundle, tmp_path):
    out = tmp_path / "report.html"
    assert cli_main([str(synth_bundle), "-o", str(out), "--case-id", "C-1"]) == 0
    r = subprocess.run(["node", str(HERE / "filter_smoke.mjs"), str(out)],
                       cwd=ROOT, capture_output=True, text=True)
    print(r.stdout, r.stderr)
    assert r.returncode == 0, f"jsdom-Filtertest fehlgeschlagen:\n{r.stdout}\n{r.stderr}"
