#!/usr/bin/env python3
"""Erzeugt ABDECKUNG.md aus einem Verzeichnis mit Bundles.

    python3 scripts/abdeckung.py ~/testdata/_work > ABDECKUNG.md

Die Matrix ist zur **Veröffentlichung** bestimmt: Sie zeigt, welche
Modell-/Firmware-Kombinationen schon einmal ausgelesen wurden und welche
Datenarten dabei tatsächlich Datensätze geliefert haben. Daraus kann ein
Außenstehender ablesen, ob ein Abzug seiner Box dem Projekt weiterhilft.

Bewusst NICHT ausgegeben werden Seriennummern, Aktenzeichen, Hostnamen, IPs
und absolute Datensatzzahlen — letztere lassen Rückschlüsse auf den
Haushalt zu (Zahl der Geräte, Anrufe). Es steht nur da, *ob* eine Datenart
Daten lieferte, nie wie viele. Eine Gegenprobe darauf steht in
tests/format/test_abdeckung.py.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from fritzformat.names import JSON_TYPES, SUPPORT_VARIANTS  # noqa: E402

#: HWRevision → Handelsname. Aus den Supportdaten ist nur die Revision
#: sicher ablesbar; das Modell steht dort nicht durchgängig als Klartext.
HWREV_MODELL = {
    "185": "FRITZ!Box 7490",
    "226": "FRITZ!Box 7590",
    "256": "FRITZ!Box 7530 AX",
    "285": "FRITZ!Box 7690",
}


def _erste_zeilen(pfad: Path, anzahl: int = 400) -> list[str]:
    with pfad.open(encoding="utf-8", errors="replace") as f:
        return [zeile for _, zeile in zip(range(anzahl), f)]


def firmware_kurz(roh: str) -> str:
    """``285.08.25,slot0=…,slot1=…`` → ``08.25``.

    ``firmware_info`` führt hinter einem Komma die Inhalte beider Flash-Slots
    des Dual-Boot-Systems auf. Die sind hier nicht nur überflüssig breit,
    sondern schädlich: Zwei Boxen mit demselben FRITZ!OS-Stand hätten je nach
    Slot-Belegung verschiedene Werte und würden in der Matrix als
    unterschiedliche Zeilen erscheinen. Vor dem Komma steht
    ``<HWRevision>.<FRITZ!OS>``; die Revision hat eine eigene Spalte.
    """
    kern = roh.split(",", 1)[0].strip()
    teile = kern.split(".")
    return ".".join(teile[1:]) if len(teile) >= 3 else kern


def _feld(zeilen: list[str], name: str) -> str:
    """Tab-getrenntes Feld aus dem Kopf der Supportdaten ziehen."""
    muster = re.compile(rf"^{re.escape(name)}\t(.+)$")
    for zeile in zeilen:
        treffer = muster.match(zeile.rstrip("\n"))
        if treffer:
            return treffer.group(1).strip()
    return ""


def lies_bundle(verzeichnis: Path) -> dict | None:
    """Liest die veröffentlichbaren Merkmale eines Bundles."""
    standard = sorted(verzeichnis.glob("supportdata_standard_*.txt"))
    if not standard:
        return None
    kopf = _erste_zeilen(standard[0])

    hwrev = _feld(kopf, "HWRevision")
    befund = {
        "hwrev": hwrev,
        "modell": HWREV_MODELL.get(hwrev, f"unbekannt (HWRevision {hwrev})"),
        "firmware": firmware_kurz(_feld(kopf, "firmware_info")),
        "datenarten": {},
        "support": sorted(
            v for v in SUPPORT_VARIANTS if list(verzeichnis.glob(f"supportdata_{v}_*.txt"))
        ),
    }

    for art in JSON_TYPES:
        treffer = sorted(verzeichnis.glob(f"*_{art}.json"))
        if not treffer:
            befund["datenarten"][art] = "fehlt"
            continue
        try:
            daten = json.loads(treffer[0].read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError):
            befund["datenarten"][art] = "fehlt"
            continue
        satz = daten.get("records")
        # Nur ob, nicht wie viele — die Zahl bliebe sonst ein Rückschluss
        # auf den Haushalt.
        befund["datenarten"][art] = "ja" if isinstance(satz, list) and satz else "leer"
    return befund


def gruppiere(befunde: list[dict]) -> dict[tuple[str, str], list[dict]]:
    """Nach Modell+Firmware bündeln — mehrere Abzüge derselben Box sind eine Zeile."""
    gruppen: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for b in befunde:
        gruppen[(b["modell"], b["firmware"])].append(b)
    return gruppen


SYMBOL = {"ja": "✓", "leer": "○", "fehlt": "—"}


def zusammenfassen(eintraege: list[dict], art: str) -> str:
    """Bestes Ergebnis über alle Abzüge einer Modell-/Firmware-Kombination."""
    werte = {e["datenarten"].get(art, "fehlt") for e in eintraege}
    for rang in ("ja", "leer", "fehlt"):
        if rang in werte:
            return SYMBOL[rang]
    return SYMBOL["fehlt"]


def erzeuge(befunde: list[dict]) -> str:
    gruppen = gruppiere(befunde)
    zeilen: list[str] = []
    a = zeilen.append

    a("# Abdeckung: getestete Boxen und Datenarten")
    a("")
    a("Welche FRITZ!Box-Modelle mit welchem FRITZ!OS-Stand bereits ausgelesen wurden —")
    a("und welche Datenarten dabei tatsächlich Daten geliefert haben.")
    a("")
    a("**Diese Datei wird erzeugt, nicht von Hand gepflegt:**")
    a("")
    a("```bash")
    a("python3 scripts/abdeckung.py <verzeichnis-mit-bundles> > ABDECKUNG.md")
    a("```")
    a("")
    a("| Zeichen | Bedeutung |")
    a("|---|---|")
    a("| ✓ | Datenart lieferte Datensätze |")
    a("| ○ | abgefragt, kam aber leer zurück |")
    a("| — | in diesem Abzug nicht enthalten |")
    a("")
    a("Ein ○ ist nicht zwingend ein Fehler — eine Box ohne Anrufbeantworter liefert bei")
    a("`tam` zu Recht nichts. Es heißt nur: an dieser Kombination ist der Codepfad noch")
    a("nie mit echten Daten gelaufen.")
    a("")

    kopf = "| Modell | HWRev | FRITZ!OS | Abzüge | " + " | ".join(JSON_TYPES) + " |"
    a(kopf)
    a("|---" * (4 + len(JSON_TYPES)) + "|")
    for (modell, firmware), eintraege in sorted(gruppen.items()):
        felder = [zusammenfassen(eintraege, art) for art in JSON_TYPES]
        a(f"| {modell} | {eintraege[0]['hwrev']} | {firmware} | {len(eintraege)} | "
          + " | ".join(felder) + " |")
    a("")

    a("## Supportdaten-Varianten")
    a("")
    a("| Modell | FRITZ!OS | " + " | ".join(SUPPORT_VARIANTS) + " |")
    a("|---" * (2 + len(SUPPORT_VARIANTS)) + "|")
    for (modell, firmware), eintraege in sorted(gruppen.items()):
        vorhanden = {v for e in eintraege for v in e["support"]}
        felder = ["✓" if v in vorhanden else "—" for v in SUPPORT_VARIANTS]
        a(f"| {modell} | {firmware} | " + " | ".join(felder) + " |")
    a("")

    # Lücken: Datenarten, die NIRGENDS Daten lieferten, sind die wertvollsten
    # Hinweise für Beitragende — dort ist der Codepfad faktisch ungetestet.
    nie = [art for art in JSON_TYPES
           if all(e["datenarten"].get(art) != "ja" for e in befunde)]
    teils = [art for art in JSON_TYPES
             if art not in nie and any(e["datenarten"].get(art) != "ja" for e in befunde)]

    a("## Wo Abzüge dem Projekt am meisten helfen")
    a("")
    if nie:
        a("**Bisher in keinem einzigen Abzug mit Daten gesehen** — hier ist der Codepfad")
        a("faktisch ungetestet:")
        a("")
        for art in nie:
            a(f"- `{art}`")
        a("")
    if teils:
        a("**Nur auf einem Teil der Modelle mit Daten gesehen** — Abzüge der übrigen")
        a("Modelle schließen die Lücke:")
        a("")
        for art in teils:
            mit = sorted({e["modell"] for e in befunde if e["datenarten"].get(art) == "ja"})
            a(f"- `{art}` — bisher nur: {', '.join(mit)}")
        a("")

    fehlende = sorted(set(HWREV_MODELL.values()) - {b["modell"] for b in befunde})
    a("Ebenso wertvoll: **jedes Modell, das oben noch gar nicht steht**, und jeder")
    a("deutlich abweichende FRITZ!OS-Stand eines schon gelisteten Modells.")
    if fehlende:
        a("")
        a("Bekannt, aber noch nicht abgedeckt: " + ", ".join(fehlende) + ".")
    a("")
    a("Ein Abzug enthält personenbezogene Daten und gehört **nicht** in ein öffentliches")
    a("Issue. Der Weg für eine Kontaktaufnahme steht in [SECURITY.md](SECURITY.md).")
    return "\n".join(zeilen) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    wurzel = Path(argv[1]).expanduser()
    if not wurzel.is_dir():
        print(f"Kein Verzeichnis: {wurzel}", file=sys.stderr)
        return 2

    befunde = [b for b in (lies_bundle(p) for p in sorted(wurzel.iterdir()) if p.is_dir()) if b]
    if not befunde:
        print(f"Keine auswertbaren Bundles in {wurzel}", file=sys.stderr)
        return 1
    print(erzeuge(befunde), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
