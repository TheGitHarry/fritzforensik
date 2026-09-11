"""Offline-Tests für Hosts-Extractor (TR-064-Path-XML + Generic-Iteration-Fallback)."""
from __future__ import annotations

from unittest.mock import MagicMock

from fritzexport.client import Tr064Disabled, Tr064Error
from fritzexport.extractors import hosts as hosts_mod


HOSTLIST_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<List>
  <Item>
    <Index>0</Index>
    <IPAddress>192.168.178.20</IPAddress>
    <AddressSource>DHCP</AddressSource>
    <LeaseTimeRemaining>86400</LeaseTimeRemaining>
    <MACAddress>AA:BB:CC:DD:EE:01</MACAddress>
    <InterfaceType>Ethernet</InterfaceType>
    <Active>1</Active>
    <HostName>laptop</HostName>
    <X_AVM-DE_Port>1</X_AVM-DE_Port>
    <X_AVM-DE_Speed>1000</X_AVM-DE_Speed>
    <X_AVM-DE_Guest>0</X_AVM-DE_Guest>
    <X_AVM-DE_VPN>0</X_AVM-DE_VPN>
    <X_AVM-DE_Disallow>0</X_AVM-DE_Disallow>
    <X_AVM-DE_FriendlyName>Mein Laptop</X_AVM-DE_FriendlyName>
  </Item>
  <Item>
    <Index>1</Index>
    <IPAddress>192.168.178.50</IPAddress>
    <AddressSource>STATIC</AddressSource>
    <MACAddress>AA:BB:CC:DD:EE:02</MACAddress>
    <InterfaceType>802.11</InterfaceType>
    <Active>0</Active>
    <HostName>iphone</HostName>
    <X_AVM-DE_Guest>1</X_AVM-DE_Guest>
  </Item>
