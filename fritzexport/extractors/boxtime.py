"""Uhrzeit der Box — TR-064 Time:1#GetInfo.

Erfasst wird, was die Box über ihre eigene Uhr sagt: aktuelle Ortszeit, Zeitzone und
NTP-Server. Der **Versatz** gegen die Referenzuhr wird hier bewusst *nicht* gerechnet —
das tut `fritzreport` aus der Klammer, die die beiden Markerzeilen um den Aufruf ziehen
(`UHRZEIT ANFRAGE`/`ANTWORT` im Sitzungslog). So liegt die Rechnung an einer Stelle und
gilt gleichermaßen für die zweite Quelle, den Kopf der Supportdaten.

Zwei Eigenheiten der Box, die beim Ändern zu beachten sind:

- ``NewCurrentLocalTime`` ist **sekundengenau** (kein Bruchteil). Eine Differenz
  ``box − referenz`` ist deshalb systematisch verschoben; maßgeblich ist die Klammer,
  nicht der Einzelwert.
- ``NewDaylightSavingsUsed`` meldet auf allen geprüften Boxen ``0``, **obwohl CEST
  aktiv ist**. Der Wert wird roh mitgeschrieben und darf nicht als Sommerzeit-Indikator
  ausgewertet werden — maßgeblich ist der UTC-Offset in ``NewCurrentLocalTime``
  (z. B. ``+02:00``).
"""
from __future__ import annotations

import logging

from fritzformat import uhr_anfrage_line, uhr_antwort_line, uhr_jetzt_iso

from ..client import FritzClient, Tr064Disabled, Tr064Error

log = logging.getLogger(__name__)

SERVICE = "urn:dslforum-org:service:Time:1"
CONTROL = "/upnp/control/time"

#: Kennung im Sitzungslog; `fritzreport` ordnet darüber Marker und Messung zu.
QUELLE = "tr064:time"


def extract(client: FritzClient) -> list[dict]:
    log.info(uhr_anfrage_line(QUELLE, uhr_jetzt_iso()))
    try:
        info = client.tr064_call(SERVICE, CONTROL, "GetInfo")
    except Tr064Disabled as e:
        log.info("TR-064 Time.GetInfo nicht zugänglich: %s", e)
        return []
    except Tr064Error as e:
        log.warning("TR-064 Time.GetInfo fehlgeschlagen: %s", e)
        return []
    finally:
        # Auch im Fehlerfall datiert, damit ein abgebrochener Versuch im Log sichtbar
        # bleibt; ohne Anfrage-Partner bildet der Report daraus keine Klammer.
        log.info(uhr_antwort_line(QUELLE, uhr_jetzt_iso()))

    return [
        {
            "record_type":                "box_clock",
            "box_current_local_time":     info.get("NewCurrentLocalTime", ""),
            "box_local_timezone":          info.get("NewLocalTimeZone", ""),
            "box_local_timezone_name":     info.get("NewLocalTimeZoneName", ""),
            "box_daylight_savings_used":   info.get("NewDaylightSavingsUsed", ""),
            "box_daylight_savings_start":  info.get("NewDaylightSavingsStart", ""),
            "box_daylight_savings_end":    info.get("NewDaylightSavingsEnd", ""),
            "box_ntp_server1":             info.get("NewNTPServer1", ""),
            "box_ntp_server2":             info.get("NewNTPServer2", ""),
            "raw": info,
        }
    ]
