"""XML aus Box- und LAN-Antworten: Entity-Deklarationen werden abgelehnt (#57)."""
import logging
import xml.etree.ElementTree as ET

import pytest

from fritzexport.discover import parse_device_xml
from fritzexport.xmlsafe import parse_xml

# Klassische Entity-Expansion ("billion laughs"), hier klein gehalten: Abgelehnt
# wird schon die Deklaration, die Tiefe spielt keine Rolle.
BOMBE = b"""<?xml version="1.0"?>
<!DOCTYPE lol [
  <!ENTITY lol "lol">
  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
]>
<root><friendlyName>&lol2;</friendlyName></root>"""

EXTERN = b"""<?xml version="1.0"?>
<!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]>
<r>&x;</r>"""


def test_normales_xml_wird_gelesen():
    root = parse_xml(b"<root><a>1</a></root>")
    assert root.findtext("a") == "1"


def test_str_wird_gelesen():
    assert parse_xml("<root><a>x</a></root>").findtext("a") == "x"


def test_doctype_ohne_entity_bleibt_erlaubt():
    """Ob echte Boxen ein DOCTYPE senden, ist nicht belegt — es darf nicht brechen."""
    root = parse_xml(b'<?xml version="1.0"?><!DOCTYPE root><root><a>1</a></root>')
    assert root.findtext("a") == "1"


@pytest.mark.parametrize("dokument", [BOMBE, EXTERN], ids=["expansion", "extern"])
def test_entity_wird_als_parseerror_abgelehnt(dokument, caplog):
    with caplog.at_level(logging.WARNING), pytest.raises(ET.ParseError):
        parse_xml(dokument)
    assert "Entity" in caplog.text


def test_kaputtes_xml_bleibt_parseerror():
    with pytest.raises(ET.ParseError):
        parse_xml(b"<root>")


# Dieselbe Expansion in der Form einer UPnP-Gerätebeschreibung: Ohne <device> gäbe
# parse_device_xml auch ungeschützt {} zurück, und der Test bewiese nichts.
GERAET_BOMBE = b"""<?xml version="1.0"?>
<!DOCTYPE root [
  <!ENTITY lol "lol">
  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
]>
<root xmlns="urn:schemas-upnp-org:device-1-0">
  <device><friendlyName>&lol2;</friendlyName><modelName>X</modelName></device>
</root>"""


def test_discovery_verwirft_bombe():
    """Die Gerätebeschreibung kommt vor jeder Anmeldung von beliebigen LAN-Geräten."""
    assert parse_device_xml(GERAET_BOMBE) == {}
