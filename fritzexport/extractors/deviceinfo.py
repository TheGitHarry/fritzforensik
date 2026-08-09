"""Selbstauskunft der Box — TR-064 ``DeviceInfo:1#GetInfo``.

Zwölf Felder, drei davon beantworten Fragen, die sonst offen bleiben:

- ``NewModelName`` — der **Handelsname im Klartext** („FRITZ!Box 7590"). Aus den
  Supportdaten ist sicher nur die ``HWRevision`` ablesbar; das Modell steht dort
  nicht durchgängig. Wer nur die Revision hat, braucht eine gepflegte Zuordnung —
  und die veraltet mit jedem neuen Gerät.
- ``NewUpTime`` — Laufzeit in **Sekunden**, unabhängig vom Textformat der
  ``uptime:``-Zeile der Supportdaten und vorhanden auf allen geprüften Ständen
  (anders als ``system_kpi``, das es erst ab FRITZ!OS 08.25 gibt).
- ``NewDeviceLog`` — das Ereignislog der Box, zweite Quelle neben der Datenart
  ``events`` (die es über das Web-UI holt).

Gerechnet wird hier **nichts** — kein Boot-Datum aus der Laufzeit. Dieselbe Regel
wie bei `boxtime`: Der Abzug erfasst, der Report leitet ab. Sonst stünde dieselbe
Rechnung an zwei Orten.

``NewSoftwareVersion`` trägt die Form ``<Firmware-Major>.<FRITZ!OS>`` (7590:
``154.08.25``). Der erste Teil ist **nicht** die ``HWRevision`` — die Box selbst
trennt beide in ihrem TR-064-Descriptor (``<HW>226</HW>`` neben ``<Major>154</Major>``).
"""
from __future__ import annotations

import logging

from ..client import FritzClient, Tr064Disabled, Tr064Error

log = logging.getLogger(__name__)

SERVICE = "urn:dslforum-org:service:DeviceInfo:1"
CONTROL = "/upnp/control/deviceinfo"


def extract(client: FritzClient) -> list[dict]:
    try:
        info = client.tr064_call(SERVICE, CONTROL, "GetInfo")
    except Tr064Disabled as e:
        log.info("TR-064 DeviceInfo.GetInfo nicht zugänglich: %s", e)
        return []
    except Tr064Error as e:
        log.warning("TR-064 DeviceInfo.GetInfo fehlgeschlagen: %s", e)
        return []

    roh_uptime = (info.get("NewUpTime", "") or "").strip()

    return [
        {
            "record_type":        "device_info",
            "model_name":         info.get("NewModelName", ""),
            "description":        info.get("NewDescription", ""),
            "product_class":      info.get("NewProductClass", ""),
            "manufacturer":       info.get("NewManufacturerName", ""),
            "manufacturer_oui":   info.get("NewManufacturerOUI", ""),
            "serial_number":      info.get("NewSerialNumber", ""),
            "software_version":   info.get("NewSoftwareVersion", ""),
            "hardware_version":   info.get("NewHardwareVersion", ""),
            "spec_version":       info.get("NewSpecVersion", ""),
            "provisioning_code":  info.get("NewProvisioningCode", ""),
            # Sekunden als Zahl, wenn es eine ist — sonst leer statt geraten.
            "uptime_s":           int(roh_uptime) if roh_uptime.isdigit() else "",
            "device_log":         info.get("NewDeviceLog", ""),
            "raw": info,
        }
    ]
