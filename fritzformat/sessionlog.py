"""Zeitmarken im Sitzungslog.

``fritzexport`` protokolliert zwei Dinge als eigene Markerzeilen, ``fritzreport``
liest sie zurück — ein Vertrag **zwischen** den Werkzeugen, der deshalb hier steht
und nicht in einer der CLIs:

1. **Sicherungszeitraum** — erster bis letzter Datenabruf (``SICHERUNG BEGINN/ENDE``).
2. **Uhrzeit-Klammern** — Referenzzeit unmittelbar vor und nach einem Abruf, aus dem
   sich die Box-Zeit ablesen lässt (``UHRZEIT ANFRAGE/ANTWORT``). Der Report bildet
   daraus den Versatz der Box-Uhr gegen die Uhr der Abzugsmaschine.

Jeder Marker führt seinen **eigenen UTC-Wert** mit, statt sich auf den Zeitstempel am
Zeilenanfang zu verlassen: Den setzt ``logging`` in **Lokalzeit**, während alles
andere im Bundle UTC ist. Ein Report, der die Zeilenköpfe parste, mischte damit zwei
Zeitzonen.

Beispielzeilen im Log::

    2026-07-13 11:34:58,004 INFO SICHERUNG BEGINN 2026-07-13T09:34:58Z
    2026-08-08 00:01:36,323 INFO UHRZEIT ANFRAGE supportdata:standard 2026-08-07T22:01:36Z
    2026-08-08 00:03:29,780 INFO UHRZEIT ANTWORT supportdata:standard 2026-08-07T22:03:29Z
"""
from __future__ import annotations

import datetime as _dt
import re

MARKER_BEGIN = "SICHERUNG BEGINN"
MARKER_END = "SICHERUNG ENDE"

#: Klammer um einen Abruf, aus dem die Box-Zeit hervorgeht. Die Quellenkennung
#: (``tr064:time``, ``supportdata:standard`` …) steht zwischen Marker und UTC-Wert,
#: damit der Report Marker und Messung ohne Raten einander zuordnen kann.
MARKER_UHR_ANFRAGE = "UHRZEIT ANFRAGE"
MARKER_UHR_ANTWORT = "UHRZEIT ANTWORT"

#: Marker samt UTC-Wert irgendwo in der Zeile — der Zeilenkopf (Datum, Level) steht
#: davor und wird bewusst ignoriert.
_BEGIN_RE = re.compile(rf"{MARKER_BEGIN}\s+(\S+)")
_END_RE = re.compile(rf"{MARKER_END}\s+(\S+)")

#: Wie oben, aber mit Quellenkennung vor dem UTC-Wert: (quelle, iso).
_UHR_ANFRAGE_RE = re.compile(rf"{MARKER_UHR_ANFRAGE}\s+(\S+)\s+(\S+)")
_UHR_ANTWORT_RE = re.compile(rf"{MARKER_UHR_ANTWORT}\s+(\S+)\s+(\S+)")


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


def uhr_jetzt_iso() -> str:
    """``2026-08-09T17:47:11.412Z`` — Referenzzeit für eine Uhr-Klammer.

    Bewusst **feiner** als `utc_now_iso`: Deren Sekundenauflösung schlüge doppelt auf
    die Breite der Klammer durch und machte selbst einen 50-ms-Abruf zu einer
    2-Sekunden-Unschärfe. Für Zeitstempel *im Dokument* bleibt `utc_now_iso`
    maßgeblich — das Format dort ist Teil des Bundle-Vertrags.
    """
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def uhr_anfrage_line(quelle: str, iso: str) -> str:
    """Meldungstext unmittelbar **vor** dem Abruf — als ``log.info(...)`` zu schreiben."""
    return f"{MARKER_UHR_ANFRAGE} {quelle} {iso}"


def uhr_antwort_line(quelle: str, iso: str) -> str:
    """Meldungstext unmittelbar **nach** dem Abruf."""
    return f"{MARKER_UHR_ANTWORT} {quelle} {iso}"


def parse_uhr_spans(text: str) -> dict[str, tuple[str, str]]:
    """Logtext → ``{quelle: (anfrage_iso, antwort_iso)}``; Fehlendes als leerer String.

    Gutmütig wie `parse_span`:

    - keine Marker (Altbestand) → ``{}``
    - nur Anfrage (Abruf abgebrochen, Timeout) → ``(anfrage, "")``
    - nur Antwort (soll nicht vorkommen) → ``("", antwort)``

    Anders als `parse_span` gewinnt hier je Quelle das **letzte** Paar, nicht das
    erste: Der Supportdaten-Extractor ruft die erweiterte Variante zweimal ab (erst
    direkt, dann nach Tastendruck), und abgelegt wird die Datei des zweiten Abrufs.
    Das erste Paar gehört zu einer Antwort, die verworfen wurde — es zu nehmen
    verklammerte die Messung mit dem falschen Zeitraum.
    """
    if not text:
        return {}
    spans: dict[str, list[str]] = {}
    for quelle, iso in _UHR_ANFRAGE_RE.findall(text):
        spans.setdefault(quelle, ["", ""])[0] = iso
    for quelle, iso in _UHR_ANTWORT_RE.findall(text):
        spans.setdefault(quelle, ["", ""])[1] = iso
    return {q: (v[0], v[1]) for q, v in spans.items()}
