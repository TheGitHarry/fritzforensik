"""WAN-/DSL-Status — TR-064 WANIPConnection + WANCommonInterfaceConfig + WANDSLInterfaceConfig.

Forensische Timeline-Anker: ConnectionStatus, Uptime (= Connection-Start),
externe IP, Total-Traffic-Counter, DSL-Layer1-Raten und -Qualitätsmetriken.
Drei Records:
  * `record_type:"connection"` — Status, Uptime, externe IPv4/IPv6
  * `record_type:"counters"` — Total Bytes/Packets gesendet/empfangen
  * `record_type:"dsl"` — DSL-Linkdaten (nur auf DSL-Boxen vorhanden)

Tolerant gegenüber fehlenden Services: Fiber-/Cable-Boxen haben kein
WANDSLInterfaceConfig — dann fehlt der DSL-Record, alle anderen kommen
weiter durch.
"""
from __future__ import annotations

import logging

from ..client import FritzClient, Tr064Disabled, Tr064Error

log = logging.getLogger(__name__)

WANIPCONN_SERVICE = "urn:dslforum-org:service:WANIPConnection:1"
WANIPCONN_CONTROL = "/upnp/control/wanipconnection1"
WANCOMMON_SERVICE = "urn:dslforum-org:service:WANCommonInterfaceConfig:1"
WANCOMMON_CONTROL = "/upnp/control/wancommonifconfig1"
WANDSL_SERVICE = "urn:dslforum-org:service:WANDSLInterfaceConfig:1"
WANDSL_CONTROL = "/upnp/control/wandslifconfig1"


def _safe_call(
    client: FritzClient,
    service: str,
    control: str,
    action: str,
    args: dict[str, str] | None = None,
) -> dict[str, str] | None:
    """TR-064-Aufruf, der bei Tr064-Fehlern None zurückgibt statt zu werfen."""
    try:
        return client.tr064_call(service, control, action, args=args)
    except Tr064Disabled as e:
        log.info("TR-064 %s.%s nicht zugänglich: %s", service, action, e)
        return None
    except Tr064Error as e:
        log.warning("TR-064 %s.%s fehlgeschlagen: %s", service, action, e)
        return None


def _connection_record(client: FritzClient) -> dict | None:
    status = _safe_call(client, WANIPCONN_SERVICE, WANIPCONN_CONTROL, "GetStatusInfo")
    extip = _safe_call(client, WANIPCONN_SERVICE, WANIPCONN_CONTROL, "GetExternalIPAddress")
    info = _safe_call(client, WANIPCONN_SERVICE, WANIPCONN_CONTROL, "GetInfo")
    ipv6 = _safe_call(
        client, WANIPCONN_SERVICE, WANIPCONN_CONTROL, "X_AVM_DE_GetExternalIPv6Address"
    )
    if status is None and extip is None and info is None:
        return None
    record: dict = {"record_type": "connection"}
    if status:
        record["connection_status"] = status.get("NewConnectionStatus", "")
        record["last_connection_error"] = status.get("NewLastConnectionError", "")
        record["uptime"] = status.get("NewUptime", "")
    if extip:
        record["external_ipv4"] = extip.get("NewExternalIPAddress", "")
    if info:
        record["connection_type"] = info.get("NewConnectionType", "")
        record["dns_servers"] = info.get("NewDNSServers", "")
        record["mac_address"] = info.get("NewMACAddress", "")
    if ipv6:
        record["external_ipv6"] = ipv6.get("NewExternalIPv6Address", "")
        record["ipv6_prefix_length"] = ipv6.get("NewPrefixLength", "")
    return record


def _counters_record(client: FritzClient) -> dict | None:
    total_sent = _safe_call(
        client, WANCOMMON_SERVICE, WANCOMMON_CONTROL, "GetTotalBytesSent"
    )
    total_recv = _safe_call(
        client, WANCOMMON_SERVICE, WANCOMMON_CONTROL, "GetTotalBytesReceived"
    )
    pkt_sent = _safe_call(
        client, WANCOMMON_SERVICE, WANCOMMON_CONTROL, "GetTotalPacketsSent"
    )
    pkt_recv = _safe_call(
        client, WANCOMMON_SERVICE, WANCOMMON_CONTROL, "GetTotalPacketsReceived"
    )
    link = _safe_call(
        client, WANCOMMON_SERVICE, WANCOMMON_CONTROL, "GetCommonLinkProperties"
    )
    addon = _safe_call(client, WANCOMMON_SERVICE, WANCOMMON_CONTROL, "GetAddonInfos")
    if not any([total_sent, total_recv, pkt_sent, pkt_recv, link, addon]):
        return None
    record: dict = {"record_type": "counters"}
    if total_sent:
        record["total_bytes_sent"] = total_sent.get("NewTotalBytesSent", "")
    if total_recv:
        record["total_bytes_received"] = total_recv.get("NewTotalBytesReceived", "")
    if pkt_sent:
        record["total_packets_sent"] = pkt_sent.get("NewTotalPacketsSent", "")
    if pkt_recv:
        record["total_packets_received"] = pkt_recv.get("NewTotalPacketsReceived", "")
    if link:
        record["wan_access_type"] = link.get("NewWANAccessType", "")
        record["physical_link_status"] = link.get("NewPhysicalLinkStatus", "")
        record["layer1_upstream_max"] = link.get("NewLayer1UpstreamMaxBitRate", "")
        record["layer1_downstream_max"] = link.get("NewLayer1DownstreamMaxBitRate", "")
    if addon:
        record["bytes_sent_64"] = addon.get("NewX_AVM_DE_TotalBytesSent64", "")
        record["bytes_received_64"] = addon.get("NewX_AVM_DE_TotalBytesReceived64", "")
        record["byte_send_rate"] = addon.get("NewByteSendRate", "")
        record["byte_receive_rate"] = addon.get("NewByteReceiveRate", "")
    return record


def _dsl_record(client: FritzClient) -> dict | None:
    info = _safe_call(client, WANDSL_SERVICE, WANDSL_CONTROL, "GetInfo")
    if info is None:
        return None
    return {
        "record_type": "dsl",
        "status": info.get("NewStatus", ""),
        "modulation_type": info.get("NewModulationType", ""),
        "upstream_max_rate": info.get("NewUpstreamMaxRate", ""),
        "downstream_max_rate": info.get("NewDownstreamMaxRate", ""),
        "upstream_curr_rate": info.get("NewUpstreamCurrRate", ""),
        "downstream_curr_rate": info.get("NewDownstreamCurrRate", ""),
        "upstream_noise_margin": info.get("NewUpstreamNoiseMargin", ""),
        "downstream_noise_margin": info.get("NewDownstreamNoiseMargin", ""),
        "upstream_attenuation": info.get("NewUpstreamAttenuation", ""),
        "downstream_attenuation": info.get("NewDownstreamAttenuation", ""),
        "raw": info,
    }


def extract(client: FritzClient) -> list[dict]:
    """WAN-Status, Traffic-Counter, DSL-Linkdaten als getrennte Records."""
    records: list[dict] = []
    for record in (
        _connection_record(client),
        _counters_record(client),
        _dsl_record(client),
    ):
        if record is not None:
            records.append(record)
    return records
