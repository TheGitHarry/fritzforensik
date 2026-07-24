"""Offline-Tests für WAN-Extractor (Connection + Counters + DSL)."""
from __future__ import annotations

from unittest.mock import MagicMock

from fritzexport.client import Tr064Disabled, Tr064Error
from fritzexport.extractors import wan as wan_mod


def _make_client(call_map: dict[str, dict | Exception]):
    """MagicMock-Client, der pro action-Argument die passende Antwort liefert."""
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


def test_extract_full_dsl_box():
    client = _make_client({
        "GetStatusInfo": {
            "NewConnectionStatus": "Connected",
            "NewLastConnectionError": "ERROR_NONE",
            "NewUptime": "123456",
        },
        "GetExternalIPAddress": {"NewExternalIPAddress": "203.0.113.5"},
        "GetInfo": {
            "NewConnectionType": "IP_Routed",
            "NewDNSServers": "8.8.8.8,8.8.4.4",
            "NewMACAddress": "AA:BB:CC:DD:EE:FF",
            # WANDSL.GetInfo hat AVM-Felder:
            "NewStatus": "Up",
            "NewModulationType": "VDSL2",
            "NewUpstreamMaxRate": "40000",
            "NewDownstreamMaxRate": "100000",
            "NewUpstreamCurrRate": "39000",
            "NewDownstreamCurrRate": "98000",
            "NewUpstreamNoiseMargin": "120",
            "NewDownstreamNoiseMargin": "80",
            "NewUpstreamAttenuation": "100",
            "NewDownstreamAttenuation": "150",
        },
        "X_AVM_DE_GetExternalIPv6Address": {
            "NewExternalIPv6Address": "2001:db8::1",
            "NewPrefixLength": "64",
        },
        "GetTotalBytesSent": {"NewTotalBytesSent": "1234"},
        "GetTotalBytesReceived": {"NewTotalBytesReceived": "5678"},
        "GetTotalPacketsSent": {"NewTotalPacketsSent": "111"},
        "GetTotalPacketsReceived": {"NewTotalPacketsReceived": "222"},
        "GetCommonLinkProperties": {
            "NewWANAccessType": "DSL",
            "NewPhysicalLinkStatus": "Up",
            "NewLayer1UpstreamMaxBitRate": "40000000",
            "NewLayer1DownstreamMaxBitRate": "100000000",
        },
        "GetAddonInfos": {
            "NewX_AVM_DE_TotalBytesSent64": "9999999999",
            "NewX_AVM_DE_TotalBytesReceived64": "8888888888",
            "NewByteSendRate": "12345",
            "NewByteReceiveRate": "67890",
        },
    })
    records = wan_mod.extract(client)
    types = [r["record_type"] for r in records]
    assert "connection" in types
    assert "counters" in types
    assert "dsl" in types
    conn = next(r for r in records if r["record_type"] == "connection")
    assert conn["connection_status"] == "Connected"
    assert conn["uptime"] == "123456"
    assert conn["external_ipv4"] == "203.0.113.5"
    assert conn["external_ipv6"] == "2001:db8::1"
    counters = next(r for r in records if r["record_type"] == "counters")
    assert counters["total_bytes_sent"] == "1234"
    assert counters["bytes_sent_64"] == "9999999999"
    assert counters["wan_access_type"] == "DSL"
    dsl = next(r for r in records if r["record_type"] == "dsl")
    assert dsl["modulation_type"] == "VDSL2"
    assert dsl["upstream_curr_rate"] == "39000"


def test_extract_skips_dsl_on_fiber_box():
    """Fiber-/Cable-Boxen haben keinen WANDSLInterfaceConfig-Service."""
    call_map: dict[str, dict | Exception] = {
        "GetStatusInfo": {"NewConnectionStatus": "Connected", "NewUptime": "10"},
        "GetExternalIPAddress": {"NewExternalIPAddress": "203.0.113.7"},
        "GetInfo": Tr064Disabled("no DSL", error_code=606),
        "X_AVM_DE_GetExternalIPv6Address": Tr064Disabled("no v6"),
        "GetTotalBytesSent": {"NewTotalBytesSent": "1"},
        "GetTotalBytesReceived": {"NewTotalBytesReceived": "2"},
        "GetTotalPacketsSent": Tr064Disabled("no"),
        "GetTotalPacketsReceived": Tr064Disabled("no"),
        "GetCommonLinkProperties": {"NewWANAccessType": "Ethernet"},
        "GetAddonInfos": Tr064Disabled("no"),
    }
    client = _make_client(call_map)
    records = wan_mod.extract(client)
    types = [r["record_type"] for r in records]
    assert "connection" in types
    assert "counters" in types
    assert "dsl" not in types  # GetInfo war WANDSL-only und nicht zugänglich


def test_extract_returns_empty_when_all_services_unavailable():
    client = _make_client({})
    assert wan_mod.extract(client) == []


def test_extract_handles_partial_status():
    """Wenn nur GetStatusInfo geht, soll trotzdem ein connection-Record kommen."""
    call_map: dict[str, dict | Exception] = {
        "GetStatusInfo": {"NewConnectionStatus": "Connected", "NewUptime": "5"},
    }
    client = _make_client(call_map)
    records = wan_mod.extract(client)
    assert len(records) == 1
    assert records[0]["record_type"] == "connection"
    assert records[0]["connection_status"] == "Connected"
