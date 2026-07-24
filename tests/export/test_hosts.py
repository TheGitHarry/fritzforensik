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
