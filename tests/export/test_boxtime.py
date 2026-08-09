"""Offline-Tests für den Boxtime-Extractor (Time:1#GetInfo).

Der Extractor rechnet **nichts** — er holt die Rohwerte und klammert den Aufruf in
zwei Zeitmarken. Geprüft wird deshalb vor allem, dass die Rohwerte unverfälscht
durchgereicht werden und die Klammer den Aufruf tatsächlich einschließt.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from fritzexport.client import Tr064Disabled, Tr064Error
from fritzexport.extractors import boxtime as bt_mod

# Antwort einer 7490/7590/7690 — wörtlich so gemessen.
GETINFO = {
    "NewNTPServer1": "de.pool.ntp.org",
    "NewNTPServer2": "",
    "NewCurrentLocalTime": "2026-08-09T17:55:36+02:00",
    "NewLocalTimeZone": "",
    "NewLocalTimeZoneName": "CET-1CEST,M3.5.0,M10.5.0/3",
    "NewDaylightSavingsUsed": "0",
    "NewDaylightSavingsStart": "0001-01-01T00:00:00",
    "NewDaylightSavingsEnd": "0001-01-01T00:00:00",
}


def test_extract_full_record():
    client = MagicMock()
    client.tr064_call.return_value = GETINFO
    records = bt_mod.extract(client)

    assert len(records) == 1
    rec = records[0]
    assert rec["record_type"] == "box_clock"
    assert rec["box_current_local_time"] == "2026-08-09T17:55:36+02:00"
    assert rec["box_ntp_server1"] == "de.pool.ntp.org"
    assert rec["box_local_timezone_name"] == "CET-1CEST,M3.5.0,M10.5.0/3"
    assert rec["raw"] == GETINFO


def test_extract_returns_empty_on_tr064_disabled():
    """Zwei Korpus-Boxen haben den TR-064-Stack aus — das ist kein Fehlerfall."""
    client = MagicMock()
    client.tr064_call.side_effect = Tr064Disabled("aus")
    assert bt_mod.extract(client) == []


def test_extract_returns_empty_on_tr064_error():
    client = MagicMock()
    client.tr064_call.side_effect = Tr064Error("transport")
    assert bt_mod.extract(client) == []


def test_daylight_savings_used_bleibt_roh():
    """Die Box meldet ``0``, obwohl CEST aktiv ist. Der Wert wird mitgeschrieben,
    aber nie als Sommerzeit-Indikator gedeutet — sonst stünde im Report das
    Gegenteil dessen, was der UTC-Offset sagt."""
    client = MagicMock()
    client.tr064_call.return_value = GETINFO
    rec = bt_mod.extract(client)[0]

    assert rec["box_daylight_savings_used"] == "0"
    assert isinstance(rec["box_daylight_savings_used"], str)
    # Der maßgebliche Träger der Zeitzone ist der Offset in der Zeitangabe selbst.
    assert rec["box_current_local_time"].endswith("+02:00")


def test_aufruf_wird_geklammert(monkeypatch):
    """Anfrage-Marke vor dem SOAP-Aufruf, Antwort-Marke danach. Marker und Aufruf
    laufen in **eine** Liste, damit ihre Reihenfolge zueinander geprüft wird."""
    ablauf: list[str] = []
    monkeypatch.setattr(bt_mod.log, "info", lambda msg, *a: ablauf.append(msg.split()[1]))
    client = MagicMock()
    client.tr064_call.side_effect = lambda *a, **kw: ablauf.append("CALL") or GETINFO

    bt_mod.extract(client)

    assert ablauf == ["ANFRAGE", "CALL", "ANTWORT"]


def test_klammer_traegt_die_quellenkennung(monkeypatch):
    """Ohne Kennung könnte der Report die Marken nicht der Messung zuordnen."""
    zeilen: list[str] = []
    monkeypatch.setattr(bt_mod.log, "info", lambda msg, *a: zeilen.append(msg))
    client = MagicMock()
    client.tr064_call.return_value = GETINFO

    bt_mod.extract(client)

    assert zeilen[0].startswith("UHRZEIT ANFRAGE tr064:time ")
    assert zeilen[-1].startswith("UHRZEIT ANTWORT tr064:time ")


def test_abgebrochener_versuch_bleibt_datiert(monkeypatch):
    """Auch wenn der Dienst fehlt, steht die Antwort-Marke im Log — der Versuch
    soll sichtbar bleiben. Ohne Rohwerte bildet der Report daraus keine Klammer."""
    zeilen: list[str] = []
    monkeypatch.setattr(bt_mod.log, "info", lambda msg, *a: zeilen.append(msg))
    client = MagicMock()
    client.tr064_call.side_effect = Tr064Disabled("aus")

    assert bt_mod.extract(client) == []
    marker = [z for z in zeilen if z.startswith("UHRZEIT")]
    assert len(marker) == 2
