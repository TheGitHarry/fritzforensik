"""Test-Fixtures: ein selbst-enthaltenes synthetisches legacy_export-Bundle.

Erzeugt ein kleines, aber vollständiges Bundle (JSON-Datenarten + korrekte
``.sha256``-Sidecars + eine Roh-``supportdata_standard``-Datei mit dhcpd,
STATION_MODULE, WLAN_EVENTS (ID 30005), einer 802.11-``wl0``-Zeile und uptime).
So laufen die Tests ohne die echten Forensikdaten unter ``~/testdata``.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

MAC = "AA:BB:CC:DD:EE:01"
maclow = MAC.lower()
EXTRACTED = "2026-01-06T10:00:00Z"


def _meta(type_, records):
    return {"tool": "legacy_export", "version": "0.3.1",
            "host": "https://fritz.box", "extracted_at": EXTRACTED,
            "type": type_, "records": records}


def _write_json(d: Path, ts, type_, records):
    p = d / f"legacy_export_fritz.box_{ts}_{type_}.json"
    p.write_text(json.dumps(_meta(type_, records), indent=2, ensure_ascii=False), encoding="utf-8")
    _sidecar(p)
    return p


def _sidecar(p: Path):
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    p.with_suffix(p.suffix + ".sha256").write_text(f"{digest}  {p.name}\n", encoding="utf-8")


SUPPORT = """\
##### TITLE Version 8.20
##### BEGIN SECTION dhcpd
lease list:
wlease {MAC} 192.168.1.20 3600 "TestPhone" 01-aa AA:BB:CC:DD:EE:01 "" dynamic
##### END SECTION dhcpd
##### BEGIN SECTION STATION_MODULE Module for station informations
  mac                     = {MAC}
  current_state           = 4
Connect history: connect[time/status] - disconnect
 01.01.2026 10:00:00/[80.362] / 1 -  / 79 - 100 -  14
##### END SECTION STATION_MODULE
##### BEGIN SECTION WLAN_EVENTS Filtered Events
20260101-100010 /              --- / {MAC} /  30005 /  connected
##### END SECTION WLAN_EVENTS
uptime: 10:00:00 up 5 days,  2:00, load average: 0.1
ip4_uptime=432000
2026-01-01 10:00:05.123 - wl0: STA {MAC} IEEE 802.11: associated (aid 4)
2026-01-01 10:30:12.400 - wl0: STA {MAC} IEEE 802.11: disassociated
""".replace("{MAC}", MAC)


def build_bundle(d: Path) -> Path:
    ts = "20260106T100000Z"
    _write_json(d, ts, "hosts", [
        {"MACAddress": MAC, "IPAddress": "192.168.1.20", "HostName": "TestPhone",
         "InterfaceType": "802.11", "Active": "1", "X_AVM-DE_Guest": "0"},
        {"MACAddress": "AA:BB:CC:DD:EE:02", "IPAddress": "", "HostName": "NoDetail",
         "InterfaceType": "", "Active": "0", "X_AVM-DE_Guest": "0"},
    ])
    _write_json(d, ts, "mesh", [
        {"record_type": "node", "device_name": "fritzbox", "device_model": "FRITZ!Box 7590",
         "device_mac_address": MAC, "mesh_role": "master", "is_meshed": True,
         "device_firmware_version": "8.20"}])
    _write_json(d, ts, "wifi", [
        {"mac": MAC, "name": "TestPhone", "ipv4": "192.168.1.20", "interface": "wlan",
         "last_seen": 1767434400, "status": "active",
         "raw": {"parent": {"name": "fritzbox"}}}])
    _write_json(d, ts, "calls", [
        {"Typ": "1", "Datum": "01.01.26 10:05", "Name": "Alice", "Rufnummer": "0048123",
         "Landes-/Ortsnetzbereich": "", "Nebenstelle": "", "Eigene Rufnummer": "", "Dauer": "0:30"}])
    _write_json(d, ts, "phonebook", [
        {"name": "Alice", "phonebook_name": "Telefonbuch",
         "numbers": [{"number": "0048123", "type": "home"}]}])
    _write_json(d, ts, "events", [
        {"date": "01.01.26", "time": "10:00:10", "category": "wlan", "id": 1,
         "message": f"WLAN-Gerät TestPhone angemeldet, MAC {MAC}"}])
    _write_json(d, ts, "dhcp", [
        {"record_type": "dhcp_config", "dhcp_server_enable": "1",
         "min_address": "192.168.1.20", "max_address": "192.168.1.200",
         "subnet_mask": "255.255.255.0", "domain_name": "fritz.box",
         "ip_routers": "192.168.1.1", "dns_servers": "192.168.1.1"}])
    sup = d / f"supportdata_standard_{ts}.txt"
    sup.write_text(SUPPORT, encoding="utf-8")
    _sidecar(sup)
    return d


@pytest.fixture
def synth_bundle(tmp_path):
    return build_bundle(tmp_path)


@pytest.fixture
def real_boxes():
    base = Path(os.path.expanduser("~/testdata/export"))
    if not base.is_dir():
        pytest.skip("Echte Testdaten (~/testdata/export) nicht vorhanden")
    return sorted(p for p in base.glob("export_*") if p.is_dir())
