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
