"""Offline-Tests für Storage-Extractor (X_AVM-DE_Storage)."""
from __future__ import annotations

from unittest.mock import MagicMock

from legacy_export.client import Tr064Disabled, Tr064Error
from legacy_export.extractors import storage as storage_mod


def test_extract_with_active_storage_and_users():
    client = MagicMock()
    client.tr064_call.side_effect = [
        # GetInfo
        {
            "NewEnable": "1",
            "NewStatus": "OK",
            "NewSMBEnable": "1",
            "NewSMBNetbiosName": "FRITZ-NAS",
            "NewSMBWorkgroupName": "WORKGROUP",
            "NewFTPEnable": "1",
            "NewFTPStatus": "OK",
            "NewFTPInternetAccessEnabled": "0",
            "NewWebDAVEnable": "0",
            "NewMyfritzPermitInternetAccess": "0",
        },
        # GetUserInfo[0]
        {"NewUsername": "admin", "NewRights": "rw", "NewEnabled": "1"},
        # GetUserInfo[1]
        {"NewUsername": "guest", "NewRights": "r", "NewEnabled": "0"},
        # GetUserInfo[2] → OOB
        Tr064Error("OOB", error_code=713),
    ]
    records = storage_mod.extract(client)
    types = [r["record_type"] for r in records]
    assert "storage_info" in types
    assert types.count("storage_user") == 2
    info = next(r for r in records if r["record_type"] == "storage_info")
    assert info["enable"] == "1"
    assert info["smb_netbios_name"] == "FRITZ-NAS"
    users = [r for r in records if r["record_type"] == "storage_user"]
    assert users[0]["username"] == "admin"
    assert users[0]["index"] == 0
    assert users[1]["username"] == "guest"


def test_extract_returns_empty_when_storage_disabled():
    client = MagicMock()
    client.tr064_call.side_effect = Tr064Disabled("kein USB")
    assert storage_mod.extract(client) == []


def test_extract_returns_empty_when_storage_error():
    client = MagicMock()
    client.tr064_call.side_effect = Tr064Error("transport")
    assert storage_mod.extract(client) == []


def test_extract_returns_only_info_when_no_users():
    client = MagicMock()
    client.tr064_call.side_effect = [
        {"NewEnable": "1", "NewStatus": "OK"},
        Tr064Error("OOB", error_code=713),
    ]
    records = storage_mod.extract(client)
    assert len(records) == 1
    assert records[0]["record_type"] == "storage_info"
