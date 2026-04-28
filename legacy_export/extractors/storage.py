"""USB-/NAS-Storage — TR-064 X_AVM-DE_Storage:1.

Auf Boxen ohne USB-Stick gibt der Service leere/inaktive Werte oder ist
nicht zugänglich (606). Forensisch relevant: USB-Storage kann lokal
Daten halten (Backups, Notizen, exportierte Phonebooks), die im Backup
der Box selbst nicht enthalten sind. SMB/FTP-Shares sind ggf. extern
erreichbar — Indikator für mögliche Daten-Exfil-Wege.

Records:
  * `record_type:"storage_info"` — Haupt-Status
  * `record_type:"storage_user"` — pro konfiguriertem User (max 32)
"""
from __future__ import annotations

import logging

from ..client import FritzClient, Tr064Disabled, Tr064Error

log = logging.getLogger(__name__)

STORAGE_SERVICE = "urn:dslforum-org:service:X_AVM-DE_Storage:1"
STORAGE_CONTROL = "/upnp/control/x_storage"
MAX_USERS = 32
_OOB_CODES = {713, 714, 820}


def _info_record(client: FritzClient) -> dict | None:
    try:
        info = client.tr064_call(STORAGE_SERVICE, STORAGE_CONTROL, "GetInfo")
    except Tr064Disabled as e:
        log.info("TR-064 X_AVM-DE_Storage.GetInfo nicht zugänglich: %s", e)
        return None
    except Tr064Error as e:
        log.warning("TR-064 X_AVM-DE_Storage.GetInfo fehlgeschlagen: %s", e)
        return None
    return {
        "record_type": "storage_info",
        "enable": info.get("NewEnable", ""),
        "status": info.get("NewStatus", ""),
        "smb_enable": info.get("NewSMBEnable", ""),
        "smb_netbios_name": info.get("NewSMBNetbiosName", ""),
        "smb_workgroup_name": info.get("NewSMBWorkgroupName", ""),
        "ftp_enable": info.get("NewFTPEnable", ""),
        "ftp_status": info.get("NewFTPStatus", ""),
        "ftp_internet_access_enabled": info.get("NewFTPInternetAccessEnabled", ""),
        "webdav_enable": info.get("NewWebDAVEnable", ""),
        "myfritz_permit_internet_access": info.get(
            "NewMyfritzPermitInternetAccess", ""
        ),
        "raw": info,
    }


def _user_records(client: FritzClient) -> list[dict]:
    records: list[dict] = []
    for idx in range(MAX_USERS):
        try:
            user = client.tr064_call(
                STORAGE_SERVICE,
                STORAGE_CONTROL,
                "GetUserInfo",
                args={"NewIndex": str(idx)},
            )
        except Tr064Disabled:
            break
        except Tr064Error as e:
            if e.error_code in _OOB_CODES:
                break
            log.warning("GetUserInfo[%d] fehlgeschlagen: %s", idx, e)
            continue
        records.append(
            {
                "record_type": "storage_user",
                "index": idx,
                "username": user.get("NewUsername", ""),
                "rights": user.get("NewRights", ""),
                "enabled": user.get("NewEnabled", ""),
                "raw": user,
            }
        )
    return records


def extract(client: FritzClient) -> list[dict]:
    """Storage-Hauptrecord plus User-Records (falls überhaupt USB aktiv)."""
    records: list[dict] = []
    info = _info_record(client)
    if info is None:
        return []
    records.append(info)
    records.extend(_user_records(client))
    return records
