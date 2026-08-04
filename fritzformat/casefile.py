"""Der Fallkopf ``case.json`` im Bundle.

Case-ID, Asservat-/Item-ID, Sachbearbeiter und Datum werden beim Abzug **einmal**
erfasst und reisen mit dem Bundle. ``fritzreport`` belegt seine Kopf-Abfrage damit
vor, statt dieselben Angaben ein zweites Mal zu verlangen.

Bewusst **ohne** Sidecar: Der Fallkopf ist eine Bearbeiterangabe, kein Beweismittel
aus der Box. Er wird nicht gegen einen Hash geprüft, weil er nachträglich korrigiert
werden können muss, ohne die Bundle-Integrität zu verletzen. Die Sidecars der
JSON-Datenarten bleiben davon unberührt.

Alle Felder sind optional — ein Feldeinsatz ohne bekannte Case-ID ist der Normalfall,
nicht der Fehler.
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path

#: Dateiname im Bundle-Wurzelverzeichnis.
CASE_FILENAME = "case.json"

#: Felder des Fallkopfs, in Erfassungsreihenfolge.
CASE_FIELDS = ["case_id", "item_id", "sb", "date"]


#: Beschriftung der Felder in der interaktiven Abfrage.
CASE_LABELS = {
    "case_id": "Case-ID",
    "item_id": "Asservat / Item-ID",
    "sb": "Sachbearbeiter (SB)",
    "date": "Datum",
}


def case_path(bundle_dir: Path | str) -> Path:
    return Path(bundle_dir) / CASE_FILENAME


def today() -> str:
    return _dt.date.today().isoformat()


def collect_case(args, *, defaults: dict | None = None, intro: str = "") -> dict:
    """Fallkopf erheben: CLI-Werte gewinnen, der Rest wird abgefragt.

    Beide Werkzeuge fragen dasselbe ab — die Funktion liegt deshalb hier und nicht
    zweimal in den CLIs. ``defaults`` belegt die Abfrage vor (``fritzreport`` reicht
    hier eine gelesene ``case.json`` herein); ohne TTY oder mit ``--no-prompt``
    werden die Vorgaben unverändert übernommen.
    """
    defaults = defaults or {}
    interactive = (not getattr(args, "no_prompt", False)
                   and sys.stdin is not None and sys.stdin.isatty()
                   and sys.stdout is not None and sys.stdout.isatty())

    def field(name: str) -> str:
        cli_val = getattr(args, name, None)
        if cli_val is not None:
            return cli_val
        default = defaults.get(name, "") or ("" if name != "date" else today())
        if not interactive:
            return default
        suffix = f" [{default}]" if default else ""
        try:
            ans = input(f"  {CASE_LABELS[name]}{suffix}: ").strip()
        except EOFError:
            ans = ""
        return ans or default

    if interactive and intro and all(
            getattr(args, a, None) is None for a in ("case_id", "item_id", "sb")):
        print(intro, file=sys.stderr)

    return {name: field(name) for name in CASE_FIELDS}


def build_case(case_id: str = "", item_id: str = "", sb: str = "",
               date: str = "", written_at: str = "") -> dict:
    """Fallkopf-Dict in der Form, wie es auf die Platte geht."""
    case = {
        "case_id": case_id or "",
        "item_id": item_id or "",
        "sb": sb or "",
        "date": date or "",
    }
    if written_at:
        case["written_at"] = written_at
    return case


def write_case(bundle_dir: Path | str, case: dict) -> Path:
    """Schreibt ``case.json`` und gibt den Pfad zurück."""
    p = case_path(bundle_dir)
    p.write_text(json.dumps(case, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def read_case(bundle_dir: Path | str) -> dict:
    """Liest ``case.json`` → Dict; **leeres Dict**, wenn nichts Brauchbares dasteht.

    Fehlt die Datei, ist sie kaputt oder enthält kein Objekt, wird das als „kein
    Fallkopf vorhanden" behandelt. Ein Bundle ohne Fallkopf ist gültig, und ein
    beschädigter Fallkopf darf den Report nicht verhindern — er ist eine
    Bequemlichkeit, keine Voraussetzung.
    """
    p = case_path(bundle_dir)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: str(data[k]) for k in CASE_FIELDS if isinstance(data.get(k), (str, int))}
