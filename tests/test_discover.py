"""Offline-Tests für SSDP-Discovery (parser-pure + socket-mock)."""
from __future__ import annotations

import socket
from unittest.mock import patch

from legacy_export.discover import (
    DiscoveredBox,
    _is_fritzbox,
    discover,
    parse_device_xml,
    parse_ssdp_response,
)

# Realistische FRITZ!Box-SSDP-Antwort (IGD-Service)
AVM_BOX_RESPONSE = (
    b"HTTP/1.1 200 OK\r\n"
    b"CACHE-CONTROL: max-age=1800\r\n"
    b"LOCATION: http://192.168.178.1:49000/igddesc.xml\r\n"
    b"SERVER: FRITZ!Box 7590 UPnP/1.0 AVM FRITZ!OS\r\n"
    b"ST: urn:schemas-upnp-org:device:InternetGatewayDevice:1\r\n"
    b"USN: uuid:75802409-bccb-40e7-8e6c-fb4fdb71b15d::urn:schemas-upnp-org:device:InternetGatewayDevice:1\r\n"
    b"\r\n"
)
# AVM-Repeater (würde SSDP-Filter passieren, aber XML zeigt ihn als Repeater aus)
AVM_REPEATER_RESPONSE = (
    b"HTTP/1.1 200 OK\r\n"
    b"LOCATION: http://192.168.178.50:49000/igddesc.xml\r\n"
    b"SERVER: FRITZ!Repeater 3000 UPnP/1.0 AVM FRITZ!OS\r\n"
    b"ST: urn:schemas-upnp-org:device:InternetGatewayDevice:1\r\n"
    b"\r\n"
)
NON_AVM_RESPONSE = (
    b"HTTP/1.1 200 OK\r\n"
    b"LOCATION: http://192.168.1.1:5431/dyndev/uuid:abc/desc.xml\r\n"
    b"SERVER: Linux/4.9.108 UPnP/1.0 SomeRouter/1.0\r\n"
    b"\r\n"
)
CORRUPT = b"\x00\x01\x02 not http"

FRITZBOX_IGD_XML = b"""<?xml version="1.0"?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
  <device>
    <deviceType>urn:schemas-upnp-org:device:InternetGatewayDevice:1</deviceType>
    <friendlyName>FRITZ!Box 7590</friendlyName>
    <modelName>FRITZ!Box 7590</modelName>
    <modelDescription>FRITZ!Box 7590 (UI)</modelDescription>
  </device>
</root>"""

REPEATER_IGD_XML = b"""<?xml version="1.0"?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
  <device>
    <friendlyName>FRITZ!Repeater 3000</friendlyName>
    <modelName>FRITZ!Repeater 3000</modelName>
    <modelDescription>FRITZ!Repeater 3000</modelDescription>
  </device>
</root>"""


def test_parse_ssdp_response_accepts_avm_box():
    h = parse_ssdp_response(AVM_BOX_RESPONSE)
    assert h is not None
    assert "AVM" in h["SERVER"]
    assert h["LOCATION"] == "http://192.168.178.1:49000/igddesc.xml"


def test_parse_ssdp_response_accepts_avm_repeater():
    # SSDP-Filter alleine lässt Repeater durch — XML-Filter trennt erst danach.
    h = parse_ssdp_response(AVM_REPEATER_RESPONSE)
    assert h is not None
    assert "AVM" in h["SERVER"]


def test_parse_ssdp_response_rejects_non_avm():
    assert parse_ssdp_response(NON_AVM_RESPONSE) is None


def test_parse_ssdp_response_handles_corrupt():
    assert parse_ssdp_response(CORRUPT) is None


def test_parse_device_xml_extracts_fritzbox_fields():
    info = parse_device_xml(FRITZBOX_IGD_XML)
    assert info["friendly_name"] == "FRITZ!Box 7590"
    assert info["model_name"] == "FRITZ!Box 7590"
    assert "FRITZ!Box" in info["model_description"]


def test_parse_device_xml_extracts_repeater_fields():
    info = parse_device_xml(REPEATER_IGD_XML)
    assert "Repeater" in info["model_name"]
    assert "FRITZ!Box" not in info["model_description"]


