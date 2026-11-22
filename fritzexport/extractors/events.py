"""System-Ereignislog — data.lua page=log, alle Kategorien."""
from __future__ import annotations

import logging
from typing import TypedDict

from fritzformat import RawJson

from ..client import FritzClient

log = logging.getLogger(__name__)

DATA_PATH = "/data.lua"

# filter=0 holt alle Ereignisse; die Kategorie-Filter fangen Einträge ab,
# die manche Firmware-Versionen nur in der Kategorie, nicht in "all" liefern.
_FILTERS: dict[str, str] = {
    "all":  "0",
    "sys":  "sys",
    "net":  "net",
    "wlan": "wlan",
    "fon":  "fon",
    "usb":  "usb",
}


class LogLine(TypedDict):
    """Eine Zeile des Ereignisprotokolls, wie ein Filter sie liefert."""
    date: str
    time: str
    message: str
    id: int | str            # Zahl von der Box; "" wenn die Spalte fehlt
    category: str
    raw: list[object] | RawJson   # die Zeile unverändert: Liste oder Objekt, je nach Firmware


class EventRecord(LogLine):
    found_in_filters: list[str]


def _fetch(client: FritzClient, filter_val: str) -> list[LogLine]:
    try:
        resp = client.post(DATA_PATH, data={"page": "log", "xhr": "1", "filter": filter_val})
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:  # noqa: BLE001 - ein Filter fällt aus, die übrigen laufen weiter
        log.debug("events filter=%s fehlgeschlagen: %s", filter_val, e)
        return []
    data = payload.get("data") or {}
    raw = data.get("log") or []
    events: list[LogLine] = []
    for row in raw:
        if isinstance(row, list):
            events.append(
                {
                    "date":     row[0] if len(row) > 0 else "",
                    "time":     row[1] if len(row) > 1 else "",
                    "message":  row[2] if len(row) > 2 else "",
                    "id":       row[3] if len(row) > 3 else "",
                    "category": row[4] if len(row) > 4 else "",
                    "raw": row,
                }
            )
        elif isinstance(row, dict):
            events.append(
                {
                    "date":     row.get("date", ""),
                    "time":     row.get("time", ""),
                    "message":  row["msg"] if "msg" in row else row.get("message", ""),
                    "id":       row.get("id", ""),
                    "category": row["group"] if "group" in row else row.get("category", ""),
                    "raw": row,
                }
            )
    return events


def extract(client: FritzClient) -> list[EventRecord]:
    """Ereignisse aller Filter, ein Datensatz je Logzeile.

    Dasselbe Ereignis kann in mehreren Filtern stehen (``all`` und ``sys``) und wird
    dann zusammengeführt. Gleiche Zeilen *innerhalb* einer Antwort sind dagegen
    verschiedene Ereignisse, etwa zwei Anmeldeversuche in derselben Sekunde (#62).
    Deshalb zählt der Schlüssel das Vorkommen mit: das n-te Vorkommen in einem
    Filter gehört zum n-ten in einem anderen, und es bleiben so viele Datensätze,
    wie der ergiebigste Filter Zeilen hatte.
    """
    seen: dict[tuple[str, str, str, int], EventRecord] = {}
    for filter_name, filter_val in _FILTERS.items():
        vorkommen: dict[tuple[str, str, str], int] = {}
        for event in _fetch(client, filter_val):
            zeile = (event["date"], event["time"], event["message"])
            n = vorkommen.get(zeile, 0)
            vorkommen[zeile] = n + 1
            key = (*zeile, n)
            if key in seen:
                seen[key]["found_in_filters"].append(filter_name)
            else:
                seen[key] = {**event, "found_in_filters": [filter_name]}
    return list(seen.values())
