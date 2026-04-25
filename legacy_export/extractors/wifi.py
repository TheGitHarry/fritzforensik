"""WLAN-/Netzwerk-Geräteliste — data.lua page=netDev (active + passive)."""
from __future__ import annotations

from ..client import FritzClient

DATA_PATH = "/data.lua"


def _normalize(entry: dict, status: str) -> dict:
    return {
        "status": status,
        "name": entry.get("name", ""),
        "mac": entry.get("mac", ""),
        "ipv4": (entry.get("ipv4") or {}).get("ip", "") if isinstance(entry.get("ipv4"), dict) else entry.get("ip", ""),
        "ipv6": (entry.get("ipv6") or {}).get("ip", "") if isinstance(entry.get("ipv6"), dict) else "",
        "interface": entry.get("conn", "") or entry.get("type", ""),
        "speed": entry.get("speed", ""),
        "is_guest": bool(entry.get("guest", False)),
        "first_seen": entry.get("firstseen", ""),
        "last_seen": entry.get("lastused", "") or entry.get("last_used", ""),
        "raw": entry,
    }


def extract(client: FritzClient) -> list[dict]:
    resp = client.post(DATA_PATH, data={"page": "netDev", "xhr": "1", "useajax": "1"})
    resp.raise_for_status()
    try:
        payload = resp.json()
    except ValueError:
        return []
    data = (payload.get("data") or {})
    active = data.get("active") or []
    passive = data.get("passive") or []
    devices: list[dict] = []
    for entry in active:
        if isinstance(entry, dict):
            devices.append(_normalize(entry, status="active"))
    for entry in passive:
        if isinstance(entry, dict):
            devices.append(_normalize(entry, status="passive"))
    return devices
