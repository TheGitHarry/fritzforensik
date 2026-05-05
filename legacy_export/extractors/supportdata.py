"""Supportdaten — POST /cgi-bin/firmwarecfg, multipart/form-data.

Drei Varianten (je nach Firmware-Support), Reihenfolge nicht-interaktiv → interaktiv:
  * SupportData         — Standard-Diagnosebericht
  * MeshSupportData     — Mesh-Topologie-Diagnosedaten
  * SupportDataEnhanced — erweiterter Diagnosebericht, erfordert Tasten-Bestätigung an der Box

Ablage: Rohdatei als `supportdata_<typ>_<ts>.txt` + SHA256-Sidecar im output_dir.
Das JSON-Record enthält nur Metadaten (Typ, Pfad, Größe, Hash).
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import logging
import sys
import time
from pathlib import Path

from ..client import FritzClient

log = logging.getLogger(__name__)

FIRMWARECFG_PATH = "/cgi-bin/firmwarecfg"
ENHANCED_TIMEOUT_S = 30

_VARIANTS: list[tuple[str, str]] = [
    ("SupportData",         "standard"),
    ("MeshSupportData",     "mesh"),
    ("SupportDataEnhanced", "enhanced"),
]


def _utc_now_compact() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _wait_for_enter(timeout_seconds: int) -> bool:
    """Wartet auf Enter mit Sekundenanzeige auf stderr.

    True wenn Enter rechtzeitig gedrückt, False bei Timeout. Bei
    nicht-interaktivem stdin (Pipe, kein TTY) wird klassisch geblockt
    auf input() gewartet — automatisierte Aufrufe verhalten sich wie
    bisher.
    """
    if not (sys.stdin and sys.stdin.isatty()):
        try:
            input()
            return True
        except EOFError:
            return False

    if sys.platform.startswith("win"):
        return _wait_for_enter_windows(timeout_seconds)
    return _wait_for_enter_unix(timeout_seconds)


def _wait_for_enter_unix(timeout_seconds: int) -> bool:
    import select

    end = time.monotonic() + timeout_seconds
    last_shown = -1
    while True:
        remaining = end - time.monotonic()
        if remaining <= 0:
            sys.stderr.write("\r  Timeout — wird übersprungen.                    \n")
            sys.stderr.flush()
            return False
        rem_int = int(remaining) + 1
        if rem_int != last_shown:
            sys.stderr.write(f"\r  Noch {rem_int:2d} s — weiter mit Enter ... ")
            sys.stderr.flush()
            last_shown = rem_int
        ready, _, _ = select.select([sys.stdin], [], [], min(0.5, remaining))
        if ready:
            sys.stdin.readline()
            sys.stderr.write("\n")
            return True


def _wait_for_enter_windows(timeout_seconds: int) -> bool:
    import msvcrt  # nur auf Windows verfügbar

    end = time.monotonic() + timeout_seconds
    last_shown = -1
    while True:
        remaining = end - time.monotonic()
        if remaining <= 0:
            sys.stderr.write("\r  Timeout — wird übersprungen.                    \n")
            sys.stderr.flush()
            return False
        rem_int = int(remaining) + 1
        if rem_int != last_shown:
            sys.stderr.write(f"\r  Noch {rem_int:2d} s — weiter mit Enter ... ")
            sys.stderr.flush()
            last_shown = rem_int
        if msvcrt.kbhit():
            ch = msvcrt.getwch()
            if ch in ("\r", "\n"):
                sys.stderr.write("\n")
                return True
        time.sleep(0.05)


def _is_html(content: bytes) -> bool:
    snippet = content[:512].lstrip()
    return snippet.startswith(b"<!DOCTYPE") or snippet.startswith(b"<html")


def _fetch_one(client: FritzClient, field_name: str) -> bytes | None:
    """Lädt eine Supportdaten-Variante; gibt None bei HTML-Fehlerseite zurück."""
    resp = client.session.post(
        client.base_url + FIRMWARECFG_PATH,
        files={
            "sid": (None, client.sid),
            field_name: (None, ""),
        },
        timeout=120,
    )
    resp.raise_for_status()
    if _is_html(resp.content) or not resp.content.strip():
        return None
    return resp.content


def extract(
    client: FritzClient, output_dir: Path | None = None
) -> tuple[list[dict], dict]:
    """Lädt alle verfügbaren Supportdaten-Varianten und legt sie als Rohdateien ab.

    Gibt immer ein (records, extra_meta)-Tupel zurück.
    """
    ts = _utc_now_compact()
    records: list[dict] = []
    fetched: list[str] = []
    missing: list[str] = []

    for field_name, short_name in _VARIANTS:
        if field_name == "SupportDataEnhanced":
            sys.stderr.write(
                "\n"
                "HINWEIS: Erweiterte Supportdaten benötigen eine Bestätigung an der FRITZ!Box.\n"
                "  1. Drücken Sie einen der Knöpfe an der FRITZ!Box.\n"
                "  2. Klicken Sie im erscheinenden Bestätigungsdialog auf OK.\n"
                f"  Sie haben {ENHANCED_TIMEOUT_S} s; danach wird übersprungen.\n"
            )
            try:
                confirmed = _wait_for_enter(ENHANCED_TIMEOUT_S)
            except (EOFError, KeyboardInterrupt):
                log.warning("Erweiterte Supportdaten übersprungen (Abbruch durch Nutzer).")
                missing.append(short_name)
                continue
            if not confirmed:
                log.warning(
                    "Erweiterte Supportdaten übersprungen (Timeout %d s).",
                    ENHANCED_TIMEOUT_S,
                )
                missing.append(short_name)
                continue

        content = _fetch_one(client, field_name)
        if content is None:
            log.info("Supportdaten '%s': nicht verfügbar oder kein Recht.", field_name)
            missing.append(short_name)
            continue

        sha256 = hashlib.sha256(content).hexdigest()
        filename = f"supportdata_{short_name}_{ts}.txt"

        if output_dir is not None:
            output_dir.mkdir(parents=True, exist_ok=True)
            raw_path = output_dir / filename
            raw_path.write_bytes(content)
            sidecar = raw_path.with_suffix(".txt.sha256")
            sidecar.write_text(f"{sha256}  {filename}\n", encoding="utf-8")
            log.info(
                "Supportdaten '%s' gespeichert: %s (%d Bytes)",
                short_name, raw_path, len(content),
            )
            record: dict = {
                "type": short_name,
                "filename": filename,
                "size_bytes": len(content),
                "sha256": sha256,
            }
        else:
            try:
                text: str = content.decode("utf-8")
            except UnicodeDecodeError:
                text = content.decode("latin-1")
            record = {
                "type": short_name,
                "filename": filename,
                "size_bytes": len(content),
                "sha256": sha256,
                "content": text,
            }

        records.append(record)
        fetched.append(short_name)

    if not records:
        log.warning(
            "Supportdaten: alle Varianten lieferten HTML oder leer — "
            "User braucht das Recht 'FRITZ!Box-Einstellungen'."
        )

    extra_meta = {
        "supportdata_fetched": fetched,
        "supportdata_missing": missing,
    }
    return records, extra_meta
