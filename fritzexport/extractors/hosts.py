"""Hosts-Liste — TR-064 X_AVM-DE_GetHostListPath, XML-Fetch.

Liefert pro Host (LAN/WLAN/Guest) einen Record mit MAC, IP, Name, Aktiv-Flag,
Interface-Typ, Port-Speed, Lease-Restzeit, WAN-Access-Status, Modell-Hint und
Gast-/VPN-/Disallow-Flags. Reicher als data.lua/netDev (= wifi-Extractor):
TR-064 liefert AVM-Vendor-Felder, die in der UI nur indirekt sichtbar sind.

Pfad: TR-064 `X_AVM-DE_GetHostListPath` → relativer URL inkl. eigener SID →
XML-Fetch direkt auf Box-Host. Fallback auf Index-Iteration via
`GetGenericHostEntry` falls TR-064 die Path-Variante nicht beherrscht
(alte Firmware) — dabei deutlich weniger Felder.

Dazu als **zweite Quelle** die `landevice`-Liste aus `query.lua`, verbunden je MAC.
Sie bringt zwei Zeitangaben, die TR-064 nicht führt:

* ``firstused`` — „seit wann kennt diese Box dieses Gerät". Steht in **keiner** anderen
  Quelle des Bundles; `data.lua page=netDev` führt es nicht (Issue #38).
* ``lastused`` — „zuletzt gesehen". Gibt es sonst nur über `netDev`, und das schweigt
  vollständig, sobald die Box als IP-Client hinter einem anderen Router läuft.
  `query.lua` antwortet auch dann.

Die Geräteliste selbst ist **kein** Zugewinn: Gemessen an drei Boxen liefert
`query.lua` dieselbe Tabelle wie die TR-064-Hostliste (71/50/88 gegen 71/51/88). Nur
deshalb ist das hier eine Anreicherung und keine eigene Datenart.

Zwei Fallen, beide in Issue #38 belegt:

* `query.lua` antwortet **nur auf GET**. Per POST kommt `[]` mit HTTP 200 zurück, für
  jede Abfrage — das sieht aus wie „Endpunkt liefert nichts".
* ``0`` heißt **nicht gesetzt**, nicht „nie benutzt". Es wird deshalb zu ``""`` und
  niemals zu einem Datum im Jahr 1970. Ob überhaupt gefragt wurde, sagt das Feld
  ``landevice_uid``: Es steht auch dort, wo die Box keinen Zeitwert führt.

Die Epochen stammen aus der **Box-Uhr** und werden hier nicht korrigiert. Den Versatz
bildet `fritzreport` an einer Stelle für alle Quellen (siehe `_resolve_clock_offset`).
"""
from __future__ import annotations

import datetime as _dt
import logging
import xml.etree.ElementTree as ET

from ..client import FritzClient, Tr064Disabled, Tr064Error

log = logging.getLogger(__name__)

HOSTS_SERVICE = "urn:dslforum-org:service:Hosts:1"
HOSTS_CONTROL = "/upnp/control/hosts"
PATH_ACTION = "X_AVM-DE_GetHostListPath"
PATH_RESULT_KEY = "NewX_AVM-DE_HostListPath"
COUNT_ACTION = "GetHostNumberOfEntries"
COUNT_RESULT_KEY = "NewHostNumberOfEntries"
GENERIC_ACTION = "GetGenericHostEntry"
WEBUI_HOSTLIST_PATH = "/devicehostlist.lua"

QUERY_PATH = "/query.lua"

#: Genau die Felder, die verbunden oder als eigener Datensatz gebraucht werden.
LANDEVICE_QUERY = (
    "landevice:settings/landevice/list(UID,name,mac,ip,active,online,guest,"
    "interface,speed,firstused,lastused)"
)

# Felder im <Item>-XML der HostList-JSON-äh-XML-Datei. AVM liefert hier XML
# trotz „Liste" — Schema dokumentiert in der TR-064-Spez.
_ITEM_FIELDS = (
    "Index",
    "IPAddress",
    "AddressSource",
    "LeaseTimeRemaining",
    "MACAddress",
    "InterfaceType",
    "Active",
    "HostName",
    "X_AVM-DE_Port",
    "X_AVM-DE_Speed",
    "X_AVM-DE_UpdateAvailable",
    "X_AVM-DE_UpdateSuccessful",
    "X_AVM-DE_InfoURL",
    "X_AVM-DE_Model",
    "X_AVM-DE_URL",
    "X_AVM-DE_Guest",
    "X_AVM-DE_RequestClient",
    "X_AVM-DE_VPN",
    "X_AVM-DE_WANAccess",
    "X_AVM-DE_Disallow",
    "X_AVM-DE_IsMeshable",
    "X_AVM-DE_Priority",
    "X_AVM-DE_FriendlyName",
    "X_AVM-DE_FriendlyNameIsWriteable",
)


def _split_path_query(url_path: str) -> tuple[str, dict[str, str]]:
    if "?" not in url_path:
        return url_path, {}
    path, _, query = url_path.partition("?")
    params = dict(p.split("=", 1) for p in query.split("&") if "=" in p)
    return path, params


