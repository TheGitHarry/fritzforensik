"""SSDP-Auto-Discovery für FRITZ!Box im LAN.

Sendet eine UPnP M-SEARCH-Anfrage an die SSDP-Multicast-Adresse und sammelt
Antworten von InternetGatewayDevice-Geräten. AVM-Filter zweistufig: zuerst
SERVER-Header, dann optional die unter LOCATION verlinkte Device-Description-XML
auf "FRITZ!Box" prüfen — filtert FRITZ!Repeater zuverlässig raus.
"""
from __future__ import annotations

import logging
import socket
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

SSDP_MULTICAST = "239.255.255.250"
SSDP_PORT = 1900
SSDP_ST_IGD = "urn:schemas-upnp-org:device:InternetGatewayDevice:1"
SSDP_ST_ALL = "ssdp:all"
DEFAULT_TIMEOUT = 3.0
DEFAULT_XML_TIMEOUT = 2.0

#: Schemata, die eine LOCATION tragen darf. Jedes Gerät im LAN, das mit einem
#: SERVER-Header voller "AVM" antwortet, bestimmt diese URL — und ``urlopen``
#: nähme auch ``file://``.
ERLAUBTE_SCHEMATA = ("http", "https")

#: Obergrenze für die Device-Description. Eine IGD-Beschreibung einer FRITZ!Box
#: liegt im niedrigen zweistelligen KB-Bereich; 2 MB lassen jeden echten Fall
#: durch und beenden einen endlosen Datenstrom. Der Socket-Timeout allein
#: genügt nicht: Er greift je Lesevorgang, nicht auf die Gesamtmenge.
MAX_DESC_BYTES = 2_000_000

log = logging.getLogger(__name__)


def _build_msearch(st: str) -> bytes:
    return (
        "M-SEARCH * HTTP/1.1\r\n"
        f"HOST: {SSDP_MULTICAST}:{SSDP_PORT}\r\n"
        'MAN: "ssdp:discover"\r\n'
        "MX: 2\r\n"
        f"ST: {st}\r\n"
        "\r\n"
    ).encode("ascii")


# Zwei M-SEARCH-Pakete pro Lauf: gezieltes IGD-ST fängt Standard-FRITZ!Box,
# `ssdp:all` fängt Mesh-Master, die auf spezifische STs nicht antworten,
# aber jede SSDP-Anfrage beantworten. Filter via SERVER-Header (AVM) bleibt.
M_SEARCH_PACKETS: tuple[bytes, ...] = (
    _build_msearch(SSDP_ST_IGD),
    _build_msearch(SSDP_ST_ALL),
)
# Backwards-Compat-Alias für externe Importe
M_SEARCH = M_SEARCH_PACKETS[0]


@dataclass
class DiscoveredBox:
    ip: str
    server: str = ""
    location: str = ""
    friendly_name: str = ""
    model_name: str = ""
    model_description: str = ""

    def url_https(self) -> str:
        return f"https://{self.ip}"

    def to_dict(self) -> dict:
        return asdict(self)


def parse_ssdp_response(raw: bytes) -> dict | None:
    """Parst eine SSDP-Antwort (HTTP-over-UDP).

    Gibt Header-Dict zurück, falls SERVER-Header AVM-Substring enthält;
    sonst None (bei Fremdgeräten oder Parse-Fehler).
    """
    try:
        text = raw.decode("ascii", errors="replace")
    except Exception:
        return None
    lines = text.split("\r\n")
    if not lines or not lines[0].upper().startswith("HTTP/"):
        return None
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line or ":" not in line:
            continue
        k, _, v = line.partition(":")
        headers[k.strip().upper()] = v.strip()
    if "AVM" not in headers.get("SERVER", "").upper():
        return None
    return headers


