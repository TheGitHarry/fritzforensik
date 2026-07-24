"""Offline-Tests für DHCP-Extractor (LANHostConfigManagement.GetInfo)."""
from __future__ import annotations

from unittest.mock import MagicMock

from fritzexport.client import Tr064Disabled, Tr064Error
from fritzexport.extractors import dhcp as dhcp_mod


def test_extract_full_record():
    client = MagicMock()
    client.tr064_call.return_value = {
        "NewDHCPServerEnable": "1",
        "NewDHCPServerConfigurable": "1",
        "NewDHCPRelay": "0",
        "NewMinAddress": "192.168.178.20",
        "NewMaxAddress": "192.168.178.200",
        "NewReservedAddresses": "",
        "NewSubnetMask": "255.255.255.0",
        "NewDomainName": "fritz.box",
        "NewIPRouters": "192.168.178.1",
        "NewDNSServers": "192.168.178.1",
    }
    records = dhcp_mod.extract(client)
    assert len(records) == 1
    rec = records[0]
    assert rec["record_type"] == "dhcp_config"
    assert rec["dhcp_server_enable"] == "1"
    assert rec["min_address"] == "192.168.178.20"
    assert rec["max_address"] == "192.168.178.200"
    assert rec["domain_name"] == "fritz.box"


def test_extract_returns_empty_on_tr064_disabled():
    client = MagicMock()
    client.tr064_call.side_effect = Tr064Disabled("aus")
    assert dhcp_mod.extract(client) == []


def test_extract_returns_empty_on_tr064_error():
    client = MagicMock()
    client.tr064_call.side_effect = Tr064Error("transport")
    assert dhcp_mod.extract(client) == []
