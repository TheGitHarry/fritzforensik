"""Tests für den Dienst-Abgleich — Descriptor-Parser und Extractor.

Der Extractor beantwortet, ob die Box Datenquellen anbietet, für die es keinen
Extractor gibt. Zwei Fehlermodi wären hier besonders tückisch, weil sie **grün
durchlaufen**: eine leere Vergleichsbasis (dann gilt alles als ungenutzt) und
ein Parser, der nur die oberste Geräteebene liest (dann fehlen genau die
verschachtelten Dienste). Beides wird unten gezielt geprüft.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from fritzexport.client import _parse_service_list
from fritzexport.extractors import services as services_mod

DESC_XML = b"""<?xml version="1.0"?>
<root xmlns="urn:dslforum-org:device-1-0">
 <device>
  <serviceList>
   <service>
    <serviceType>urn:dslforum-org:service:DeviceInfo:1</serviceType>
    <controlURL>/upnp/control/deviceinfo</controlURL>
    <SCPDURL>/deviceinfoSCPD.xml</SCPDURL>
   </service>
   <service>
    <serviceType>urn:dslforum-org:service:Hosts:1</serviceType>
    <controlURL>/upnp/control/hosts</controlURL>
    <SCPDURL>/hostsSCPD.xml</SCPDURL>
   </service>
  </serviceList>
  <deviceList>
   <device>
    <serviceList>
     <service>
      <serviceType>urn:dslforum-org:service:WANCommonInterfaceConfig:1</serviceType>
      <controlURL>/upnp/control/wancommonifconfig1</controlURL>
      <SCPDURL>/x.xml</SCPDURL>
     </service>
    </serviceList>
    <deviceList>
     <device>
      <serviceList>
       <service>
        <serviceType>urn:dslforum-org:service:WANIPConnection:1</serviceType>
        <controlURL>/upnp/control/wanipconnection1</controlURL>
        <SCPDURL>/y.xml</SCPDURL>
       </service>
      </serviceList>
     </device>
    </deviceList>
   </device>
  </deviceList>
 </device>
</root>"""


# --- Descriptor-Parser ---

def test_parser_findet_verschachtelte_dienste() -> None:
    """Boxen schachteln Geräte — nur die oberste Ebene zu lesen unterschlägt Dienste."""
    dienste = _parse_service_list(DESC_XML)
    typen = [d["service_type"] for d in dienste]

    assert len(dienste) == 4, f"verschachtelte Dienste übersehen: {typen}"
    assert "urn:dslforum-org:service:WANIPConnection:1" in typen, (
        "Dienst aus zweiter Verschachtelungsebene fehlt"
    )
    assert typen == sorted(typen), "Ausgabe sollte stabil sortiert sein"


def test_parser_liefert_control_url() -> None:
    dienste = {d["service_type"]: d for d in _parse_service_list(DESC_XML)}
    assert dienste["urn:dslforum-org:service:Hosts:1"]["control_url"] == "/upnp/control/hosts"


def test_parser_vertraegt_unbrauchbares_xml() -> None:
    """Kein Abbruch: ein fehlendes Verzeichnis ist kein Forensikfehler."""
    assert _parse_service_list(b"kein xml") == []
    assert _parse_service_list(b"") == []
    assert _parse_service_list(b"<root/>") == []


# --- Vergleichsbasis ---

def test_genutzte_services_ist_nicht_leer() -> None:
    """Wäre sie leer, gälte jeder Dienst als ungenutzt — und der Test bliebe grün."""
    genutzt = services_mod.genutzte_services()
    assert genutzt, "keine Extractor-Dienste gefunden — Einsammeln greift ins Leere"
    assert "urn:dslforum-org:service:Hosts:1" in genutzt
    assert "urn:dslforum-org:service:X_AVM-DE_TAM:1" in genutzt
    assert all(s.startswith("urn:") for s in genutzt)


# --- Extractor ---

def _client(dienste: list[dict]) -> MagicMock:
    client = MagicMock()
    client.tr064_services.return_value = dienste
    return client


def test_extract_markiert_genutzt_und_offen() -> None:
    client = _client([
        {"service_type": "urn:dslforum-org:service:Hosts:1",
         "control_url": "/upnp/control/hosts", "scpd_url": "/h.xml"},
        {"service_type": "urn:dslforum-org:service:WLANConfiguration:1",
         "control_url": "/upnp/control/wlanconfig1", "scpd_url": "/w.xml"},
    ])
    records = {r["service_type"]: r for r in services_mod.extract(client)}

    assert records["urn:dslforum-org:service:Hosts:1"]["genutzt"] is True
    assert records["urn:dslforum-org:service:WLANConfiguration:1"]["genutzt"] is False
    assert records["urn:dslforum-org:service:Hosts:1"]["control_url"] == "/upnp/control/hosts"


def test_extract_ohne_tr064_liefert_leere_liste(caplog) -> None:
    """Ohne TR-064-Zugang kein Abgleich — aber auch kein Absturz."""
    with caplog.at_level("INFO"):
        assert services_mod.extract(_client([])) == []
    assert any("nicht abrufbar" in r.message for r in caplog.records), (
        "stiller Fehlschlag: der Grund muss im Sitzungslog stehen"
    )


def test_extract_vertraegt_client_ohne_die_methode() -> None:
    """Ein Client ohne ``tr064_services`` darf den Abzug nicht abbrechen.

    Beim Einbau ist genau das passiert: Der unbedingte Aufruf ließ drei
    CLI-Tests mit AttributeError scheitern. Im Feld träfe es jeden älteren
    oder abweichenden Client — und würde den ganzen Lauf kosten, wegen einer
    Nebeninformation.
    """
    class OhneMethode:
        pass

    assert services_mod.extract(OhneMethode()) == []


def test_extract_gibt_keine_scpd_url_aus() -> None:
    """Die SCPD-URL ist ein internes Detail und gehört nicht ins Bundle."""
    client = _client([{"service_type": "urn:dslforum-org:service:Hosts:1",
                       "control_url": "/upnp/control/hosts", "scpd_url": "/h.xml"}])
    assert set(services_mod.extract(client)[0]) == {"service_type", "control_url", "genutzt"}
