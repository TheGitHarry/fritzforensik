"""SSDP-Auto-Discovery für FRITZ!Box im LAN.

Sendet eine UPnP M-SEARCH-Anfrage an die SSDP-Multicast-Adresse und sammelt
Antworten von InternetGatewayDevice-Geräten. AVM-Filter zweistufig: zuerst
SERVER-Header, dann optional die unter LOCATION verlinkte Device-Description-XML
auf "FRITZ!Box" prüfen — filtert FRITZ!Repeater zuverlässig raus.
"""
from __future__ import annotations

import socket
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field

SSDP_MULTICAST = "239.255.255.250"
SSDP_PORT = 1900
SSDP_ST = "urn:schemas-upnp-org:device:InternetGatewayDevice:1"
DEFAULT_TIMEOUT = 3.0
DEFAULT_XML_TIMEOUT = 2.0

M_SEARCH = (
    "M-SEARCH * HTTP/1.1\r\n"
    f"HOST: {SSDP_MULTICAST}:{SSDP_PORT}\r\n"
    'MAN: "ssdp:discover"\r\n'
    "MX: 2\r\n"
    f"ST: {SSDP_ST}\r\n"
    "\r\n"
).encode("ascii")


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
    with urllib.request.urlopen(location, timeout=timeout) as resp:
        return resp.read()


def _is_fritzbox(box: DiscoveredBox) -> bool:
    """Sekundär-Filter: wenn XML-Metadaten vorliegen, müssen sie 'FRITZ!Box' tragen."""
    if not (box.model_description or box.model_name):
        return True
    haystack = f"{box.model_description} {box.model_name}"
    return "FRITZ!Box" in haystack


def discover(
    timeout: float = DEFAULT_TIMEOUT,
    iface: str | None = None,
    enrich: bool = True,
) -> list[DiscoveredBox]:
    """Sendet SSDP M-SEARCH und sammelt FRITZ!Box-Antworten.

    `iface`: Source-IP der zu nutzenden Netzwerk-Schnittstelle für Multicast
    (z.B. "192.168.2.228"). Default: OS-Routing.

    `enrich`: LOCATION-XML pro Antwort fetchen für friendly_name/model_*.
    Verlangsamt Discovery um Sekunden, ermöglicht aber Repeater-Filter.
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
        sock.sendto(M_SEARCH, (SSDP_MULTICAST, SSDP_PORT))
        seen: dict[str, DiscoveredBox] = {}
        while True:
            try:
                data, addr = sock.recvfrom(8192)
            except socket.timeout:
                break
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
    finally:
        sock.close()
