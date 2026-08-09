"""Dateinamen und Datenarten eines Bundles.

Ein Bundle ist ein Verzeichnis mit — je Datenart — einer
``fritzexport_<host>_<UTC>Z_<typ>.json`` samt ``.sha256``-Sidecar, dazu den
Roh-Supportdateien ``supportdata_<variante>_<UTC>Z.txt`` (+ Sidecar), einem
Sitzungs-Log und optional ``tam_audio/``.
"""
from __future__ import annotations

import re

#: Werkzeugkennung im Dateinamen und im Hüllformat (Feld ``tool``).
TOOL_NAME = "fritzexport"

#: Alle Datenarten, die als JSON im Bundle liegen. Maßgeblich für beide Seiten:
#: der Export erzeugt sie (ein Extractor je Eintrag), der Report sucht sie.
#: Ein Test hält diese Liste gegen die Extractor-Registry synchron.
JSON_TYPES = [
    "calls", "phonebook", "wifi", "events", "tam", "mesh", "hosts",
    "wan", "dhcp", "portforward", "storage", "supportdata", "tr069",
    "services", "boxtime", "deviceinfo",
]

#: Roh-Supportdaten-Varianten (Textdateien mit Sektionen / Logs).
SUPPORT_VARIANTS = ["standard", "mesh", "enhanced"]

#: Erkennungsmuster für ein Bundle-Verzeichnis.
BUNDLE_GLOB = f"{TOOL_NAME}_*_*.json"

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def slug_host(value: str) -> str:
    """Host für die Verwendung im Dateinamen entschärfen.

    Ein etwaiges Schema wird abgeschnitten, alles außerhalb von
    ``[A-Za-z0-9._-]`` zu ``_`` zusammengefasst.
    """
    if "://" in value:
        value = value.split("://", 1)[1]
    return _UNSAFE.sub("_", value).strip("_") or "host"


#: Verzeichnisname eines Abzugs ohne Fallkopf — auch Namensstamm des Reports.
RUN_FALLBACK = "export"


def run_slug(case_id: str = "", item_id: str = "", timestamp: str = "") -> str:
    """Gemeinsamer Namensstamm von Bundle-Verzeichnis und Report.

    ``<Case>_<Item>_<UTC>Z`` — leere Teile entfallen, ohne Fallkopf bleibt
    ``export_<UTC>Z``. Beide Werkzeuge bilden den Stamm hier und nicht jedes für
    sich, damit Abzug und Report am Namen zusammenfinden:

        C-2026-0815_A-01_20260804T184059Z/       (Bundle)
        C-2026-0815_A-01_20260804T184059Z.html   (Report)

    Der Zeitstempel stammt aus dem Abzug (Hüllfeld ``extracted_at`` bzw. der
    Laufzeitstempel) — er macht den Reportnamen zugleich kollisionsfrei, sodass
    ein zweiter Abzug desselben Asservats den ersten Report nicht überschreibt.
    """
    parts = [_UNSAFE.sub("-", p.strip()).strip("-")
             for p in (case_id, item_id) if p and p.strip()]
    stem = "_".join(p for p in parts if p) or RUN_FALLBACK
    ts = _UNSAFE.sub("-", timestamp.strip()).strip("-") if timestamp else ""
    return f"{stem}_{ts}" if ts else stem


def dataset_filename(host: str, timestamp: str, type_name: str) -> str:
    """``fritzexport_<host>_<UTC>Z_<typ>.json``"""
    return f"{TOOL_NAME}_{slug_host(host)}_{timestamp}_{type_name}.json"


def dataset_glob(type_name: str) -> str:
    """Suchmuster für eine Datenart.

    Bewusst ohne Werkzeug-Präfix (``*_<typ>.json``): der Host-Anteil im
    Dateinamen ist variabel, und die Datenart am Ende ist eindeutig genug.
    """
    return f"*_{type_name}.json"


def support_filename(variant: str, timestamp: str) -> str:
    """``supportdata_<variante>_<UTC>Z.txt``"""
    return f"supportdata_{variant}_{timestamp}.txt"


def support_glob(variant: str) -> str:
    return f"supportdata_{variant}_*.txt"


def session_log_filename(timestamp: str) -> str:
    """``fritzexport_<UTC>Z.log``"""
    return f"{TOOL_NAME}_{timestamp}.log"


def session_log_glob() -> str:
    return f"{TOOL_NAME}_*.log"
