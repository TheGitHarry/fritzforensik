"""Test-Fixtures: ein selbst-enthaltenes synthetisches fritzexport-Bundle.

Erzeugt ein kleines, aber vollständiges Bundle (JSON-Datenarten + korrekte
``.sha256``-Sidecars + eine Roh-``supportdata_standard``-Datei mit dhcpd,
STATION_MODULE, WLAN_EVENTS (ID 30005), einer 802.11-``wl0``-Zeile und uptime).
So laufen die Tests ohne die echten Forensikdaten unter ``~/testdata``.

Das Bundle wird über :mod:`fritzformat` gebaut — also über exakt denselben
Formatvertrag, den fritzexport beim Schreiben benutzt. Früher baute dieses
Fixture das Format von Hand nach; eine Abweichung wäre unbemerkt geblieben.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from fritzformat import (
    TOOL_NAME,
    build_envelope,
    dataset_filename,
    session_log_filename,
    sha256_bytes,
    support_filename,
    write_sidecar,
)

MAC = "AA:BB:CC:DD:EE:01"
maclow = MAC.lower()
EXTRACTED = "2026-01-06T10:00:00Z"


HOST = "https://fritz.box"


def _meta(type_, records):
    return build_envelope(tool=TOOL_NAME, version="0.3.1", host=HOST,
                          type_name=type_, records=records, extracted_at=EXTRACTED)


def _write_json(d: Path, ts, type_, records):
    p = d / dataset_filename(HOST, ts, type_)
    body = json.dumps(_meta(type_, records), indent=2, ensure_ascii=False).encode("utf-8")
    p.write_bytes(body)
    write_sidecar(p, sha256_bytes(body))
    return p


SUPPORT = """\
##### TITLE Version 8.20
##### TITLE Datum Tue Jan  6 11:00:02 CET 2026
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
    # Selbstauskunft der Box über TR-064 — Modellname im Klartext und die Laufzeit
    # in Sekunden, beide unabhängig von den Supportdaten.
    _write_json(d, ts, "deviceinfo", [
        {"record_type": "device_info", "model_name": "FRITZ!Box 7590",
         "description": "FRITZ!Box 7590 Release 154.08.25",
         "product_class": "FRITZ!Box", "manufacturer": "AVM",
         "manufacturer_oui": "00040E", "serial_number": "AABBCCDDEEFF",
         "software_version": "154.08.25", "hardware_version": "FRITZ!Box 7590",
         "spec_version": "1.0", "provisioning_code": "",
         "uptime_s": 441000,
         "device_log": "06.01.26 09:00:00 Anmeldung an der Benutzeroberfläche\n",
         "raw": {"NewModelName": "FRITZ!Box 7590"}}])

    # Zweite Uhr-Quelle: TR-064 Time:1. Die Box meldet 11:00:02+01:00 (= 10:00:02Z),
    # geklammert von 10:00:01,900Z / 10:00:02,100Z — eine Round-Trip-Klammer, bei der
    # **beide** Schranken tragen. Ohne diese Datenart im Fixture ließ sich der ganze
    # TR-064-Zweig der Auswertung lahmlegen, ohne dass ein Test rot wurde.
    _write_json(d, ts, "boxtime", [
        {"record_type": "box_clock",
         "box_current_local_time": "2026-01-06T11:00:02+01:00",
         "box_local_timezone": "CET-1CEST,M3.5.0,M10.5.0/3",
         "box_local_timezone_name": "", "box_daylight_savings_used": "0",
         "box_daylight_savings_start": "", "box_daylight_savings_end": "",
         "box_ntp_server1": "ntp.fritz.box", "box_ntp_server2": "",
         "raw": {"NewCurrentLocalTime": "2026-01-06T11:00:02+01:00"}}])
    _write_json(d, ts, "dhcp", [
        {"record_type": "dhcp_config", "dhcp_server_enable": "1",
         "min_address": "192.168.1.20", "max_address": "192.168.1.200",
         "subnet_mask": "255.255.255.0", "domain_name": "fritz.box",
         "ip_routers": "192.168.1.1", "dns_servers": "192.168.1.1"}])
    sup = d / support_filename("standard", ts)
    body = SUPPORT.encode("utf-8")
    sup.write_bytes(body)
    write_sidecar(sup, sha256_bytes(body))

    # Sitzungslog mit **beiden** Uhr-Klammern — der Fall, den der Report mit zwei
    # Zeilen beantwortet:
    #
    #   supportdata:standard — Box meldet 11:00:02 CET (= 10:00:02Z), Marken 10:00:00Z
    #     und 10:00:40Z. Obere Schranke +3 s (2 s Differenz + 1 s Quantisierung); die
    #     untere −38 s ist reine Übertragungsdauer und darf nicht als Messwert
    #     erscheinen.
    #   tr064:time — dieselbe Box-Zeit, Marken 10:00:01,900Z / 10:00:02,100Z. Klammer
    #     +0 s bis +1 s, beidseitig scharf.
    #
    # Bewusst **ohne** SICHERUNG-Marker: Ein anderer Test prüft an diesem Fixture,
    # dass der Sicherungszeitraum aus den `extracted_at` abgeleitet wird.
    (d / session_log_filename(ts)).write_text(
        "2026-01-06 11:00:00,000 INFO UHRZEIT ANFRAGE supportdata:standard "
        "2026-01-06T10:00:00.000Z\n"
        "2026-01-06 11:00:40,000 INFO UHRZEIT ANTWORT supportdata:standard "
        "2026-01-06T10:00:40.000Z\n"
        "2026-01-06 11:00:41,900 INFO UHRZEIT ANFRAGE tr064:time "
        "2026-01-06T10:00:01.900Z\n"
        "2026-01-06 11:00:42,100 INFO UHRZEIT ANTWORT tr064:time "
        "2026-01-06T10:00:02.100Z\n",
        encoding="utf-8")
    return d


@pytest.fixture
def synth_bundle(tmp_path):
    return build_bundle(tmp_path)


@pytest.fixture
def real_boxes():
    base = Path(os.path.expanduser("~/testdata/eingang"))
    if not base.is_dir():
        pytest.skip("Echte Testdaten (~/testdata/eingang) nicht vorhanden")
    return sorted(p for p in base.glob("export_*") if p.is_dir())
