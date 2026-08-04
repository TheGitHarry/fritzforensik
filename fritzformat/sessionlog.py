"""Sicherungszeitraum im Sitzungslog.

``fritzexport`` protokolliert Beginn und Ende des Sicherungsvorgangs — erster bis
letzter Datenabruf — als eigene Markerzeilen; ``fritzreport`` liest sie daraus
zurück und weist den Zeitraum im Report aus. Das ist ein Vertrag **zwischen** den
Werkzeugen und steht deshalb hier, nicht in einer der CLIs.

Der Marker führt seinen **eigenen UTC-Wert** mit, statt sich auf den Zeitstempel am
Zeilenanfang zu verlassen: Den setzt ``logging`` in **Lokalzeit**, während alles
andere im Bundle UTC ist. Ein Report, der die Zeilenköpfe parste, mischte damit zwei
Zeitzonen.

Beispielzeile im Log::

    2026-07-13 11:34:58,004 INFO SICHERUNG BEGINN 2026-07-13T09:34:58Z
"""
from __future__ import annotations

import re

MARKER_BEGIN = "SICHERUNG BEGINN"
MARKER_END = "SICHERUNG ENDE"

#: Marker samt UTC-Wert irgendwo in der Zeile — der Zeilenkopf (Datum, Level) steht
#: davor und wird bewusst ignoriert.
_BEGIN_RE = re.compile(rf"{MARKER_BEGIN}\s+(\S+)")
_END_RE = re.compile(rf"{MARKER_END}\s+(\S+)")


def begin_line(iso: str) -> str:
    """Meldungstext für den Beginn — als ``log.info(...)`` zu schreiben."""
    return f"{MARKER_BEGIN} {iso}"


def end_line(iso: str) -> str:
    """Meldungstext für das Ende."""
    return f"{MARKER_END} {iso}"


def parse_span(text: str) -> tuple[str, str]:
    """Logtext → ``(beginn_iso, ende_iso)``; fehlende Werte als leerer String.

    Gutmütig, weil ein Log alles Mögliche enthalten kann:

    - keine Marker (Altbestand, vor Einführung dieser Zeilen) → ``("", "")``
    - nur Beginn (Lauf abgebrochen, abgestürzt, Strg-C) → ``(beginn, "")``
    - mehrfach vorhanden → **erster** Beginn und **letztes** Ende, damit ein Log mit
      mehreren Läufen den gesamten Zeitraum abdeckt statt nur den letzten
    """
    if not text:
        return "", ""
    begins = _BEGIN_RE.findall(text)
    ends = _END_RE.findall(text)
    return (begins[0] if begins else "", ends[-1] if ends else "")
