"""fritzreport und fritzformat müssen ohne Fremdpakete auskommen.

Das ist kein Schönheitswunsch: das Report-Binary soll unabhängig von einer
TLS-/HTTP-Bibliothek bleiben, und fritzformat wird von beiden Werkzeugen
importiert — zöge es etwas Fremdes herein, wäre fritzreport es sofort mit los.
Geprüft wird statisch über den AST, nicht über Laufzeit-Imports.
"""
from __future__ import annotations

import ast
import re
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


#: Hosts, die im Export-Code als Zeichenkette stehen dürfen.
#:
#: ``fritz.box`` ist AVMs Standardname der Box im lokalen Netz.
#: ``schemas.xmlsoap.org`` sind XML-Namensräume im SOAP-Rumpf — Bezeichner,
#: die nie abgerufen werden. ``239.255.255.250`` ist die link-lokale
#: SSDP-Multicast-Adresse, die das eigene Netz nicht verlässt.
ERLAUBTE_HOSTS = {"fritz.box", "schemas.xmlsoap.org", "239.255.255.250"}

_HOST_IM_CODE = re.compile(r"https?://([a-zA-Z0-9.-]+)")


def test_export_kennt_keine_externe_gegenstelle() -> None:
    """fritzexport darf nur mit der Box sprechen, nicht mit dem Internet.

    Der Netzzugriff ist hier der Zweck — „sendet nichts" wäre falsch. Belastbar
    ist die engere Aussage: Es gibt **keine fest verdrahtete Gegenstelle**.
    Jede Adresse stammt aus ``--host`` oder aus der SSDP-Discovery im eigenen
    Netz; es gibt keinen Update-Check, keine Telemetrie, keinen Cloud-Dienst.

    Das ist bei einem Forensikwerkzeug wesentlich: Wer es im Netz eines
    Betroffenen einsetzt, muss wissen, dass dabei nichts nach außen geht.
    """
    treffer: dict[str, set[str]] = {}
    for py in sorted((REPO_ROOT / "fritzexport").rglob("*.py")):
        hosts = set(_HOST_IM_CODE.findall(py.read_text(encoding="utf-8")))
        fremd = hosts - ERLAUBTE_HOSTS
        if fremd:
            treffer[str(py.relative_to(REPO_ROOT))] = fremd
    assert not treffer, (
        f"fritzexport nennt fest verdrahtete Gegenstellen: {treffer}. "
        "Jede Adresse muss aus --host oder der Discovery stammen."
    )


def test_ssdp_bleibt_im_lokalen_netz() -> None:
    """Die Discovery darf nur link-lokal suchen.

    ``239.255.255.250`` ist per Definition nicht routbar; entscheidend ist
    zusätzlich die TTL. Ein hoher Wert würde die Suche über Router hinaus
    tragen — im Einsatz beim Betroffenen ein unerwünschter Nebeneffekt.
    """
    quelle = (REPO_ROOT / "fritzexport" / "discover.py").read_text(encoding="utf-8")
    assert 'SSDP_MULTICAST = "239.255.255.250"' in quelle, (
        "SSDP-Adresse geändert — ist sie noch link-lokal?"
    )
    tree = ast.parse(quelle)
    ttls = [
        node.args[2].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "setsockopt"
        and len(node.args) == 3
        and isinstance(node.args[1], ast.Attribute)
        and node.args[1].attr == "IP_MULTICAST_TTL"
        and isinstance(node.args[2], ast.Constant)
    ]
    assert ttls, "IP_MULTICAST_TTL wird nicht mehr gesetzt — Suche könnte weiter reichen"
    assert all(t <= 4 for t in ttls), f"SSDP-TTL zu hoch: {ttls}"


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
