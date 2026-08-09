"""WLAN-/Netzwerk-Geräteliste — zwei Quellen, ein Datensatz je Gerät.

1. **Web-UI** ``data.lua page=netDev`` — alle Netzwerkgeräte (LAN und WLAN, aktiv und
   passiv), mit Name und ``lastused``.
2. **TR-064** ``WLANConfiguration:1/:2/:3`` — die *aktuell assoziierten* WLAN-Clients
   je Funkinstanz, mit Signalstärke, Aushandlungsrate und Kanalbreite.

Warum beide: Der Web-UI-Weg **schweigt vollständig**, sobald die Box als IP-Client
hinter einem anderen Router läuft — sie antwortet dann mit einem Rumpf ohne
``active``/``passive`` (``nolist: true``). Gemessen an vier Boxen: Die eine, die
Router ist, liefert 64 Einträge; die drei im IP-Client-Modus null, während TR-064 dort
3, 5 und 7 assoziierte Geräte meldet. Forensisch ist der IP-Client-Modus der
**Normalfall**, denn am Auswerteplatz hängt die Box hinter dem Router des Prüfers.

Zusammengeführt wird **je MAC-Adresse**, nicht aneinandergehängt: Auf einer Box, die
Router ist, kennen beide Wege dieselben Geräte, und zwei Datensätze zählten sie im
Bericht doppelt. Der TR-064-Teil ergänzt dabei nur, was der Web-UI-Weg nicht führt —
ein vorhandener Wert wird **nie** überschrieben. Widersprechen sich die Quellen, bleibt
der Web-UI-Wert stehen und der abweichende TR-064-Wert im Feld ``raw_tr064``; das Feld
``source`` sagt je Datensatz, woher er stammt.

``GetSecurityKeys`` wird bewusst **nicht** aufgerufen — der Dienst gäbe WLAN-Passwörter
im Klartext heraus, und ein Report ist ein Dokument, das weitergereicht wird.
"""
from __future__ import annotations

import logging

from ..client import FritzClient, Tr064Disabled, Tr064Error

log = logging.getLogger(__name__)

DATA_PATH = "/data.lua"

#: Je Funkinstanz ein eigener Dienst. Üblich 1 = 2,4 GHz, 2 = 5 GHz, 3 = Gast — die
#: Zuordnung ist aber modellabhängig und wird deshalb **nicht** ausgewertet, sondern
#: als ``wlan_instance`` roh mitgeschrieben.
WLAN_SERVICE = "urn:dslforum-org:service:WLANConfiguration:{}"
WLAN_CONTROL = "/upnp/control/wlanconfig{}"
WLAN_INSTANCES = (1, 2, 3)


def _normalize(entry: dict, status: str) -> dict:
    ipv4 = entry.get("ipv4") if isinstance(entry.get("ipv4"), dict) else {}
    ipv6 = entry.get("ipv6") if isinstance(entry.get("ipv6"), dict) else {}
    options = entry.get("options") if isinstance(entry.get("options"), dict) else {}
    return {
        "source": "webui",
        "status": status,
        "name": entry.get("name", ""),
        "mac": entry.get("mac", ""),
        "ipv4": ipv4.get("ip", "") or entry.get("ip", ""),
        "ipv6": ipv6.get("ip", ""),
        "interface": entry.get("conn", "") or entry.get("type", ""),
        "port": entry.get("port", ""),
        "speed": entry.get("speed", ""),
        "is_guest": bool(options.get("guest", entry.get("guest", False))),
        "uid": entry.get("UID", ""),
        "last_seen": ipv4.get("lastused", "") or entry.get("lastused", "") or entry.get("last_used", ""),
        "raw": entry,
    }


def _tr064_clients(client: FritzClient) -> list[dict]:
    """Assoziierte WLAN-Clients je Funkinstanz — leer, wo TR-064 nicht mitspielt."""
    gefunden: list[dict] = []
    for i in WLAN_INSTANCES:
        service, control = WLAN_SERVICE.format(i), WLAN_CONTROL.format(i)
        try:
            info = client.tr064_call(service, control, "GetInfo")
            anzahl = int(client.tr064_call(
                service, control, "GetTotalAssociations"
            ).get("NewTotalAssociations", "0") or 0)
        except (Tr064Disabled, Tr064Error) as e:
            log.info("WLANConfiguration:%d nicht abrufbar: %s", i, e)
            continue
        except ValueError:
            continue

        for index in range(anzahl):
            try:
                dev = client.tr064_call(
                    service, control, "GetGenericAssociatedDeviceInfo",
                    {"NewAssociatedDeviceIndex": str(index)})
            except (Tr064Disabled, Tr064Error) as e:
                log.warning("WLANConfiguration:%d Gerät %d: %s", i, index, e)
                continue
            gefunden.append({
                "source": "tr064",
                # Assoziiert heißt: in diesem Moment am WLAN angemeldet.
                "status": "active",
                "name": "",              # TR-064 führt keinen Gerätenamen
                "mac": dev.get("NewAssociatedDeviceMACAddress", ""),
                "ipv4": dev.get("NewAssociatedDeviceIPAddress", ""),
                "ipv6": "",
                "interface": "802.11",
                "port": "",
                "speed": dev.get("NewX_AVM-DE_Speed", ""),
                "uid": "",
                "last_seen": "",         # TR-064 führt keinen Zeitstempel
                "auth_state": dev.get("NewAssociatedDeviceAuthState", ""),
                "signal_strength": dev.get("NewX_AVM-DE_SignalStrength", ""),
                "channel_width": dev.get("NewX_AVM-DE_ChannelWidth", ""),
                "wlan_instance": i,
                "wlan_ssid": info.get("NewSSID", ""),
                "wlan_standard": info.get("NewStandard", ""),
                "raw_tr064": dev,
            })
    return gefunden


#: Was der TR-064-Weg zusätzlich weiß. Nur diese Felder werden in einen vorhandenen
#: Web-UI-Datensatz übernommen — und auch das nur, wo er selbst nichts führt.
_TR064_ZUSATZ = ("speed", "ipv4", "auth_state", "signal_strength", "channel_width",
                 "wlan_instance", "wlan_ssid", "wlan_standard", "raw_tr064")


def extract(client: FritzClient) -> list[dict]:
    resp = client.post(
        DATA_PATH,
        data={"page": "netDev", "xhr": "1", "xhrId": "all", "lang": "de"},
    )
    resp.raise_for_status()
    try:
        payload = resp.json()
    except ValueError:
        payload = {}
    data = (payload.get("data") or {})
    devices: list[dict] = []
    for entry in data.get("active") or []:
        if isinstance(entry, dict):
            devices.append(_normalize(entry, status="active"))
    for entry in data.get("passive") or []:
        if isinstance(entry, dict):
            devices.append(_normalize(entry, status="passive"))

    nach_mac = {(d.get("mac") or "").upper(): d for d in devices if d.get("mac")}
    for tr in _tr064_clients(client):
        vorhanden = nach_mac.get((tr.get("mac") or "").upper())
        if vorhanden is None:
            devices.append(tr)
            continue
        for feld in _TR064_ZUSATZ:
            if not vorhanden.get(feld) and tr.get(feld):
                vorhanden[feld] = tr[feld]
        vorhanden["raw_tr064"] = tr["raw_tr064"]
        vorhanden["source"] = "webui+tr064"
    return devices
