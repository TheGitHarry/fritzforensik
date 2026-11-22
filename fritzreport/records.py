"""Gemeinsame Felder der Report-Datensätze.

Eigenes Modul ohne weitere Importe: ``model`` und ``supportdata`` bauen beide
Datensätze auf dieser Grundlage, und ``bundle`` importiert ``supportdata`` — ein
Import aus ``model`` schlösse dort den Kreis.
"""
from __future__ import annotations

from typing import TypedDict


class Origin(TypedDict):
    """Fundstelle eines Datensatzes: Datei, Hash, Position und wörtlicher Auszug."""
    file: str
    sha: str
    idx: int | None
    total: int | None
    line: int | None
    line_end: int | None
    text: str


class FilterFields(TypedDict):
    """Felder, die jede Report-Tabelle trägt: Filter, Belegtheit, Fundstelle."""
    mac: str
    f_name: str
    f_phone: str
    f_ap: str
    f_iso: str
    grades: list[str]
    origin: Origin
