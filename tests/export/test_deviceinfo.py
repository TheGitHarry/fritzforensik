"""Offline-Tests für den DeviceInfo-Extractor (TR-064 ``DeviceInfo:1#GetInfo``).

Der Dienst liefert, was die Box über sich selbst sagt — darunter drei Angaben, die
bisher nur mühsam oder gar nicht zu haben waren: den **Modellnamen im Klartext**
(aus den Supportdaten ist sicher nur die ``HWRevision`` ablesbar), die **Laufzeit in
Sekunden** und das **Ereignislog**.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from fritzexport.client import Tr064Disabled, Tr064Error
from fritzexport.extractors import deviceinfo as di_mod

#: Antwort einer 7590 (154.08.25) — Feldnamen wörtlich so gemessen, Werte entschärft.
GETINFO = {
    "NewManufacturerName": "AVM",
    "NewManufacturerOUI": "00040E",
    "NewModelName": "FRITZ!Box 7590",
    "NewDescription": "FRITZ!Box 7590 Release 154.08.25",
    "NewProductClass": "FRITZ!Box",
    "NewSerialNumber": "AABBCCDDEEFF",
    "NewSoftwareVersion": "154.08.25",
    "NewHardwareVersion": "FRITZ!Box 7590",
    "NewSpecVersion": "1.0",
    "NewProvisioningCode": "",
    "NewUpTime": "3116010",
    "NewDeviceLog": "09.08.26 02:23:29 WLAN-Autokanal: Erfassung läuft\n",
}


def test_extract_gibt_die_rohwerte_durch():
    client = MagicMock()
    client.tr064_call.return_value = GETINFO
    records = di_mod.extract(client)

    assert len(records) == 1
    rec = records[0]
    assert rec["record_type"] == "device_info"
    assert rec["model_name"] == "FRITZ!Box 7590"
    assert rec["hardware_version"] == "FRITZ!Box 7590"
    assert rec["software_version"] == "154.08.25"
    assert rec["serial_number"] == "AABBCCDDEEFF"
    assert rec["raw"] == GETINFO


def test_uptime_bleibt_zahl_und_wird_nicht_gerechnet():
    """Die Laufzeit steht sekundengenau da. Ein daraus gerechnetes Boot-Datum wäre
    eine Ableitung — die gehört in den Report, nicht in den Abzug (wie bei `boxtime`
    der Versatz der Box-Uhr)."""
    client = MagicMock()
    client.tr064_call.return_value = GETINFO
    rec = di_mod.extract(client)[0]

    assert rec["uptime_s"] == 3116010
    assert not any("boot" in k for k in rec), "Der Extractor darf nichts ableiten"


def test_device_log_wird_mitgenommen():
    """Das Ereignislog der Box — eine zweite Quelle neben der Datenart `events`."""
    client = MagicMock()
    client.tr064_call.return_value = GETINFO
    assert "WLAN-Autokanal" in di_mod.extract(client)[0]["device_log"]


def test_unbrauchbare_uptime_bleibt_leer():
    """Liefert die Box etwas anderes als eine Zahl, wird nicht geraten."""
    client = MagicMock()
    client.tr064_call.return_value = {**GETINFO, "NewUpTime": "unbekannt"}
    assert di_mod.extract(client)[0]["uptime_s"] == ""


def test_tr064_abgeschaltet_ergibt_leere_liste():
    """Boxen ohne TR-064 sind kein Fehlerfall — die Datenart bleibt leer."""
    client = MagicMock()
    client.tr064_call.side_effect = Tr064Disabled("aus")
    assert di_mod.extract(client) == []


def test_tr064_fehler_ergibt_leere_liste():
    client = MagicMock()
    client.tr064_call.side_effect = Tr064Error("kaputt")
    assert di_mod.extract(client) == []
