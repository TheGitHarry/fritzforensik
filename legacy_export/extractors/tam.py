"""Anrufbeantworter — TR-064 (X_AVM-DE_TAM:1) primary, Web-UI fallback.

Liefert pro Nachricht einen Metadaten-Record und schreibt das Audio (WAV)
in `<output_dir>/tam_audio/`. Bei TR-064 wird der `<New>`-Flag pre/post
verglichen und bei Drift mit `MarkMessage(MarkedAsRead=0)` restoriert —
für Web-UI-Fallback ist das nicht möglich, dann steht im Output-Hüllformat
`tam_state_preserved: false`.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from ..client import FritzClient, Tr064Disabled, Tr064Error

log = logging.getLogger(__name__)

TAM_SERVICE = "urn:dslforum-org:service:X_AVM-DE_TAM:1"
TAM_CONTROL = "/upnp/control/x_tam"
MAX_SLOTS = 5
TAM_LIST_PATH = "/fon_devices/tam_list.lua"
DATA_PATH = "/data.lua"

# AVM-spezifische TR-064 Out-of-Bounds-Codes (mapping aus Spezifikation
# "TR-064 Special Actions" — Index außerhalb der konfigurierten TAM-Anzahl)
_OOB_CODES = {713, 714, 820}

_GTABS_RE = re.compile(r"g_tabs\s*=\s*(\[.*?\])\s*;", re.DOTALL)


def _parse_message_xml(xml_text: str, tam_index: int) -> list[dict]:
    """XML-Format: <Root><Message><Index/>... <New/> <Path/> ...</Message></Root>."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    messages: list[dict] = []
    for m in root.iter("Message"):
        try:
            msg_idx = int((m.findtext("Index") or "0").strip())
        except ValueError:
            continue
        messages.append(
            {
                "tam_index": tam_index,
                "message_index": msg_idx,
                "date": (m.findtext("Date") or "").strip(),
                "duration": (m.findtext("Duration") or "").strip(),
                "caller_name": (m.findtext("Name") or "").strip(),
                "caller_number": (m.findtext("Number") or "").strip(),
                "called_number": (m.findtext("Called") or "").strip(),
                "in_phonebook": (m.findtext("Inbook") or "0").strip() == "1",
                "is_new": (m.findtext("New") or "0").strip() == "1",
                "audio_path": (m.findtext("Path") or "").strip(),
            }
        )
    return messages


def _download_audio_webui(client: FritzClient, audio_path: str) -> bytes:
    """Audio via Web-UI-SID (für Fallback-Pfad)."""
    if "?" in audio_path:
        path, _, query_str = audio_path.partition("?")
        params = dict(p.split("=", 1) for p in query_str.split("&") if "=" in p)
    else:
        path, params = audio_path, {}
    resp = client.get(path, params=params)
    resp.raise_for_status()
    return resp.content


def _download_audio_tr064(
    client: FritzClient, audio_path: str, list_sid: str
) -> bytes:
    """Audio via TR-064-Pseudo-SID auf Port 49000.

    TR-064 generiert für `GetMessageList` eine eigene SID, die nur auf
    Port 49000 (`/download.lua`) gilt — die Web-UI-SID auf 443 reicht
    nicht (404). Pfad und Query aus dem `<Path>`-Feld zusammensetzen.
    """
    if "?" in audio_path:
        path, _, query_str = audio_path.partition("?")
        params = dict(p.split("=", 1) for p in query_str.split("&") if "=" in p)
    else:
        path, params = audio_path, {}
    params["sid"] = list_sid
    resp = client.session.get(client.tr064_url(path), params=params, timeout=60)
    resp.raise_for_status()
    return resp.content


