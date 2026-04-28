"""Port-Forwards — TR-064 WANIPConnection:1.GetGenericPortMappingEntry, indexiert.

Forensisch wertvoll: jeder Forward ist ein potenzieller Eingangsweg von
außen — Beschreibung, Zielport/Protokoll, interner Client, Lease-Dauer
(0 = permanent, sonst UPnP-IGD-eingerichtete temporäre Mappings).

Iteration: erst `GetPortMappingNumberOfEntries` für die Anzahl, dann
0..N-1 via `GetGenericPortMappingEntry(NewPortMappingIndex=...)`. AVM
liefert UPnPError 713 wenn Index OOB — als Bound-Marker behandelt.
"""
from __future__ import annotations

import logging

from ..client import FritzClient, Tr064Disabled, Tr064Error

log = logging.getLogger(__name__)

WANIPCONN_SERVICE = "urn:dslforum-org:service:WANIPConnection:1"
WANIPCONN_CONTROL = "/upnp/control/wanipconnection1"
COUNT_ACTION = "GetPortMappingNumberOfEntries"
COUNT_RESULT_KEY = "NewPortMappingNumberOfEntries"
ENTRY_ACTION = "GetGenericPortMappingEntry"
_OOB_CODES = {713, 402, 714}


def extract(client: FritzClient) -> list[dict]:
    """Liefert pro Port-Mapping einen Record."""
    try:
        count_resp = client.tr064_call(
            WANIPCONN_SERVICE, WANIPCONN_CONTROL, COUNT_ACTION
        )
    except Tr064Disabled as e:
        log.info("TR-064 GetPortMappingNumberOfEntries nicht zugänglich: %s", e)
        return []
    except Tr064Error as e:
        log.warning("TR-064 GetPortMappingNumberOfEntries fehlgeschlagen: %s", e)
        return []
    try:
        count = int((count_resp.get(COUNT_RESULT_KEY) or "0").strip())
    except ValueError:
        return []
    records: list[dict] = []
    # Defensiver Index-Schutz: einige Boxen geben Count und brechen vor
    # dem letzten Index ab. Wir laufen bis Count, fangen 713 als End-Marker.
    for idx in range(count):
        try:
            entry = client.tr064_call(
                WANIPCONN_SERVICE,
                WANIPCONN_CONTROL,
                ENTRY_ACTION,
                args={"NewPortMappingIndex": str(idx)},
            )
        except Tr064Error as e:
            if e.error_code in _OOB_CODES:
                break
            log.warning("GetGenericPortMappingEntry[%d] fehlgeschlagen: %s", idx, e)
            continue
        records.append(
            {
                "index": idx,
                "remote_host": entry.get("NewRemoteHost", ""),
                "external_port": entry.get("NewExternalPort", ""),
                "protocol": entry.get("NewProtocol", ""),
                "internal_port": entry.get("NewInternalPort", ""),
                "internal_client": entry.get("NewInternalClient", ""),
                "enabled": entry.get("NewEnabled", ""),
                "description": entry.get("NewPortMappingDescription", ""),
                "lease_duration": entry.get("NewLeaseDuration", ""),
            }
        )
    return records
