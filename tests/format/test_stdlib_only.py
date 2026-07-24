"""fritzreport und fritzformat müssen ohne Fremdpakete auskommen.

Das ist kein Schönheitswunsch: das Report-Binary soll unabhängig von einer
TLS-/HTTP-Bibliothek bleiben, und fritzformat wird von beiden Werkzeugen
importiert — zöge es etwas Fremdes herein, wäre fritzreport es sofort mit los.
Geprüft wird statisch über den AST, nicht über Laufzeit-Imports.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
STDLIB_ONLY_PACKAGES = ["fritzformat", "fritzreport"]

#: Eigene Pakete, die diese Module importieren dürfen.
OWN_PACKAGES = {"fritzformat", "fritzreport"}


def _toplevel_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # level > 0 ist ein relativer Import innerhalb des eigenen Pakets
            if node.level == 0 and node.module:
                found.add(node.module.split(".")[0])
    return found


@pytest.mark.parametrize("package", STDLIB_ONLY_PACKAGES)
def test_keine_fremdpakete(package: str) -> None:
    allowed = set(sys.stdlib_module_names) | OWN_PACKAGES
    offenders: dict[str, set[str]] = {}
    for py in sorted((REPO_ROOT / package).rglob("*.py")):
        fremd = _toplevel_imports(py) - allowed
        if fremd:
            offenders[str(py.relative_to(REPO_ROOT))] = fremd
    assert not offenders, (
        f"{package} muss stdlib-only bleiben, importiert aber Fremdpakete: {offenders}"
    )


def test_requests_ist_im_export_erlaubt() -> None:
    """Gegenprobe: der Wächter oben ist scharf, nicht zufällig immer grün."""
    imports: set[str] = set()
    for py in sorted((REPO_ROOT / "fritzexport").rglob("*.py")):
        imports |= _toplevel_imports(py)
    assert "requests" in imports, "fritzexport sollte requests verwenden — Test greift ins Leere"