def _try_tr064(
    client: FritzClient, audio_dir: Path
) -> tuple[list[dict], dict]:
    audio_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    state_mutations: list[dict] = []
    state_preserved = True

    for slot in range(MAX_SLOTS):
        try:
            info = client.tr064_call(
                TAM_SERVICE, TAM_CONTROL, "GetInfo", {"NewIndex": str(slot)}
            )
        except Tr064Error as e:
            if e.error_code in _OOB_CODES:
                break  # höhere TAM-Slots existieren nicht mehr
            raise

        if info.get("NewEnable") != "1":
            log.info("TAM-Slot %d ist deaktiviert, überspringe", slot)
            continue

        log.info(
            "TAM-Slot %d: '%s' (Capacity %ss)",
            slot,
            info.get("NewName", ""),
            info.get("NewCapacity", "?"),
        )

        list_resp = client.tr064_call(
            TAM_SERVICE, TAM_CONTROL, "GetMessageList", {"NewIndex": str(slot)}
        )
        list_url = list_resp.get("NewURL", "")
        if not list_url:
            continue

        # SID für Audio-Download aus der Liste-URL extrahieren
        sid_match = re.search(r"[?&]sid=([0-9a-f]+)", list_url)
        list_sid = sid_match.group(1) if sid_match else ""

        # Pre-Snapshot
        pre_xml = client.session.get(list_url, timeout=30).text
        msgs = _parse_message_xml(pre_xml, slot)
        log.info("TAM-Slot %d: %d Nachrichten", slot, len(msgs))

        for msg in msgs:
            audio = _download_audio_tr064(client, msg["audio_path"], list_sid)
            fname = f"tam{slot:02d}_msg{msg['message_index']:03d}.wav"
            (audio_dir / fname).write_bytes(audio)
            msg["audio_file"] = f"tam_audio/{fname}"
            msg["audio_sha256"] = hashlib.sha256(audio).hexdigest()
            msg["audio_bytes"] = len(audio)

        # Post-Snapshot — wurde der New-Flag durch Download verändert?
        post_xml = client.session.get(list_url, timeout=30).text
        post_by_idx = {m["message_index"]: m for m in _parse_message_xml(post_xml, slot)}

        for msg in msgs:
            post = post_by_idx.get(msg["message_index"])
            if post is None:
                msg["state_restored"] = None
                continue
            if msg["is_new"] and not post["is_new"]:
                # Box hat impliziet markiert — restore
                try:
                    client.tr064_call(
                        TAM_SERVICE,
                        TAM_CONTROL,
                        "MarkMessage",
                        {
                            "NewIndex": str(slot),
                            "NewMessageIndex": str(msg["message_index"]),
                            "NewMarkedAsRead": "0",
                        },
                    )
                    msg["state_restored"] = True
                    state_mutations.append(
                        {
                            "tam_index": slot,
                            "message_index": msg["message_index"],
                            "action": "MarkMessage(MarkedAsRead=0)",
                            "reason": "auto-marked-by-download",
                        }
                    )
                except Tr064Error as e:
                    msg["state_restored"] = False
                    state_preserved = False
                    state_mutations.append(
                        {
                            "tam_index": slot,
                            "message_index": msg["message_index"],
                            "action": "MarkMessage(MarkedAsRead=0) FAILED",
                            "error": str(e),
                        }
                    )
            else:
                # Status unverändert — kein Restore nötig
                msg["state_restored"] = None

        records.extend(msgs)

    extra_meta = {
        "tam_method": "tr064",
        "tam_state_preserved": state_preserved,
        "tam_state_mutations": state_mutations,
    }
    return records, extra_meta


