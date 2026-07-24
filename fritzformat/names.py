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
