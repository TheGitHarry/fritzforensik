"""Die Doku darf nicht vom Code weglaufen.

Genau das ist passiert, bevor es diese Tests gab: CONCEPT.md nannte einen
CI-Tag, den es nicht mehr gab, und eine Testanzahl, die seit Monaten falsch war.
Gefährlich ist davon vor allem eine Sorte Aussage — die **Belegtheits-Grade**.
Sie tragen im Gutachten das Gewicht, und ihre Bedeutung hat sich beim Umstieg
vom 4- auf das 3-Grade-System verschoben (alt D3 = „eigene Versuche" ist heute
D2). Eine Doku, die das falsch wiedergibt, lässt Badges in die belastende
Richtung fehllesen.

Geprüft wird deshalb statisch gegen die einzige Wahrheit im Code
(``fritzreport.model.GRADE_LABEL``) — kein Doku-Framework, nur Markdown-Parsing.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from fritzreport.model import GRADE_LABEL

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ANFORDERUNGEN = REPO_ROOT / "ANFORDERUNGEN.md"
README = REPO_ROOT / "README.md"

#: Zeile einer Markdown-Tabelle, deren erste Spalte ein Grad ist: | D1 | Text |
_GRADE_ROW = re.compile(r"^\|\s*\*{0,2}(D[1-9])\*{0,2}\s*\|\s*(.+?)\s*\|", re.MULTILINE)

#: Anforderungszeile: | ID | Anforderung | Status | Nachweis |
_REQ_ROW = re.compile(r"^\|\s*([A-H]-?\w+)\s*\|([^|]*)\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*$",
                      re.MULTILINE)

_STATUS = {"erfüllt", "erfüllt, angepasst", "offen", "entfällt"}


def _grade_rows(text: str) -> dict[str, str]:
    """Grad → Beschreibungstext, aus allen Grade-Tabellenzeilen einer Datei."""
    return {g: desc.strip().rstrip("|").strip() for g, desc in _GRADE_ROW.findall(text)}


def _testnamen_im_repo() -> set[str]:
    """Alle Testfunktionsnamen unter tests/ — statisch über den AST."""
    namen: set[str] = set()
    for py in sorted((REPO_ROOT / "tests").rglob("test_*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                namen.add(node.name)
    return namen


# ───────────────────────── Grade-Bedeutungen ─────────────────────────────────

@pytest.mark.parametrize("doc", [ANFORDERUNGEN, README], ids=lambda p: p.name)
def test_grade_texte_stimmen_mit_code(doc: Path) -> None:
    """Jede Grade-Tabelle in der Doku muss GRADE_LABEL wörtlich wiedergeben."""
    rows = _grade_rows(doc.read_text(encoding="utf-8"))
    assert rows, f"{doc.name}: keine Grade-Tabelle gefunden — Test greift ins Leere"

    for grad, text in rows.items():
        assert grad in GRADE_LABEL, (
            f"{doc.name} nennt Grad {grad}, den es im Code nicht gibt. "
            f"Bekannt sind: {sorted(GRADE_LABEL)}. Stammt die Zeile aus dem alten "
            f"4-Grade-Schema?"
        )
        assert text == GRADE_LABEL[grad], (
            f"{doc.name}: Bedeutung von {grad} weicht vom Code ab.\n"
            f"  Doku: {text!r}\n  Code: {GRADE_LABEL[grad]!r}\n"
            f"Einzige Wahrheit ist fritzreport/model.py::GRADE_LABEL."
        )

    fehlend = set(GRADE_LABEL) - set(rows)
    assert not fehlend, f"{doc.name}: Grade ohne Eintrag in der Tabelle: {sorted(fehlend)}"


def test_altes_vier_grade_schema_wird_nicht_als_gueltig_dargestellt() -> None:
    """D4 darf in ANFORDERUNGEN.md nur in der Umrechnung vorkommen, nie als gültiger Grad."""
    rows = _grade_rows(ANFORDERUNGEN.read_text(encoding="utf-8"))
    assert "D4" not in rows, (
        "ANFORDERUNGEN.md führt D4 in einer Grade-Tabelle. Das alte 4-Grade-Schema "
        "gilt nicht mehr — es gehört ausschließlich in den Umrechnungsblock."
    )


# ───────────────────────── Anforderungs-Nachweise ────────────────────────────

def test_nachweise_verweisen_auf_existierende_tests() -> None:
    """Jede in der Nachweisspalte genannte Testfunktion muss es wirklich geben."""
    vorhanden = _testnamen_im_repo()
    text = ANFORDERUNGEN.read_text(encoding="utf-8")
    tot: dict[str, str] = {}

    for req_id, _anf, _status, nachweis in _REQ_ROW.findall(text):
        for name in re.findall(r"`(test_\w+)`", nachweis):
            if name not in vorhanden:
                tot[req_id] = name

    assert not tot, (
        f"ANFORDERUNGEN.md verweist auf Testfunktionen, die es nicht (mehr) gibt: {tot}. "
        f"Wurde ein Test umbenannt?"
    )


def test_status_werte_sind_gueltig_und_vollstaendig() -> None:
    """Statuswerte aus der festen Liste; 'offen' braucht Issue-Nr., 'entfällt' eine Begründung."""
    text = ANFORDERUNGEN.read_text(encoding="utf-8")
    rows = _REQ_ROW.findall(text)
    assert rows, "ANFORDERUNGEN.md: keine Anforderungszeilen gefunden — Test greift ins Leere"

    fehler: list[str] = []
    for req_id, _anf, status, nachweis in rows:
        status = status.strip()
        if status.startswith("ersetzt durch "):
            continue
        if status not in _STATUS:
            fehler.append(f"{req_id}: unbekannter Status {status!r}")
            continue
        if status == "offen" and not re.search(r"#\d+", nachweis):
            fehler.append(f"{req_id}: Status 'offen' ohne Issue-Nummer im Nachweis")
        if status == "entfällt" and len(nachweis.strip()) < 10:
            fehler.append(f"{req_id}: Status 'entfällt' ohne Begründung")

    assert not fehler, "ANFORDERUNGEN.md, Formfehler:\n  " + "\n  ".join(fehler)


def test_anforderungs_ids_sind_eindeutig() -> None:
    """IDs werden nie wiederverwendet — doppelte Vergabe wäre eine stille Fehlerquelle."""
    ids = [r[0] for r in _REQ_ROW.findall(ANFORDERUNGEN.read_text(encoding="utf-8"))]
    doppelt = {i for i in ids if ids.count(i) > 1}
    assert not doppelt, f"ANFORDERUNGEN.md vergibt IDs doppelt: {sorted(doppelt)}"