def test_parse_device_xml_handles_corrupt():
    assert parse_device_xml(b"<not valid xml") == {}


def test_is_fritzbox_filter_accepts_box():
    box = DiscoveredBox(
        ip="1.2.3.4",
        model_description="FRITZ!Box 7590",
        model_name="FRITZ!Box 7590",
    )
    assert _is_fritzbox(box) is True


def test_is_fritzbox_filter_rejects_repeater():
    box = DiscoveredBox(
        ip="1.2.3.4",
        model_description="FRITZ!Repeater 3000",
        model_name="FRITZ!Repeater 3000",
    )
    assert _is_fritzbox(box) is False


def test_is_fritzbox_filter_passes_when_xml_unavailable():
    # SERVER-Filter hat AVM bereits durchgelassen; ohne XML akzeptieren.
    box = DiscoveredBox(ip="1.2.3.4", server="AVM something")
    assert _is_fritzbox(box) is True


class _FakeSocket:
    """Minimaler socket.socket-Ersatz: liefert pre-canned Antworten, dann Timeout."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.sent: list[tuple[bytes, tuple]] = []

    def setsockopt(self, *args, **kwargs):
        pass

    def settimeout(self, t):
        pass

    def sendto(self, data, addr):
        self.sent.append((data, addr))

    def recvfrom(self, bufsize):
        if self._responses:
            return self._responses.pop(0)
        raise socket.timeout()

    def close(self):
        pass


def _fake_urlopen_factory(url_to_xml):
    class _Resp:
        def __init__(self, body):
            self._body = body
        def read(self):
            return self._body
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass
    def _fake(url, timeout=None):
        body = url_to_xml.get(url)
        if body is None:
            raise OSError(f"unmocked url: {url}")
        return _Resp(body)
    return _fake


def test_discover_returns_single_fritzbox():
    fake = _FakeSocket([(AVM_BOX_RESPONSE, ("192.168.178.1", 1900))])
    with patch("legacy_export.discover.socket.socket", return_value=fake), \
         patch(
             "legacy_export.discover._fetch_device_xml",
             return_value=FRITZBOX_IGD_XML,
         ):
        boxes = discover(timeout=0.1)
    assert len(boxes) == 1
    assert boxes[0].ip == "192.168.178.1"
    assert "FRITZ!Box" in boxes[0].model_name
    # Validate that M-SEARCH was actually sent
    assert len(fake.sent) == 1
    assert b"M-SEARCH" in fake.sent[0][0]


def test_discover_filters_out_repeater_via_xml():
    fake = _FakeSocket([
        (AVM_BOX_RESPONSE, ("192.168.178.1", 1900)),
        (AVM_REPEATER_RESPONSE, ("192.168.178.50", 1900)),
    ])
    xml_for = {
        "http://192.168.178.1:49000/igddesc.xml": FRITZBOX_IGD_XML,
        "http://192.168.178.50:49000/igddesc.xml": REPEATER_IGD_XML,
    }
    with patch("legacy_export.discover.socket.socket", return_value=fake), \
         patch(
             "legacy_export.discover.urllib.request.urlopen",
             new=_fake_urlopen_factory(xml_for),
         ):
        boxes = discover(timeout=0.1)
    assert len(boxes) == 1
    assert boxes[0].ip == "192.168.178.1"


def test_discover_returns_empty_on_timeout():
    fake = _FakeSocket([])
    with patch("legacy_export.discover.socket.socket", return_value=fake):
        boxes = discover(timeout=0.1)
    assert boxes == []


def test_discover_dedups_duplicate_responses():
    # Manche Boxen senden auf M-SEARCH mehrfach — gleiche IP, soll ein Eintrag sein.
    fake = _FakeSocket([
        (AVM_BOX_RESPONSE, ("192.168.178.1", 1900)),
        (AVM_BOX_RESPONSE, ("192.168.178.1", 1900)),
    ])
    with patch("legacy_export.discover.socket.socket", return_value=fake), \
         patch("legacy_export.discover._fetch_device_xml", return_value=FRITZBOX_IGD_XML):
        boxes = discover(timeout=0.1)
    assert len(boxes) == 1