def _try_webui(client: FritzClient, audio_dir: Path) -> tuple[list[dict], dict]:
    """Web-UI-Fallback: parsing der HTML-Tabelle, kein State-Restore.

    Liest die Liste der TAM-Slots aus `g_tabs` der tam-Page und holt für
    jeden Slot die Tabelle aus `tam_list.lua`. Audio-Download-URLs werden
    aus `<a href="...">`-Attributen extrahiert.
    """
    audio_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []

    overview = client.post(
        DATA_PATH, data={"page": "tam", "xhr": "1", "xhrId": "all", "lang": "de"}
    )
    m = _GTABS_RE.search(overview.text)
    if not m:
        return records, {
            "tam_method": "webui",
            "tam_state_preserved": False,
            "tam_state_warning": "g_tabs nicht in tam-page gefunden",
        }
    try:
        tabs = json.loads(m.group(1))
    except ValueError:
        return records, {
            "tam_method": "webui",
            "tam_state_preserved": False,
            "tam_state_warning": "g_tabs ist kein gültiges JSON",
        }

    for tab in tabs:
        try:
            slot = int(tab.get("value", 0))
        except (TypeError, ValueError):
            continue
        page = client.get(TAM_LIST_PATH, params={"TamNr": str(slot)})
        rows = _parse_webui_rows(page.text, slot)
        for row in rows:
            if row.get("audio_path"):
                try:
                    audio = _download_audio_webui(client, row["audio_path"])
                    fname = f"tam{slot:02d}_msg{row['message_index']:03d}.wav"
                    (audio_dir / fname).write_bytes(audio)
                    row["audio_file"] = f"tam_audio/{fname}"
                    row["audio_sha256"] = hashlib.sha256(audio).hexdigest()
                    row["audio_bytes"] = len(audio)
                except Exception as e:
                    row["audio_error"] = str(e)
        records.extend(rows)

    return records, {
        "tam_method": "webui",
        "tam_state_preserved": False,
        "tam_state_warning": (
            "Web-UI-Fallback: read-Status kann nicht zurückgesetzt werden, "
            "falls die Box durch den Download den Flag verändert. Aktiviere "
            "TR-064 für deterministische Forensik."
        ),
    }


_ROW_RE = re.compile(
    r'<tr[^>]*>(?P<body>.*?)</tr>', re.DOTALL | re.IGNORECASE
)
_CELL_RE = re.compile(r'<td[^>]*>(?P<body>.*?)</td>', re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r'<[^>]+>')
_HREF_RE = re.compile(r'href="([^"]+)"', re.IGNORECASE)
_DOWNLOAD_RE = re.compile(r'/download\.lua\?[^"\'<> ]+')


def _strip_tags(html: str) -> str:
    return _TAG_RE.sub("", html).strip().replace("&nbsp;", " ").replace("&amp;", "&")


def _parse_webui_rows(html: str, tam_index: int) -> list[dict]:
    """Heuristischer Parser der `#uiTamCalls`-Tabelle."""
    table_m = re.search(
        r'<table[^>]*id=["\']?uiTamCalls["\']?[^>]*>(?P<body>.*?)</table>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if not table_m:
        return []
    rows: list[dict] = []
    seq = 0
    for row in _ROW_RE.finditer(table_m.group("body")):
        body = row.group("body")
        if "thead" in row.group(0).lower() or 'class="thead"' in row.group(0):
            continue
        cells = [c.group("body") for c in _CELL_RE.finditer(body)]
        if len(cells) < 4:
            continue
        # Audio-Pfad aus href
        audio_path = ""
        for c in cells:
            href_m = _HREF_RE.search(c)
            if href_m and "download" in href_m.group(1).lower():
                audio_path = _DOWNLOAD_RE.search(c).group(0) if _DOWNLOAD_RE.search(c) else href_m.group(1)
                break
        # Heuristische Spaltenzuordnung: Datum / Anrufer / eigene Nummer / Dauer
        # Erste Spalte ist oft das "neu"-Icon
        text_cols = [_strip_tags(c) for c in cells]
        rows.append(
            {
                "tam_index": tam_index,
                "message_index": seq,
                "date": text_cols[1] if len(text_cols) > 1 else "",
                "caller_name": text_cols[2] if len(text_cols) > 2 else "",
                "called_number": text_cols[3] if len(text_cols) > 3 else "",
                "duration": text_cols[4] if len(text_cols) > 4 else "",
                "is_new": "newicon" in body.lower() or "isNew" in body,
                "audio_path": audio_path,
            }
        )
        seq += 1
    return rows


def extract(
    client: FritzClient, audio_dir: Path | None = None
) -> tuple[list[dict], dict]:
    """Primary: TR-064 mit State-Restore. Fallback: Web-UI ohne Restore."""
    if audio_dir is None:
        audio_dir = Path(".") / "tam_audio"
    try:
        return _try_tr064(client, audio_dir)
    except Tr064Disabled as e:
        log.warning("TR-064 nicht verfügbar (%s) — Web-UI-Fallback", e)
        return _try_webui(client, audio_dir)
