"""Offline-Tests für den Telefonbuch-Extractor (Buchliste via data.lua, Export via firmwarecfg)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

from fritzexport.extractors import phonebook as pb

# ───────────────────────── Buchliste ─────────────────────────────────────────


def test_buchliste_aus_json():
    text = json.dumps({"data": {"phonebooks": [
        {"uniqueid": "0", "name": "Telefonbuch"},
        {"id": 1, "name": "Privat"},
    ]}})
    assert pb._parse_books_payload(text) == [
        {"id": 0, "name": "Telefonbuch"},
        {"id": 1, "name": "Privat"},
    ]


def test_buchliste_aus_html_mit_g_books():
    """Neuere FRITZ!OS-Stände liefern HTML mit einer JS-Initialisierung."""
    text = ('<div>…</div><script>var g_books = [{"id": "2", "name": "Geschäftlich"}];'
            "</script>")
    assert pb._parse_books_payload(text) == [{"id": 2, "name": "Geschäftlich"}]


def test_ungueltige_buecher_werden_uebergangen():
    text = json.dumps({"data": {"phonebooks": [
        "kein Objekt",
        {"name": "ohne ID"},           # id fällt auf -1 zurück
        {"id": "x", "name": "kaputt"},
        {"id": -5, "name": "negativ"},
        {"id": None, "name": "None"},
        {"id": 3},                     # ohne Namen
    ]}})
    assert pb._parse_books_payload(text) == [{"id": 3, "name": ""}]


def test_buchliste_unlesbar_leer():
    assert pb._parse_books_payload("<html>Anmeldung</html>") == []
    assert pb._parse_books_payload("g_books = [kaputt];") == []
    assert pb._parse_books_payload(json.dumps({"data": None})) == []


# ───────────────────────── Telefonbuch-XML ──────────────────────────────────

BUCH_XML = """<?xml version="1.0" encoding="utf-8"?>
<phonebooks><phonebook name="Telefonbuch">
  <contact>
    <person><realName> Erika Mustermann </realName></person>
    <telephony>
      <number type="home" vanity="" prio="1"> 0301234567 </number>
      <number type="mobile" vanity="ERIKA">01701234567</number>
      <number type="work"></number>
    </telephony>
  </contact>
  <contact>
    <telephony><number type="home">0309876543</number></telephony>
  </contact>
</phonebook></phonebooks>"""


def test_kontakte_mit_nummern_und_herkunft():
    contacts = pb._parse_xml(BUCH_XML, 0, "Telefonbuch")
    assert len(contacts) == 2
    erika = contacts[0]
    assert erika["phonebook_id"] == 0
    assert erika["phonebook_name"] == "Telefonbuch"
    assert erika["name"] == "Erika Mustermann"
    assert erika["numbers"] == [
        {"type": "home", "number": "0301234567", "vanity": ""},
        {"type": "mobile", "number": "01701234567", "vanity": "ERIKA"},
    ]


def test_leere_nummer_wird_weggelassen():
    contacts = pb._parse_xml(BUCH_XML, 0, "Telefonbuch")
    assert all(n["number"] for c in contacts for n in c["numbers"])


def test_kontakt_ohne_person_hat_leeren_namen():
    contacts = pb._parse_xml(BUCH_XML, 0, "Telefonbuch")
    assert contacts[1]["name"] == ""
    assert contacts[1]["numbers"] == [{"type": "home", "number": "0309876543", "vanity": ""}]


def test_kaputtes_xml_leer():
    assert pb._parse_xml("<phonebooks><contact>", 0, "x") == []


# ───────────────────────── extract ──────────────────────────────────────────


def test_extract_holt_jedes_buch_und_markiert_die_herkunft():
    client = MagicMock()
    client.sid = "abc"
    client.base_url = "https://fritz.box"
    client.post.return_value = MagicMock(text=json.dumps({"data": {"phonebooks": [
        {"id": 0, "name": "Telefonbuch"}, {"id": 1, "name": "Privat"},
    ]}}))
    client.session.post.return_value = MagicMock(text=BUCH_XML)

    entries = pb.extract(client)

    assert len(entries) == 4
    assert [e["phonebook_name"] for e in entries] == ["Telefonbuch"] * 2 + ["Privat"] * 2
    aufrufe = client.session.post.call_args_list
    assert len(aufrufe) == 2
    url = aufrufe[1].args[0]
    files = aufrufe[1].kwargs["files"]
    assert url == "https://fritz.box" + pb.FIRMWARECFG_PATH
    assert files["sid"] == (None, "abc")
    assert files["PhonebookId"] == (None, "1")


def test_extract_ohne_buecher_exportiert_nichts():
    client = MagicMock()
    client.post.return_value = MagicMock(text=json.dumps({"data": {"phonebooks": []}}))
    assert pb.extract(client) == []
    client.session.post.assert_not_called()
