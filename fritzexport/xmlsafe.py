"""XML aus Box- und LAN-Antworten parsen, ohne Entity-Expansion (#57).

Jede XML-Antwort, die fritzexport liest, ist Fremdeingabe — die Gerätebeschreibung
aus der SSDP-``LOCATION`` sogar von beliebigen Geräten im LAN, vor jeder Anmeldung.
``xml.etree`` expandiert Entities; mit Expat unter 2.7.2 reicht ein kleines
Dokument, um den Abzug aufzuhängen (Python-Doku, „XML security").

``defusedxml`` lehnt jede ``<!ENTITY>``-Deklaration ab. Ein bloßes ``<!DOCTYPE>``
bleibt erlaubt (``forbid_dtd`` steht bewusst auf dem Standard ``False``): Ob echte
Boxen eines senden, lässt sich am Korpus nicht prüfen, die rohen Antworten liegen
dort nicht vor.

Die Ausnahmen von defusedxml leiten von ``ValueError`` ab, nicht von
``ET.ParseError``. Sie werden hier übersetzt, damit die vorhandenen
``except ET.ParseError`` an jeder Aufrufstelle weiter greifen.
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring as _defused_fromstring

log = logging.getLogger(__name__)


def parse_xml(data: str | bytes) -> ET.Element:
    """Wie ``ET.fromstring``, aber Entities führen zu ``ET.ParseError``."""
    try:
        return _defused_fromstring(data)
    except DefusedXmlException as e:
        # Für die Untersuchung ein Befund: Kein Box-Dienst braucht Entities.
        log.warning("XML-Antwort abgelehnt, sie deklariert eine Entity (%s)",
                    type(e).__name__)
        raise ET.ParseError(f"Entity-Deklaration abgelehnt: {type(e).__name__}") from e
