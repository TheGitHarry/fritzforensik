"""TR-069-Konfiguration — TR-064 ManagementServer:1#GetInfo.

Forensisch relevant: ACS-URL (ISP-Server), ob Fernwartung aktiv ist,
Verbindungsintervall und ConnectionRequestURL (Eingangskanal für ISP).
Passwörter liefert die Box üblicherweise maskiert oder leer.
"""
from __future__ import annotations

import logging

from ..client import FritzClient, Tr064Disabled, Tr064Error

log = logging.getLogger(__name__)

SERVICE = "urn:dslforum-org:service:ManagementServer:1"
CONTROL = "/upnp/control/mgmsrv"


def _safe_call(client: FritzClient, action: str) -> dict[str, str] | None:
    try:
        return client.tr064_call(SERVICE, CONTROL, action)
    except Tr064Disabled as e:
        log.info("TR-064 ManagementServer.%s nicht zugänglich: %s", action, e)
        return None
    except Tr064Error as e:
        log.warning("TR-064 ManagementServer.%s fehlgeschlagen: %s", action, e)
        return None


def extract(client: FritzClient) -> list[dict]:
    info = _safe_call(client, "GetInfo")
    if info is None:
        return []

    return [
        {
            "acs_url":                      info.get("NewURL", ""),
            "username":                     info.get("NewUsername", ""),
            "password":                     info.get("NewPassword", ""),
            "periodic_inform_enable":       info.get("NewPeriodicInformEnable", ""),
            "periodic_inform_interval_sec": info.get("NewPeriodicInformInterval", ""),
            "connection_request_url":       info.get("NewConnectionRequestURL", ""),
            "connection_request_username":  info.get("NewConnectionRequestUsername", ""),
            "connection_request_password":  info.get("NewConnectionRequestPassword", ""),
            "upgrades_managed":             info.get("NewUpgradesManaged", ""),
            "raw": info,
        }
    ]
