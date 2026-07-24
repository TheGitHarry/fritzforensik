"""DHCP-Server-Konfiguration — TR-064 LANHostConfigManagement:1.GetInfo.

Liefert Server-Status, Pool-Range (Min/Max-Address), Subnet, Gateway,
DNS-Server, Domain-Name, Lease-Time-Defaults. Per-Lease-Daten kommen aus
dem Hosts-Extractor (LeaseTimeRemaining pro Host).

Forensisch interessant: bei Box-Tausch oder DHCP-Reset ändern sich Pool-
Grenzen — Vergleich mit Hosts-Liste zeigt manuell vergebene IPs außerhalb
des Pools.
"""
from __future__ import annotations

import logging

from ..client import FritzClient, Tr064Disabled, Tr064Error

log = logging.getLogger(__name__)

DHCP_SERVICE = "urn:dslforum-org:service:LANHostConfigManagement:1"
DHCP_CONTROL = "/upnp/control/lanhostconfigmgm"


def extract(client: FritzClient) -> list[dict]:
    """Ein Konfigurations-Record. Bei deaktiviertem TR-064-Service: leer."""
    try:
        info = client.tr064_call(DHCP_SERVICE, DHCP_CONTROL, "GetInfo")
    except Tr064Disabled as e:
        log.info("TR-064 LANHostConfigManagement.GetInfo nicht zugänglich: %s", e)
        return []
    except Tr064Error as e:
        log.warning("TR-064 LANHostConfigManagement.GetInfo fehlgeschlagen: %s", e)
        return []
    record = {
        "record_type": "dhcp_config",
        "dhcp_server_enable": info.get("NewDHCPServerEnable", ""),
        "dhcp_server_configurable": info.get("NewDHCPServerConfigurable", ""),
        "dhcp_relay": info.get("NewDHCPRelay", ""),
        "min_address": info.get("NewMinAddress", ""),
        "max_address": info.get("NewMaxAddress", ""),
        "reserved_addresses": info.get("NewReservedAddresses", ""),
        "subnet_mask": info.get("NewSubnetMask", ""),
        "domain_name": info.get("NewDomainName", ""),
        "ip_routers": info.get("NewIPRouters", ""),
        "dns_servers": info.get("NewDNSServers", ""),
        "subnet_mask_configurable": info.get("NewSubnetMaskConfigurable", ""),
        "ip_routers_configurable": info.get("NewIPRoutersConfigurable", ""),
        "dns_servers_configurable": info.get("NewDNSServersConfigurable", ""),
        "raw": info,
    }
    return [record]
