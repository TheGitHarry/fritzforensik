"""WLAN-/Netzwerk-Geräteliste — data.lua page=netDev (active + passive)."""
from __future__ import annotations

from ..client import FritzClient

DATA_PATH = "/data.lua"


def _normalize(entry: dict, status: str) -> dict:
    ipv4 = entry.get("ipv4") if isinstance(entry.get("ipv4"), dict) else {}
    ipv6 = entry.get("ipv6") if isinstance(entry.get("ipv6"), dict) else {}
    options = entry.get("options") if isinstance(entry.get("options"), dict) else {}
    return {
        "status": status,
        "name": entry.get("name", ""),
        "mac": entry.get("mac", ""),
        "ipv4": ipv4.get("ip", "") or entry.get("ip", ""),
        "ipv6": ipv6.get("ip", ""),
        "interface": entry.get("conn", "") or entry.get("type", ""),
        "port": entry.get("port", ""),
        "speed": entry.get("speed", ""),
        "is_guest": bool(options.get("guest", entry.get("guest", False))),
        "uid": entry.get("UID", ""),
        "last_seen": ipv4.get("lastused", "") or entry.get("lastused", "") or entry.get("last_used", ""),
        "raw": entry,
    }


def extract(client: FritzClient) -> list[dict]:
    resp = client.post(
        DATA_PATH,
        data={"page": "netDev", "xhr": "1", "xhrId": "all", "lang": "de"},
    )
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