def parse_device_xml(xml_bytes: bytes) -> dict:
    """Liest friendlyName/modelName/modelDescription aus IGD-Description-XML."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return {}
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}", 1)[0] + "}"
    device = root.find(f"{ns}device")
    if device is None:
        return {}
    return {
        "friendly_name": (device.findtext(f"{ns}friendlyName") or "").strip(),
        "model_name": (device.findtext(f"{ns}modelName") or "").strip(),
        "model_description": (device.findtext(f"{ns}modelDescription") or "").strip(),
    }


def _fetch_device_xml(location: str, timeout: float) -> bytes:
    """Device-Description unter ``location`` holen — begrenzt und nur über HTTP(S).

    ``location`` ist **unauthentifizierte Fremdeingabe**: Sie stammt aus einer
    UDP-Antwort, die jedes Gerät im eigenen Netz schicken kann, und wird
    verarbeitet, bevor irgendeine Anmeldung stattgefunden hat.

    Beides bleibt folgenlos für den Fund selbst: ``discover()`` fängt die Ausnahme
    ab und übernimmt die Box dann ohne XML-Metadaten — ``_is_fritzbox`` behandelt
    genau diesen Fall bereits.
    """
    schema = urlsplit(location).scheme.lower()
    if schema not in ERLAUBTE_SCHEMATA:
        raise ValueError(f"Unerwartetes Schema in LOCATION: {location!r}")
    with urllib.request.urlopen(location, timeout=timeout) as resp:
        return resp.read(MAX_DESC_BYTES)


def _is_fritzbox(box: DiscoveredBox) -> bool:
    """Sekundär-Filter: wenn XML-Metadaten vorliegen, müssen sie 'FRITZ!Box' tragen."""
    if not (box.model_description or box.model_name):
        return True
    haystack = f"{box.model_description} {box.model_name}"
    return "FRITZ!Box" in haystack


def _local_ipv4_interfaces() -> list[str]:
    """Best-effort-Enumeration lokaler IPv4-Adressen (ohne Loopback).

    Wird auf Windows als Fallback genutzt, wenn das OS-Routing keine
    Schnittstelle für Multicast wählt (typisch: WSAEHOSTUNREACH=10065).
    """
    ips: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith("127."))


def _msearch_once(timeout: float, iface: str | None) -> list[tuple[bytes, tuple]]:
    """Sendet einmal M-SEARCH und sammelt Antworten bis Timeout.

    OSError wird hochgereicht — Aufrufer entscheidet über Fallback.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)
    sock.settimeout(timeout)
    if iface:
        sock.setsockopt(
            socket.IPPROTO_IP,
            socket.IP_MULTICAST_IF,
            socket.inet_aton(iface),
        )
    try:
        for packet in M_SEARCH_PACKETS:
            sock.sendto(packet, (SSDP_MULTICAST, SSDP_PORT))
        responses: list[tuple[bytes, tuple]] = []
        while True:
            try:
                data, addr = sock.recvfrom(8192)
            except socket.timeout:
                break
            responses.append((data, addr))
        return responses
    finally:
        sock.close()


def _collect_responses(timeout: float, iface: str | None) -> list[tuple[bytes, tuple]]:
    """M-SEARCH mit Windows-Fallback: bei OSError pro Schnittstelle nachprobieren."""
    if iface:
        try:
            return _msearch_once(timeout, iface)
        except OSError as e:
            log.warning("SSDP-Sendto auf --iface %s fehlgeschlagen: %s", iface, e)
            return []
    try:
        return _msearch_once(timeout, None)
    except OSError as e:
        candidates = _local_ipv4_interfaces()
        if not candidates:
            log.warning(
                "SSDP-Sendto via OS-Routing fehlgeschlagen (%s) und keine "
                "lokale IPv4-Schnittstelle gefunden.", e
            )
            return []
        log.warning(
            "SSDP-Sendto via OS-Routing fehlgeschlagen (%s); "
            "probiere lokale Schnittstellen: %s",
            e,
            ", ".join(candidates),
        )
        responses: list[tuple[bytes, tuple]] = []
        for ip in candidates:
            try:
                responses.extend(_msearch_once(timeout, ip))
            except OSError as e2:
                log.debug("SSDP-Sendto auf %s fehlgeschlagen: %s", ip, e2)
        return responses


def discover(
    timeout: float = DEFAULT_TIMEOUT,
    iface: str | None = None,
    enrich: bool = True,
) -> list[DiscoveredBox]:
    """Sendet SSDP M-SEARCH und sammelt FRITZ!Box-Antworten.

    `iface`: Source-IP der zu nutzenden Netzwerk-Schnittstelle für Multicast
    (z.B. "192.168.2.228"). Default: OS-Routing, mit Windows-Fallback auf
    Per-Interface-Send wenn das Routing scheitert (WSAEHOSTUNREACH).

    `enrich`: LOCATION-XML pro Antwort fetchen für friendly_name/model_*.
    Verlangsamt Discovery um Sekunden, ermöglicht aber Repeater-Filter.
    """
    responses = _collect_responses(timeout, iface)
    seen: dict[str, DiscoveredBox] = {}
    for data, addr in responses:
        headers = parse_ssdp_response(data)
        if headers is None:
            continue
        ip = addr[0]
        if ip in seen:
            continue
        box = DiscoveredBox(
            ip=ip,
            server=headers.get("SERVER", ""),
            location=headers.get("LOCATION", ""),
        )
        if enrich and box.location:
            try:
                info = parse_device_xml(
                    _fetch_device_xml(box.location, DEFAULT_XML_TIMEOUT)
                )
                box.friendly_name = info.get("friendly_name", "")
                box.model_name = info.get("model_name", "")
                box.model_description = info.get("model_description", "")
            except Exception:
                pass
        if not _is_fritzbox(box):
            continue
        seen[ip] = box
    return list(seen.values())
