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

#: Netzfähige Module der **Standardbibliothek**.
#:
#: Der Fremdpaket-Wächter oben greift hier nicht: ``sys.stdlib_module_names``
#: enthält ``socket``, ``urllib`` und Verwandte, ein Netzzugriff über die
#: stdlib liefe also unbemerkt durch. Für fritzreport ist das die
#: entscheidende Zusicherung — das Werkzeug wertet Beweismittel aus und darf
#: dabei nichts senden, weder an einen Update-Dienst noch sonstwohin.
#: fritzformat steht mit auf der Liste, weil fritzreport es importiert.
#: Nicht enthalten ist ``webbrowser``: ``fritzreport --open`` öffnet damit den
#: fertigen Report als ``file://``-URI im lokalen Browser. Das startet ein
#: lokales Programm und sendet nichts — die Zusicherung bleibt gewahrt.
NETZ_MODULE = {
    "socket", "ssl", "urllib", "http", "ftplib", "smtplib", "poplib",
    "imaplib", "telnetlib", "nntplib", "socketserver", "xmlrpc",
    "asyncio", "selectors", "asyncore", "asynchat",
    "requests", "httpx", "aiohttp", "urllib3",
}


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


def _dynamische_imports(tree: ast.AST) -> set[str]:
    """Modulnamen aus ``importlib.import_module("x")`` und ``__import__("x")``.

    Ein reiner AST-Import-Check ließe sich damit umgehen; erfasst werden
    deshalb auch diese beiden Formen — jedenfalls, solange der Name als
    Zeichenkette dasteht.
    """
    gefunden: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        ziel = node.func
        name = (
            ziel.attr if isinstance(ziel, ast.Attribute)
            else ziel.id if isinstance(ziel, ast.Name)
            else ""
        )
        if name in {"import_module", "__import__"}:
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                gefunden.add(arg.value.split(".")[0])
    return gefunden


@pytest.mark.parametrize("package", STDLIB_ONLY_PACKAGES)
def test_kein_netzzugriff(package: str) -> None:
    """fritzreport darf nichts senden — auch nicht über die Standardbibliothek.

    Das ist die Zusicherung, die README und ABDECKUNG.md nach außen geben
    („spricht nicht mit einem Dienst"). Eine Zusage, die kein Test bewacht,
    ist bei einem Werkzeug zur Beweismittelauswertung wertlos.
    """
    treffer: dict[str, set[str]] = {}
    for py in sorted((REPO_ROOT / package).rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        module = _toplevel_imports(py) | _dynamische_imports(tree)
        netz = module & NETZ_MODULE
        if netz:
            treffer[str(py.relative_to(REPO_ROOT))] = netz
    assert not treffer, (
        f"{package} darf keine netzfähigen Module verwenden, tut es aber: {treffer}. "
        "README und ABDECKUNG.md sagen zu, dass das Werkzeug nichts sendet."
    )


def test_netzwaechter_ist_scharf() -> None:
    """Gegenprobe: der Wächter oben erkennt Netzmodule wirklich.

    fritzexport MUSS mit der Box sprechen — dort müssen also Treffer
    entstehen. Bleibt das aus, prüft der Wächter ins Leere.
    """
    module: set[str] = set()
    for py in sorted((REPO_ROOT / "fritzexport").rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        module |= _toplevel_imports(py) | _dynamische_imports(tree)
    assert module & NETZ_MODULE, (
        "fritzexport verwendet laut Wächter keine netzfähigen Module — "
        "dann greift die Erkennung nicht."
    )
