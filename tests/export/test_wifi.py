"""Offline-Tests für den WLAN-Extractor — zwei Quellen, ein Datensatz je Gerät.

Der Web-UI-Weg (``data.lua page=netDev``) schweigt, sobald die Box als **IP-Client
hinter einem anderen Router** läuft: Sie zeigt dann bewusst keine Geräteliste. Das ist
forensisch der Normalfall, denn am Auswerteplatz hängt die Box hinter dem Router des
Prüfers. TR-064 ``WLANConfiguration`` ist davon unberührt.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from fritzexport.client import Tr064Disabled, Tr064Error
from fritzexport.extractors import wifi as wifi_mod

MAC_A = "AA:BB:CC:DD:EE:01"
MAC_B = "AA:BB:CC:DD:EE:02"

#: Antwort einer 7590 — Feldnamen wörtlich so gemessen.
DEV = {
    "NewAssociatedDeviceMACAddress": MAC_B,
    "NewAssociatedDeviceIPAddress": "192.168.2.55",
    "NewAssociatedDeviceAuthState": "1",
    "NewX_AVM-DE_Speed": "650",
    "NewX_AVM-DE_SignalStrength": "72",
    "NewX_AVM-DE_ChannelWidth": "80",
}


def _client(netdev: dict | None, tr064) -> MagicMock:
    """netdev=None → Box im IP-Client-Modus (kein `active`/`passive` in der Antwort)."""
    client = MagicMock()
    client.post.return_value.json.return_value = {
        "data": netdev if netdev is not None else {"ipclient": True, "nolist": True}}
    client.tr064_call.side_effect = tr064
    return client


def _tr064(instanzen: dict):
    """Baut eine tr064_call-Seitenwirkung: {instanz: [geraete]}."""
    def call(service_type, control_url, action, args=None, **kw):
        i = int(service_type.rstrip(":")[-1])
        geraete = instanzen.get(i, [])
        if action == "GetInfo":
            return {"NewSSID": f"WLAN-{i}", "NewEnable": "1", "NewStandard": "ax"}
        if action == "GetTotalAssociations":
            return {"NewTotalAssociations": str(len(geraete))}
        if action == "GetGenericAssociatedDeviceInfo":
            return geraete[int(args["NewAssociatedDeviceIndex"])]
        raise AssertionError(f"unerwartete Aktion: {action}")
    return call


def test_tr064_fuellt_die_leere_web_ui_liste():
    """Der Kernfall: Box als IP-Client, Web-UI liefert nichts, TR-064 liefert."""
    records = wifi_mod.extract(_client(None, _tr064({1: [DEV]})))

    assert len(records) == 1
    r = records[0]
    assert r["source"] == "tr064"
    assert r["mac"] == MAC_B
    assert r["ipv4"] == "192.168.2.55"
    assert r["signal_strength"] == "72"
    assert r["wlan_instance"] == 1
    assert r["status"] == "active", "assoziiert heißt aktiv verbunden"


def test_beide_quellen_ergeben_einen_datensatz_je_geraet():
    """Auf einer Box, die Router ist, kennen beide Wege dasselbe Gerät. Zwei
    Datensätze daraus zu machen zählte es im Bericht doppelt."""
    netdev = {"active": [{"mac": MAC_B, "name": "Handy",
                          "ipv4": {"ip": "192.168.2.55", "lastused": "1767434400"},
                          "conn": "802.11"}], "passive": []}
    records = wifi_mod.extract(_client(netdev, _tr064({1: [DEV]})))

    assert len(records) == 1
    r = records[0]
    assert r["source"] == "webui+tr064"
    assert r["name"] == "Handy", "der Web-UI-Wert darf nicht überschrieben werden"
    assert r["last_seen"] == "1767434400"
    assert r["signal_strength"] == "72", "die TR-064-Felder fehlen"


def test_tr064_ueberschreibt_keinen_web_ui_wert():
    """Widersprechen sich die Quellen, gewinnt keine still: Der Web-UI-Wert bleibt
    stehen, der abweichende TR-064-Wert steht im Rohteil des Datensatzes."""
    netdev = {"active": [{"mac": MAC_B, "name": "Handy",
                          "ipv4": {"ip": "192.168.2.99"}, "conn": "802.11"}],
              "passive": []}
    r = wifi_mod.extract(_client(netdev, _tr064({1: [DEV]})))[0]

    assert r["ipv4"] == "192.168.2.99"
    assert r["raw_tr064"]["NewAssociatedDeviceIPAddress"] == "192.168.2.55"


def test_ohne_tr064_bleibt_der_web_ui_weg():
    """Boxen mit abgeschaltetem TR-064 sind kein Fehlerfall."""
    netdev = {"active": [{"mac": MAC_A, "name": "PC", "conn": "802.11"}], "passive": []}
    records = wifi_mod.extract(_client(netdev, Tr064Disabled("aus")))

    assert [r["source"] for r in records] == ["webui"]
    assert records[0]["name"] == "PC"


def test_tr064_fehler_kippt_den_abruf_nicht():
    records = wifi_mod.extract(_client({"active": [], "passive": []},
                                       Tr064Error("kaputt")))
    assert records == []


def test_alle_instanzen_werden_abgefragt():
    """2,4 GHz, 5 GHz und Gast sind eigene Instanzen — eine ohne Clients liefert
    nichts, darf aber die übrigen nicht verhindern."""
    zweites = {**DEV, "NewAssociatedDeviceMACAddress": MAC_A}
    records = wifi_mod.extract(_client(None, _tr064({1: [DEV], 3: [zweites]})))

    assert {r["mac"] for r in records} == {MAC_A, MAC_B}
    assert {r["wlan_instance"] for r in records} == {1, 3}