</List>"""


def test_parse_hostlist_xml_extracts_two_items():
    records = hosts_mod._parse_hostlist_xml(HOSTLIST_XML)
    assert len(records) == 2
    laptop = next(r for r in records if r["HostName"] == "laptop")
    assert laptop["IPAddress"] == "192.168.178.20"
    assert laptop["MACAddress"] == "AA:BB:CC:DD:EE:01"
    assert laptop["Active"] == "1"
    assert laptop["X_AVM-DE_Port"] == "1"
    assert laptop["X_AVM-DE_FriendlyName"] == "Mein Laptop"
    assert laptop["source"] == "tr064_path"
    iphone = next(r for r in records if r["HostName"] == "iphone")
    assert iphone["X_AVM-DE_Guest"] == "1"
    assert iphone["Active"] == "0"


def test_parse_hostlist_xml_handles_corrupt():
    assert hosts_mod._parse_hostlist_xml(b"<not xml") == []


def test_parse_hostlist_xml_handles_empty_list():
    assert hosts_mod._parse_hostlist_xml(b"<List></List>") == []


def test_extract_uses_tr064_path():
    client = MagicMock()
    client.tr064_call.return_value = {
        "NewX_AVM-DE_HostListPath": "/hostlist.lua?sid=abc"
    }
    client.base_url = "https://192.168.2.1"
    fake_resp = MagicMock()
    fake_resp.content = HOSTLIST_XML
    fake_resp.raise_for_status.return_value = None
    client.session.get.return_value = fake_resp
    records = hosts_mod.extract(client)
    assert len(records) == 2
    # Path-eigene SID muss durchgereicht worden sein, nicht überschrieben
    args, kwargs = client.session.get.call_args
    assert kwargs["params"].get("sid") == "abc"


def test_extract_falls_back_to_generic_iteration_when_path_disabled():
    client = MagicMock()
    # Port-49000-WebUI-Fallback soll durchfallen → Stage 3 (Generic-Iteration)
    client.session.get.side_effect = OSError("no webui fallback")
    # Erster Call (Path-Action) wirft Tr064Disabled, dann Count + zwei Generic-Calls
    client.tr064_call.side_effect = [
        Tr064Disabled("aus", error_code=606),
        {"NewHostNumberOfEntries": "2"},
        {
            "NewIPAddress": "192.168.178.20",
            "NewMACAddress": "AA:BB:CC:DD:EE:01",
            "NewActive": "1",
            "NewHostName": "host0",
            "NewInterfaceType": "Ethernet",
            "NewAddressSource": "DHCP",
            "NewLeaseTimeRemaining": "86000",
        },
        {
            "NewIPAddress": "192.168.178.21",
            "NewMACAddress": "AA:BB:CC:DD:EE:02",
            "NewActive": "0",
            "NewHostName": "host1",
            "NewInterfaceType": "802.11",
            "NewAddressSource": "DHCP",
            "NewLeaseTimeRemaining": "0",
        },
    ]
    records = hosts_mod.extract(client)
    assert len(records) == 2
    assert records[0]["HostName"] == "host0"
    assert records[0]["source"] == "tr064_generic"
    assert records[1]["HostName"] == "host1"


def test_extract_returns_empty_when_everything_disabled():
    client = MagicMock()
    client.tr064_call.side_effect = Tr064Disabled("aus")
    client.session.get.side_effect = OSError("no webui fallback")
    assert hosts_mod.extract(client) == []


def test_extract_falls_back_when_xml_fetch_raises():
    client = MagicMock()
    client.tr064_call.side_effect = [
        {"NewX_AVM-DE_HostListPath": "/hostlist.lua?sid=abc"},
        # danach Generic-Iteration:
        {"NewHostNumberOfEntries": "1"},
        {
            "NewIPAddress": "10.0.0.1",
            "NewMACAddress": "AA:BB:CC:DD:EE:99",
            "NewActive": "1",
            "NewHostName": "fallback-host",
            "NewInterfaceType": "Ethernet",
        },
    ]
    client.base_url = "https://192.168.2.1"
    client.session.get.side_effect = OSError("connection reset")
    records = hosts_mod.extract(client)
    assert len(records) == 1
    assert records[0]["HostName"] == "fallback-host"
    assert records[0]["source"] == "tr064_generic"


# ── query.lua-Zeitfelder (firstused/lastused) ───────────────────────────────

LANDEVICE_ANSWER = {
    "landevice": [
        {
            "UID": "landevice7", "name": "laptop", "mac": "aa:bb:cc:dd:ee:01",
            "ip": "192.168.178.20", "active": "1", "guest": "0",
            "interface": "lan", "speed": "1000",
            "firstused": "1755900000", "lastused": "1756000000",
        },
        {
            "UID": "landevice9", "name": "nur-in-query", "mac": "AA:BB:CC:DD:EE:07",
            "ip": "192.168.178.77", "active": "0", "guest": "1",
            "interface": "wlan", "speed": "0",
            "firstused": "0", "lastused": "1740000000",
        },
    ]
}


def test_landevice_epochen_werden_nach_iso_utc_umgerechnet():
    eintraege = hosts_mod._landevice_eintraege(LANDEVICE_ANSWER)
    laptop = next(e for e in eintraege if e["landevice_uid"] == "landevice7")
    assert laptop["first_seen"] == "2025-08-22T22:00:00Z"
    assert laptop["last_seen"] == "2025-08-24T01:46:40Z"
    assert laptop["first_seen_epoch"] == 1755900000


def test_landevice_epoch_null_bleibt_leer_statt_1970():
    eintraege = hosts_mod._landevice_eintraege(LANDEVICE_ANSWER)
    fremd = next(e for e in eintraege if e["landevice_uid"] == "landevice9")
    assert fremd["first_seen"] == ""
    assert fremd["first_seen_epoch"] == 0
    assert fremd["last_seen"] == "2025-02-19T21:20:00Z"


def test_merge_landevice_ergaenzt_host_je_mac_unabhaengig_von_schreibweise():
    records = hosts_mod._parse_hostlist_xml(HOSTLIST_XML)
    merged = hosts_mod._merge_landevice(
        records, hosts_mod._landevice_eintraege(LANDEVICE_ANSWER)
    )
    laptop = next(r for r in merged if r["MACAddress"] == "AA:BB:CC:DD:EE:01")
    assert laptop["first_seen"] == "2025-08-22T22:00:00Z"
    assert laptop["landevice_uid"] == "landevice7"
    # Die TR-064-Herkunft des Datensatzes bleibt stehen
    assert laptop["source"] == "tr064_path"


def test_merge_landevice_haengt_nur_dort_bekanntes_geraet_an():
    records = hosts_mod._parse_hostlist_xml(HOSTLIST_XML)
    merged = hosts_mod._merge_landevice(
        records, hosts_mod._landevice_eintraege(LANDEVICE_ANSWER)
    )
    assert len(merged) == 3
    fremd = next(r for r in merged if r["MACAddress"] == "AA:BB:CC:DD:EE:07")
    assert fremd["source"] == "query_lua"
    assert fremd["HostName"] == "nur-in-query"
    assert fremd["IPAddress"] == "192.168.178.77"
    assert fremd["Active"] == "0"
    assert fremd["X_AVM-DE_Guest"] == "1"


def test_merge_landevice_ohne_treffer_laesst_host_unberuehrt():
    records = hosts_mod._parse_hostlist_xml(HOSTLIST_XML)
    merged = hosts_mod._merge_landevice(records, [])
    iphone = next(r for r in merged if r["MACAddress"] == "AA:BB:CC:DD:EE:02")
    assert "landevice_uid" not in iphone
    assert "first_seen" not in iphone


def test_extract_fragt_query_lua_per_get_mit_landevice_liste():
    client = MagicMock()
    client.tr064_call.return_value = {
        "NewX_AVM-DE_HostListPath": "/hostlist.lua?sid=abc"
    }
    fake_xml = MagicMock()
    fake_xml.content = HOSTLIST_XML
    fake_xml.raise_for_status.return_value = None
    client.session.get.return_value = fake_xml
    fake_query = MagicMock()
    fake_query.json.return_value = LANDEVICE_ANSWER
    fake_query.raise_for_status.return_value = None
    client.get.return_value = fake_query

    records = hosts_mod.extract(client)

    args, kwargs = client.get.call_args
    assert args[0] == hosts_mod.QUERY_PATH
    assert kwargs["params"]["landevice"] == hosts_mod.LANDEVICE_QUERY
    laptop = next(r for r in records if r["MACAddress"] == "AA:BB:CC:DD:EE:01")
    assert laptop["last_seen"] == "2025-08-24T01:46:40Z"


def test_extract_liefert_hosts_unveraendert_wenn_query_lua_schweigt():
    client = MagicMock()
    client.tr064_call.return_value = {
        "NewX_AVM-DE_HostListPath": "/hostlist.lua?sid=abc"
    }
    fake_xml = MagicMock()
    fake_xml.content = HOSTLIST_XML
    fake_xml.raise_for_status.return_value = None
    client.session.get.return_value = fake_xml
    client.get.side_effect = OSError("keine Antwort")

    records = hosts_mod.extract(client)

    assert len(records) == 2
    assert all("first_seen" not in r for r in records)


def test_fetch_landevice_ruft_den_echten_client_auf():
    """Mit dem echten ``FritzClient.get`` statt einem MagicMock.

    Ein MagicMock nimmt jedes Argument an — ein Aufruf, der gegen die tatsächliche
    Signatur verstößt, fällt dort nie auf, sondern erst an der Box. Genau das ist
    passiert: ``get()`` setzt ``timeout`` bereits selbst, ein zweites löst einen
    ``TypeError`` aus, den der Auffang-Zweig als „nicht abrufbar" verbucht.
    """
    from fritzexport.client import FritzClient

    class FakeSession:
        def __init__(self):
            self.calls = []

        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            resp = MagicMock()
            resp.json.return_value = LANDEVICE_ANSWER
            resp.raise_for_status.return_value = None
            return resp

    session = FakeSession()
    client = FritzClient(base_url="http://box", sid="s1", session=session)

    eintraege = hosts_mod._fetch_landevice(client)

    assert len(eintraege) == 2, "die Antwort der Box muss ankommen"
    url, kwargs = session.calls[0]
    assert url == "http://box/query.lua"
    assert kwargs["params"]["sid"] == "s1"
    assert kwargs["params"]["landevice"] == hosts_mod.LANDEVICE_QUERY
