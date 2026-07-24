"""Tests für TR-069-Extractor — mit und ohne TR-064."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from fritzexport.client import Tr064Disabled, Tr064Error
from fritzexport.extractors import tr069 as tr069_mod


def _make_client(call_map: dict[str, dict | Exception]):
    def _side_effect(service, control, action, args=None, **kwargs):
        result = call_map.get(action)
        if isinstance(result, Exception):
            raise result
        if result is None:
            raise Tr064Disabled(f"no fixture for {action}")
        return result

    client = MagicMock()
    client.tr064_call.side_effect = _side_effect
    return client


# --- Mit TR-064 ---

def test_extract_full_response():
    """TR-064 verfügbar, GetInfo liefert alle Felder."""
    client = _make_client({
        "GetInfo": {
            "NewURL":                       "https://tr069.isp.example.com/acs",
            "NewUsername":                  "01234567890",
            "NewPassword":                  "",
            "NewPeriodicInformEnable":      "1",
            "NewPeriodicInformInterval":    "86400",
            "NewConnectionRequestURL":      "http://192.168.2.1:56789/tr069",
            "NewConnectionRequestUsername": "fw-admin",
            "NewConnectionRequestPassword": "",
            "NewUpgradesManaged":           "1",
        }
    })
    records = tr069_mod.extract(client)
    assert len(records) == 1
    r = records[0]
    assert r["acs_url"] == "https://tr069.isp.example.com/acs"
    assert r["periodic_inform_enable"] == "1"
    assert r["periodic_inform_interval_sec"] == "86400"
    assert r["connection_request_url"] == "http://192.168.2.1:56789/tr069"
    assert r["upgrades_managed"] == "1"
    assert "raw" in r


def test_extract_acs_url_empty_when_tr069_inactive():
    """Box hat TR-069 konfiguriert aber ACS-URL ist leer (deaktiviert)."""
    client = _make_client({
        "GetInfo": {
            "NewURL":                    "",
            "NewPeriodicInformEnable":   "0",
            "NewPeriodicInformInterval": "0",
            "NewConnectionRequestURL":   "",
        }
    })
    records = tr069_mod.extract(client)
    assert len(records) == 1
    assert records[0]["acs_url"] == ""
    assert records[0]["periodic_inform_enable"] == "0"


# --- Ohne TR-064 ---

def test_extract_returns_empty_when_tr064_disabled():
    """TR-064 Stack aus: Tr064Disabled → leere Liste, kein Fehler."""
    client = _make_client({
        "GetInfo": Tr064Disabled("TR-064 Stack deaktiviert", error_code=401),
    })
    records = tr069_mod.extract(client)
    assert records == []


def test_extract_returns_empty_when_no_permission():
    """User hat keine TR-064-Berechtigung (UPnPError 606)."""
    client = _make_client({
        "GetInfo": Tr064Disabled("Keine TR-064-Berechtigung", error_code=606),
    })
    records = tr069_mod.extract(client)
    assert records == []


def test_extract_returns_empty_on_tr064_error():
    """Unerwarteter TR-064-Fehler → leere Liste."""
    client = _make_client({
        "GetInfo": Tr064Error("Timeout", error_code=0),
    })
    records = tr069_mod.extract(client)
    assert records == []
