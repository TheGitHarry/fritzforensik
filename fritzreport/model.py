"""Rohdatensätze → Anzeige-/Filter-/Herkunfts-/Grade-Modell.

Übernimmt die Datensatz-Aufbereitung aus dem PoC (``build_report.py``), aber mit
dem **neuen 3-Grade-System**. Das alte „D1 = aus signierter Rohdatei" entfällt
(trivial — der Report bereitet ausschließlich aus Rohdaten auf), die übrigen
rücken auf:

    alt D1 → (kein Badge)   alt D2 → D1   alt D3 → D2   alt D4 → D3

Jede Zeile trägt: Anzeigefelder · Filterschlüssel (``f_*`` + ``mac``) ·
``grades`` (Liste) · ``origin`` (Fundstelle in der Quelldatei).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .bundle import Bundle, Dataset

# Neues 3-Grade-System (kombinierbar).
#
# Der Report weist dieses Schema aus, weil das Vorgängersystem VIER Grade hatte und
# die Bedeutungen sich beim Umstieg verschoben haben: dort war D3 "durch eigene
# forensische Versuche belegt" — hier ist das D2, und D3 heißt "abgeleitet". Wer
# einen Report neben eine alte Unterlage legt, liest Badges sonst in die belastende
# Richtung falsch. Umrechnung siehe ANFORDERUNGEN.md, Abschnitt D.
GRADE_SCHEMA = "v2"
GRADE_LABEL = {
    "D1": "Plausibel innerhalb Rohdaten",
    "D2": "Durch eigene forensische Tests verifiziert",
    "D3": "Abgeleitet / Interpretation",
}

NO_AP = "(keine AP-Zuordnung in Rohdaten)"

MAC_RE = re.compile(r"[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}")
PHONE_RE = re.compile(r"\b(?:\+|00)?\d{6,}\b")

CALL_TYPES = {"1": "eingehend", "2": "verpasst", "3": "abgehend",
              "4": "aktiv eingehend", "10": "Anrufbeantworter", "11": "AB abgehört"}


def origin(ds: Dataset, i: int, total: int) -> dict:
    """Fundstelle eines Records. ``i`` 0-basiert; Anzeige zählt ab 1."""
    s = ds.slices[i] if i < len(ds.slices) else None
    return {
        "file": ds.name, "sha": ds.sha256, "idx": i + 1, "total": total,
        "line": s["line"] if s else None,
        "line_end": s["line_end"] if s else None,
        "text": s["text"] if s else "",
    }


def _iso_from_epoch(v) -> str:
    try:
        return datetime.fromtimestamp(int(v), tz=timezone.utc).isoformat() if v else ""
    except Exception:
        return ""


def _parse_dt(datum: str, zeit: str) -> datetime | None:
    try:
        return datetime.strptime(f"{datum} {zeit}", "%d.%m.%y %H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _parse_dt_short(s: str) -> datetime | None:
    try:
        return datetime.strptime(s, "%d.%m.%y %H:%M").replace(tzinfo=timezone.utc)
    except Exception:
        return None


@dataclass
class Model:
    meta: dict = field(default_factory=dict)
    real_aps: list = field(default_factory=list)
    master: dict = field(default_factory=dict)
    hosts: list = field(default_factory=list)
    mesh_nodes: list = field(default_factory=list)
    wifi: list = field(default_factory=list)
    calls: list = field(default_factory=list)
    phonebook: list = field(default_factory=list)
    events: list = field(default_factory=list)
    dhcp: dict | None = None
    # Aggregate/Kennzahlen (D3)
    stats: dict = field(default_factory=dict)
    cat_counts: dict = field(default_factory=dict)


def build_model(b: Bundle) -> Model:
    m = Model(meta=dict(b.meta))

    # --- echte Mesh-Access-Points (nur is_meshed == true)
    mesh_records = b.ds("mesh").records
    m.real_aps = sorted({
        r.get("device_name") for r in mesh_records
        if r.get("record_type") == "node" and r.get("is_meshed") and r.get("device_name")
    })

    # --- Hosts
    ds = b.ds("hosts")
    for i, r in enumerate(ds.records):
        mac = (r.get("MACAddress") or "").upper()
        if not mac:
            continue
        name = r.get("HostName") or ""
        has_detail = bool(r.get("IPAddress") and r.get("InterfaceType"))
        m.hosts.append({
            "mac": mac, "ip": r.get("IPAddress") or "", "name": name,
            "iface": r.get("InterfaceType") or "",
            "active": r.get("Active") == "1", "guest": r.get("X_AVM-DE_Guest") == "1",
            "f_name": name, "f_phone": "", "f_ap": "", "f_iso": "",
            "grades": (["D1"] if has_detail else []),   # alt D2 → D1
            "origin": origin(ds, i, len(ds.records)),
        })

    # --- Mesh-Knoten (über volle Recordliste für korrekten Datei-Index)
    ds = b.ds("mesh")
    for i, r in enumerate(ds.records):
        if r.get("record_type") != "node":
            continue
        name = r.get("device_name") or ""
        is_ap = bool(r.get("is_meshed"))
        is_master = r.get("mesh_role") == "master"
        m.mesh_nodes.append({
            "name": name, "model": r.get("device_model") or "",
            "mac": (r.get("device_mac_address") or "").upper(),
            "role": r.get("mesh_role") or "", "firmware": r.get("device_firmware_version") or "",
            "is_ap": is_ap,
            "f_name": name, "f_phone": "", "f_ap": name if is_ap else "", "f_iso": "",
            # alt D2(AP)→D1, alt D3(master)→D2
            "grades": (["D1"] if is_ap else []) + (["D2"] if is_master else []),
            "origin": origin(ds, i, len(ds.records)),
        })
    m.master = next((n for n in m.mesh_nodes if n["role"] == "master"), {})

    # --- WLAN-/LAN-Clients (wifi.json)
    ds = b.ds("wifi")
    for i, r in enumerate(ds.records):
        mac = (r.get("mac") or "").upper()
        if not mac:
            continue
        raw = r.get("raw") if isinstance(r.get("raw"), dict) else {}
        parent = raw.get("parent") if isinstance(raw.get("parent"), dict) else {}
        ap_reported = (parent or {}).get("name") or ""
        ap_is_mesh = ap_reported in m.real_aps
        ts = _iso_from_epoch(r.get("last_seen"))
        name = r.get("name") or ""
        if ap_is_mesh:
            ap_display = ap_reported
        elif ap_reported:
            ap_display = f"{ap_reported} — kein Mesh-AP"
        else:
            ap_display = NO_AP
        m.wifi.append({
            "mac": mac, "name": name, "ipv4": r.get("ipv4") or "",
            "interface": r.get("interface") or "", "ap_display": ap_display,
            "ap_is_mesh": ap_is_mesh, "port": r.get("port") or "", "status": r.get("status") or "",
            "last_seen_iso": ts,
            "f_name": name, "f_phone": "", "f_ap": ap_reported if ap_is_mesh else "", "f_iso": ts,
            "grades": (["D1"] if ap_is_mesh else []),   # alt D2 → D1
            "origin": origin(ds, i, len(ds.records)),
        })

    # --- Anrufe (reine Rohdaten → kein Badge)
    ds = b.ds("calls")
    for i, r in enumerate(ds.records):
        ts = _parse_dt_short(r.get("Datum") or "")
        nummer = r.get("Rufnummer") or ""
        name = r.get("Name") or ""
        m.calls.append({
            "iso": ts.isoformat() if ts else "",
            "typ": CALL_TYPES.get(r.get("Typ") or "", r.get("Typ") or ""),
            "rufnummer": nummer, "name": name,
            "region": r.get("Landes-/Ortsnetzbereich") or "",
            "nebenstelle": r.get("Nebenstelle") or "", "eigene": r.get("Eigene Rufnummer") or "",
            "dauer": r.get("Dauer") or "",
            "f_name": name, "f_phone": nummer, "f_ap": "", "f_iso": ts.isoformat() if ts else "",
            "grades": [],
            "origin": origin(ds, i, len(ds.records)),
        })

    # --- Telefonbuch (reine Rohdaten → kein Badge)
    ds = b.ds("phonebook")
    for i, r in enumerate(ds.records):
        nums = r.get("numbers") or []
        num_str = ", ".join(f'{n.get("number","")} ({n.get("type","")})' for n in nums)
        name = r.get("name") or ""
        m.phonebook.append({
            "name": name, "book": r.get("phonebook_name") or "", "numbers": num_str,
            "f_name": name, "f_phone": " ".join(n.get("number", "") for n in nums),
            "f_ap": "", "f_iso": "",
            "grades": [],
            "origin": origin(ds, i, len(ds.records)),
        })

    # --- Ereignisse
    ds = b.ds("events")
    for i, r in enumerate(ds.records):
        ts = _parse_dt(r.get("date") or "", r.get("time") or "")
        msg = r.get("message") or ""
        mm = MAC_RE.search(msg)
        mac = mm.group(0).upper() if mm else ""
        pm = PHONE_RE.search(msg)
        phone = pm.group(0) if pm else ""
        low = msg.lower()
        grades = []
        if mac and ("anmeldung" in low or "angemeldet" in low or "abgemeldet" in low):
            grades.append("D1")   # alt D2 → D1
        ev_ap = next((a for a in m.real_aps if a.lower() in low), "")
        m.events.append({
            "iso": ts.isoformat() if ts else "", "category": r.get("category") or "",
            "id": r.get("id"), "mac": mac, "message": msg,
            "f_name": "", "f_phone": phone, "f_ap": ev_ap, "f_iso": ts.isoformat() if ts else "",
            "grades": grades,
            "origin": origin(ds, i, len(ds.records)),
        })

    # --- DHCP-Konfiguration (reine Rohdaten → kein Badge)
    ds = b.ds("dhcp")
    for i, r in enumerate(ds.records):
        if r.get("record_type") == "dhcp_config":
            m.dhcp = {
                "enable": r.get("dhcp_server_enable") == "1",
                "min": r.get("min_address") or "", "max": r.get("max_address") or "",
                "mask": r.get("subnet_mask") or "", "domain": r.get("domain_name") or "",
                "router": r.get("ip_routers") or "", "dns": r.get("dns_servers") or "",
                "origin": origin(ds, i, len(ds.records)),
            }
            break

    # --- Ereignis-Kategorien
    for e in m.events:
        m.cat_counts[e["category"]] = m.cat_counts.get(e["category"], 0) + 1

    return m
