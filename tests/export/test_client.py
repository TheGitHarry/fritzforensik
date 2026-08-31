"""FritzClient — Schema-Default beim Login (#39).

Welches Schema gilt, wenn der Host ohne eines angegeben wird, ist **eine** Frage.
Sie wurde an zwei Stellen verschieden beantwortet: die CLI ergänzte ``https://``,
``FritzClient.login`` ``http://``. Über die CLI gewann HTTPS, weil die Normalisierung
vorher läuft — wer den Client direkt benutzt, bekam still Klartext. Seit #43 gibt es
nur noch ``client.normalize_host``; beide Wege rufen dieselbe Funktion.
"""
from __future__ import annotations

import pytest

from fritzexport import client as client_mod
from fritzexport.client import FritzClient


@pytest.fixture
def gesehen(monkeypatch):
    """Fängt die base_url ab, mit der der Login tatsächlich losläuft."""
    gesehen: list[str] = []

    class _Result:
        sid = "0123456789abcdef"

    def _login(base_url, username, password, session):
        gesehen.append(base_url)
        return _Result()

    monkeypatch.setattr(client_mod.auth, "login", _login)
    return gesehen


@pytest.mark.parametrize("host,erwartet", [
    ("fritz.box", "https://fritz.box"),
    ("192.168.2.1", "https://192.168.2.1"),
    ("fritz.box/", "https://fritz.box"),
    ("https://fritz.box", "https://fritz.box"),
    # Ein ausdrückliches http:// bleibt stehen — der Aufrufer hat sich entschieden.
    ("http://fritz.box", "http://fritz.box"),
])
def test_schema_default_ist_https(gesehen, host, erwartet):
    c = FritzClient.login(host, "admin", "geheim", verify_tls=False)
    assert gesehen == [erwartet]
    assert c.base_url == erwartet


def test_client_und_cli_teilen_sich_die_antwort(gesehen):
    """#39 hat die beiden Antworten in Deckung gebracht, #43 die Frage auf einen Ort
    gezogen. Geprüft wird deshalb nicht mehr, dass zwei Ergebnisse übereinstimmen,
    sondern dass es nur noch **eine** Funktion gibt, die sie liefert."""
    from fritzexport import cli, client

    assert cli.normalize_host is client.normalize_host

    FritzClient.login("fritz.box", "admin", "geheim", verify_tls=False)
    assert gesehen[0] == client.normalize_host("fritz.box")


# ─────────────────── SOAP-Body: Argumentwerte escapen (#40) ───────────────────

def _client_mit_aufzeichnung(monkeypatch):
    """FritzClient, der den gesendeten SOAP-Body festhält statt ihn zu schicken."""
    gesendet: dict = {}

    class _Resp:
        status_code = 200
        text = ('<?xml version="1.0"?><s:Envelope '
                'xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
                '<u:XResponse xmlns:u="urn:x"><NewX>ok</NewX>'
                '</u:XResponse></s:Body></s:Envelope>')

    class _Session:
        def post(self, url, data=None, **kw):
            gesendet["body"] = data
            return _Resp()

    c = FritzClient(base_url="https://fritz.box", sid="0" * 16, session=_Session(),
                    username="admin", password="geheim")
    return c, gesendet


def test_sonderzeichen_im_argument_werden_escaped(monkeypatch):
    """Ein Wert mit & < > erzeugte bisher kaputtes oder fremdbestimmtes XML.

    Heute übergeben alle Extractoren nur Ziffern — es ist keine Lücke, sondern eine
    gestellte Falle: Der erste Extractor, der einen Wert aus einer Box-Antwort
    zurück in einen Aufruf gibt (MAC, Gerätename, Telefonbucheintrag), macht sie
    scharf, ohne dass an dieser Stelle etwas auffällt.
    """
    c, gesendet = _client_mit_aufzeichnung(monkeypatch)
    c.tr064_call("urn:x", "/upnp/control/x", "X", {"NewName": 'A&B<C>"D"'})

    body = gesendet["body"]
    assert "<NewName>A&amp;B&lt;C&gt;" in body
    # Der Wert darf keine neuen Elemente aufmachen können
    assert "<C>" not in body


def test_eingeschleustes_element_bleibt_text(monkeypatch):
    """Gegenprobe an der schärfsten Form: ein kompletter Element-Schnipsel."""
    import xml.etree.ElementTree as ET

    c, gesendet = _client_mit_aufzeichnung(monkeypatch)
    c.tr064_call("urn:x", "/upnp/control/x", "X",
                 {"NewIndex": "0</NewIndex><NewEvil>1</NewEvil><NewIndex>"})

    root = ET.fromstring(gesendet["body"])
    assert root.find(".//NewEvil") is None, "Argumentwert hat ein Element erzeugt"
    werte = [e.text for e in root.iter("NewIndex")]
    assert werte == ["0</NewIndex><NewEvil>1</NewEvil><NewIndex>"]


def test_ziffern_bleiben_unveraendert(monkeypatch):
    """Keine Verhaltensänderung für die bestehenden Aufrufe."""
    c, gesendet = _client_mit_aufzeichnung(monkeypatch)
    c.tr064_call("urn:x", "/upnp/control/x", "X", {"NewIndex": "3"})
    assert "<NewIndex>3</NewIndex>" in gesendet["body"]
