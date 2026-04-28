"""Offline-Tests für Port-Forward-Extractor (indexierte Iteration)."""
from __future__ import annotations

from unittest.mock import MagicMock

from legacy_export.client import Tr064Disabled, Tr064Error
from legacy_export.extractors import portforward as pf_mod


def test_extract_iterates_to_count():
    client = MagicMock()
    client.tr064_call.side_effect = [
        {"NewPortMappingNumberOfEntries": "2"},
        {
            "NewRemoteHost": "",
            "NewExternalPort": "443",
            "NewProtocol": "TCP",
            "NewInternalPort": "443",
            "NewInternalClient": "192.168.178.50",
            "NewEnabled": "1",
            "NewPortMappingDescription": "HTTPS to NAS",
            "NewLeaseDuration": "0",
        },
        {
            "NewRemoteHost": "",
            "NewExternalPort": "9999",
            "NewProtocol": "UDP",
            "NewInternalPort": "9999",
            "NewInternalClient": "192.168.178.60",
            "NewEnabled": "0",
            "NewPortMappingDescription": "Game Server",
            "NewLeaseDuration": "3600",
        },
    ]
    records = pf_mod.extract(client)
    assert len(records) == 2
    assert records[0]["external_port"] == "443"
    assert records[0]["protocol"] == "TCP"
    assert records[0]["description"] == "HTTPS to NAS"
    assert records[0]["index"] == 0
    assert records[1]["lease_duration"] == "3600"
    assert records[1]["index"] == 1


def test_extract_breaks_on_oob_error():
    """Wenn der Box-Count zu hoch ist, soll der OOB-Code 713 sauber stoppen."""
    client = MagicMock()
    client.tr064_call.side_effect = [
        {"NewPortMappingNumberOfEntries": "5"},
        {
            "NewRemoteHost": "",
            "NewExternalPort": "80",
            "NewProtocol": "TCP",
            "NewInternalPort": "80",
            "NewInternalClient": "192.168.178.50",
            "NewEnabled": "1",
            "NewPortMappingDescription": "HTTP",
            "NewLeaseDuration": "0",
        },
        Tr064Error("OOB", error_code=713),
    ]
    records = pf_mod.extract(client)
    assert len(records) == 1
    assert records[0]["external_port"] == "80"


def test_extract_returns_empty_on_count_disabled():
    client = MagicMock()
    client.tr064_call.side_effect = Tr064Disabled("aus")
    assert pf_mod.extract(client) == []


def test_extract_returns_empty_on_count_error():
    client = MagicMock()
    client.tr064_call.side_effect = Tr064Error("transport")
    assert pf_mod.extract(client) == []


def test_extract_returns_empty_when_count_is_zero():
    client = MagicMock()
    client.tr064_call.return_value = {"NewPortMappingNumberOfEntries": "0"}
    assert pf_mod.extract(client) == []
