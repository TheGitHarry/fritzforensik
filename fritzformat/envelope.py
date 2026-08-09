"""Hüllformat der JSON-Datenarten.

Jede Datenart liegt als JSON-Objekt mit festem Kopf vor::

    {"tool": …, "version": …, "host": …, "extracted_at": …,
     "type": …, "records": [ … ]}

Optional kommen ``discovery`` (Fundumstände der Box) und
extractor-spezifische Zusatzfelder hinzu.
"""
from __future__ import annotations

import datetime as _dt

#: Pflichtfelder des Kopfes, in Schreibreihenfolge.
ENVELOPE_KEYS = ("tool", "version", "host", "extracted_at", "type", "records")


def utc_now_iso() -> str:
    """``2026-07-24T10:15:30Z`` — für Zeitstempel *im* Dokument."""
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_now_compact() -> str:
    """``20260724T101530Z`` — für Zeitstempel *in Dateinamen*."""
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def compact_from_iso(value: str) -> str:
    """``2026-07-24T10:15:30Z`` → ``20260724T101530Z``.

    Der Report kennt den Abzugszeitpunkt nur als ISO-Wert aus der Hülle
    (``extracted_at``), braucht ihn für den Dateinamen aber kompakt — sonst bilden
    Abzug und Report nicht denselben Namensstamm. Unbrauchbare Werte ergeben einen
    leeren String; der Aufrufer entscheidet dann über den Rückfall.

    Die **Millisekundenform** von `uhr_jetzt_iso` gehört ausdrücklich dazu: Der
    Supportdaten-Extractor datiert seine Rohdateien aus derselben Uhrablesung, mit der
    er die Marke ins Sitzungslog schreibt. Zwei Ablesungen könnten über eine
    Sekundengrenze fallen und denselben Abruf verschieden datieren.
    """
    raw = (value or "").strip()
    if not raw:
        return ""
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            return _dt.datetime.strptime(raw, fmt).strftime("%Y%m%dT%H%M%SZ")
        except ValueError:
            continue
    return ""


def build_envelope(
    tool: str,
    version: str,
    host: str,
    type_name: str,
    records: list[dict],
    extracted_at: str | None = None,
    discovery_meta: dict | None = None,
    extra_meta: dict | None = None,
) -> dict:
    """Baut den vollständigen Datensatz einer Datenart."""
    payload: dict = {
        "tool": tool,
        "version": version,
        "host": host,
        "extracted_at": extracted_at or utc_now_iso(),
        "type": type_name,
        "records": records,
    }
    if discovery_meta:
        payload["discovery"] = discovery_meta
    if extra_meta:
        payload.update(extra_meta)
    return payload


def read_envelope_meta(data: dict) -> dict:
    """Liest den Kopf einer geladenen Datenart heraus (fehlende Felder → "")."""
    data = data or {}
    return {
        "tool": data.get("tool", ""),
        "version": data.get("version", ""),
        "host": data.get("host", ""),
        "extracted_at": data.get("extracted_at", ""),
    }
