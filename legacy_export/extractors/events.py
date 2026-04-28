"""System-Ereignislog — data.lua page=log."""
from __future__ import annotations

from ..client import FritzClient

DATA_PATH = "/data.lua"


def extract(client: FritzClient) -> list[dict]:
    resp = client.post(DATA_PATH, data={"page": "log", "xhr": "1", "filter": "0"})
    resp.raise_for_status()
    try:
        payload = resp.json()
    except ValueError:
        return []
    data = payload.get("data") or {}
    raw = data.get("log") or []
    events: list[dict] = []
    for row in raw:
        if isinstance(row, list):
            events.append(
                {
                    "date": row[0] if len(row) > 0 else "",
                    "time": row[1] if len(row) > 1 else "",
                    "message": row[2] if len(row) > 2 else "",
                    "id": row[3] if len(row) > 3 else "",
                    "category": row[4] if len(row) > 4 else "",
                    "raw": row,
                }
            )
        elif isinstance(row, dict):
            events.append(
                {
                    "date": row.get("date", ""),
                    "time": row.get("time", ""),
                    "message": row.get("msg", row.get("message", "")),
                    "id": row.get("id", ""),
                    "category": row.get("group", row.get("category", "")),
                    "raw": row,
                }
            )
    return events