def _get_hostlist_path(client: FritzClient) -> str | None:
    try:
        resp = client.tr064_call(HOSTS_SERVICE, HOSTS_CONTROL, PATH_ACTION)
    except Tr064Disabled as e:
        log.info("TR-064 GetHostListPath nicht zugänglich: %s", e)
        return None
    except Tr064Error as e:
        log.warning("TR-064 GetHostListPath fehlgeschlagen: %s", e)
        return None
    return (resp.get(PATH_RESULT_KEY) or "").strip() or None


def _fetch_hostlist_xml(client: FritzClient, hostlist_path: str) -> bytes | None:
    path, params = _split_path_query(hostlist_path)
    # devicehostlist.lua gilt nur auf Port 49000, nicht auf Port 80 (→ 404).
    resp = client.session.get(client.tr064_url(path), params=params, timeout=30)
    resp.raise_for_status()
    return resp.content


def _parse_hostlist_xml(xml_bytes: bytes) -> list[dict]:
    """XML-Format: <List><Item>... <MACAddress/>...</Item>...</List>."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        log.warning("HostList-XML nicht parsebar: %s", e)
        return []
    records: list[dict] = []
    for item in root.iter("Item"):
        record: dict = {}
        for field in _ITEM_FIELDS:
            value = item.findtext(field)
            if value is not None:
                record[field] = value.strip()
        if record:
            record["source"] = "tr064_path"
            records.append(record)
    return records


def _iterate_generic_entries(client: FritzClient) -> list[dict]:
    """Alt-Firmware-Fallback: Index-für-Index via GetGenericHostEntry.

    Liefert deutlich weniger Felder, aber wenigstens MAC/IP/Name/Active.
    """
    try:
        resp = client.tr064_call(HOSTS_SERVICE, HOSTS_CONTROL, COUNT_ACTION)
    except (Tr064Disabled, Tr064Error) as e:
        log.warning("TR-064 GetHostNumberOfEntries fehlgeschlagen: %s", e)
        return []
    try:
        count = int((resp.get(COUNT_RESULT_KEY) or "0").strip())
    except ValueError:
        return []
    records: list[dict] = []
    for idx in range(count):
        try:
            entry = client.tr064_call(
                HOSTS_SERVICE,
                HOSTS_CONTROL,
                GENERIC_ACTION,
                args={"NewIndex": str(idx)},
            )
        except (Tr064Disabled, Tr064Error) as e:
            log.warning("GetGenericHostEntry[%d] fehlgeschlagen: %s", idx, e)
            continue
        records.append(
            {
                "Index": str(idx),
                "IPAddress": entry.get("NewIPAddress", ""),
                "AddressSource": entry.get("NewAddressSource", ""),
                "LeaseTimeRemaining": entry.get("NewLeaseTimeRemaining", ""),
                "MACAddress": entry.get("NewMACAddress", ""),
                "InterfaceType": entry.get("NewInterfaceType", ""),
                "Active": entry.get("NewActive", ""),
                "HostName": entry.get("NewHostName", ""),
                "source": "tr064_generic",
            }
        )
    return records


def _fetch_hostlist_xml_webui(client: FritzClient) -> bytes | None:
    """Fallback: devicehostlist.lua auf Port 49000 mit WebUI-SID.

    Liefert dasselbe vollständige XML wie der TR-064-Pfad, funktioniert
    aber auch ohne TR-064-Berechtigung des Users.
    """
    resp = client.session.get(
        client.tr064_url(WEBUI_HOSTLIST_PATH), params={"sid": client.sid}, timeout=30
    )
    resp.raise_for_status()
    return resp.content


def _iso_utc(value) -> str:
    """Unix-Epoch → ``YYYY-MM-DDTHH:MM:SSZ``; ``0`` und Unbrauchbares → ``""``."""
    try:
        epoch = int(str(value).strip() or 0)
    except (TypeError, ValueError):
        return ""
    if epoch <= 0:
        return ""
    try:
        return _dt.datetime.fromtimestamp(
            epoch, _dt.timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, ValueError):
        return ""


def _epoch(value) -> int:
    try:
        return max(0, int(str(value).strip() or 0))
    except (TypeError, ValueError):
        return 0


def _landevice_eintraege(antwort) -> list[dict]:
    """Antwort von ``query.lua`` in flache Einträge je Gerät übersetzen.

    Die Antwort ist ein Objekt, dessen Schlüssel der **Parametername** ist. AVM
    liefert die Liste je nach Firmware als Liste oder als Objekt mit laufenden
    Schlüsseln — beides wird hier gleich behandelt.
    """
    if not isinstance(antwort, dict):
        return []
    liste = antwort.get("landevice")
    if isinstance(liste, dict):
        liste = list(liste.values())
    if not isinstance(liste, list):
        return []
    eintraege: list[dict] = []
    for e in liste:
        if not isinstance(e, dict):
            continue
        mac = (e.get("mac") or "").strip()
        if not mac:
            continue
        eintraege.append({
            "mac": mac,
            "landevice_uid": e.get("UID") or "",
            "name": e.get("name") or "",
            "ip": e.get("ip") or "",
            "active": e.get("active") or "",
            "guest": e.get("guest") or "",
            "interface": e.get("interface") or "",
            "speed": e.get("speed") or "",
            "first_seen": _iso_utc(e.get("firstused")),
            "last_seen": _iso_utc(e.get("lastused")),
            "first_seen_epoch": _epoch(e.get("firstused")),
            "last_seen_epoch": _epoch(e.get("lastused")),
        })
    return eintraege


#: Was aus einem Eintrag in den verbundenen Datensatz übernommen wird.
_ZEITFELDER = ("landevice_uid", "first_seen", "last_seen",
               "first_seen_epoch", "last_seen_epoch")


def _merge_landevice(records: list[dict], eintraege: list[dict]) -> list[dict]:
    """Zeitangaben je MAC an die Hosts-Datensätze heften.

    Vorhandene Felder der Hostliste werden **nie** überschrieben — es kommen nur die
    Zeitangaben dazu. Ein Gerät, das nur ``query.lua`` kennt, wird als eigener
    Datensatz angehängt und trägt ``source: "query_lua"``; sonst verschwiege die Liste
    ein Gerät, das die Box sehr wohl kennt.
    """
    nach_mac = {(r.get("MACAddress") or "").upper(): r for r in records if r.get("MACAddress")}
    for e in eintraege:
        mac = e["mac"].upper()
        treffer = nach_mac.get(mac)
        if treffer is not None:
            for feld in _ZEITFELDER:
                treffer[feld] = e[feld]
            continue
        record = {
            "IPAddress": e["ip"],
            "MACAddress": mac,
            "InterfaceType": e["interface"],
            "Active": e["active"],
            "HostName": e["name"],
            "X_AVM-DE_Speed": e["speed"],
            "X_AVM-DE_Guest": e["guest"],
            "source": "query_lua",
        }
        record.update({feld: e[feld] for feld in _ZEITFELDER})
        records.append(record)
        nach_mac[mac] = record
    return records


def _fetch_landevice(client: FritzClient) -> list[dict]:
    """``landevice``-Liste holen — leere Liste, wo die Box sie nicht hergibt.

    Gefangen wird nur, was von der Box kommen kann: Netz- und HTTP-Fehler (erben von
    ``OSError``) und eine Antwort, die kein JSON ist (``ValueError``). **Nicht**
    gefangen werden Programmierfehler — ein zu breiter Auffang-Zweig hat hier einen
    ``TypeError`` als „Box antwortet nicht" verbucht, und der Extractor lief an jeder
    echten Box stumm durch.
    """
    try:
        resp = client.get(QUERY_PATH, params={"landevice": LANDEVICE_QUERY})
        resp.raise_for_status()
        return _landevice_eintraege(resp.json())
    except (OSError, ValueError) as e:
        log.info("query.lua landevice nicht abrufbar: %s", e)
        return []


def extract(client: FritzClient) -> list[dict]:
    """Vollständige Hosts-Liste der Box, inkl. Mesh-Repeater-Clients.

    Angereichert um ``first_seen``/``last_seen`` aus ``query.lua``, soweit die Box sie
    führt. Bleibt diese Quelle stumm, ist das Ergebnis dasselbe wie zuvor.
    """
    eintraege = _fetch_landevice(client)

    # 1. Versuch: TR-064-Pfad (liefert den reichsten Datensatz mit AVM-Feldern)
    path = _get_hostlist_path(client)
    if path:
        try:
            xml_bytes = _fetch_hostlist_xml(client, path)
        except Exception as e:
            log.warning("Hosts-XML-Fetch (TR-064-Pfad) fehlgeschlagen: %s", e)
            xml_bytes = None
        if xml_bytes:
            records = _parse_hostlist_xml(xml_bytes)
            if records:
                return _merge_landevice(records, eintraege)

    # 2. Versuch: devicehostlist.lua direkt auf Port 49000 (kein TR-064-Recht nötig)
    log.info("Hosts: TR-064-Pfad leer/nicht verfügbar — Fallback auf Port-49000-WebUI.")
    try:
        xml_bytes = _fetch_hostlist_xml_webui(client)
    except Exception as e:
        log.info("Hosts-XML-Fetch (Port-49000-WebUI) fehlgeschlagen: %s", e)
        xml_bytes = None
    if xml_bytes:
        records = _parse_hostlist_xml(xml_bytes)
        for r in records:
            r["source"] = "port49000_webui"
        if records:
            return _merge_landevice(records, eintraege)

    # 3. Letzter Ausweg: GetGenericHostEntry (nur bei sehr alter Firmware nötig)
    log.info("Hosts: Port-49000-WebUI fehlgeschlagen — Fallback auf Index-Iteration.")
    return _merge_landevice(_iterate_generic_entries(client), eintraege)
