"""Offline-Tests für TAM-Extractor (XML-Parser, HTML-Fallback, SOAP-Helpers)."""
from __future__ import annotations

import pytest

from fritzexport.client import (
    Tr064Disabled,
    Tr064Error,
    _parse_soap_fault,
    _parse_soap_response,
)
from fritzexport.extractors.tam import (
    _parse_message_xml,
    _parse_webui_rows,
)


GETMESSAGELIST_RESPONSE = """<?xml version="1.0"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
<s:Body>
<u:GetMessageListResponse xmlns:u="urn:dslforum-org:service:X_AVM-DE_TAM:1">
<NewURL>http://192.168.178.1:49000/tamcalllist.lua?sid=abc&amp;tamindex=0</NewURL>
</u:GetMessageListResponse>
</s:Body>
</s:Envelope>"""

UPNP_FAULT_401 = """<?xml version="1.0"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
<s:Body><s:Fault><faultcode>s:Client</faultcode><faultstring>UPnPError</faultstring>
<detail><UPnPError xmlns="urn:schemas-upnp-org:control-1-0">
<errorCode>401</errorCode><errorDescription>Invalid Action</errorDescription>
</UPnPError></detail></s:Fault></s:Body></s:Envelope>"""

UPNP_FAULT_606 = UPNP_FAULT_401.replace("401", "606").replace("Invalid Action", "Action not authorized")
UPNP_FAULT_713 = UPNP_FAULT_401.replace("401", "713").replace("Invalid Action", "Specified Array Index Invalid")

TAM_MESSAGE_LIST_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Root>
<!-- index:0 -->
<!-- tam calls:2 -->
<Message>
<Index>1</Index>
<Tam>0</Tam>
<Called>4133051</Called>
<Date>28.04.26 21:12</Date>
<Duration>0:01</Duration>
<Inbook>1</Inbook>
<Name>Papa</Name>
<New>1</New>
<Number>017644551736</Number>
<Path>/download.lua?path=/data/tam/rec/rec.0.001</Path>
</Message>
<Message>
<Index>0</Index>
<Tam>0</Tam>
<Called>4133051</Called>
<Date>28.04.26 21:10</Date>
<Duration>0:01</Duration>
<Inbook>0</Inbook>
<Name></Name>
<New>0</New>
<Number>017644551736</Number>
<Path>/download.lua?path=/data/tam/rec/rec.0.000</Path>
</Message>
</Root>"""


def test_parse_soap_response_extracts_args():
    args = _parse_soap_response(GETMESSAGELIST_RESPONSE, "GetMessageList")
    assert args["NewURL"].startswith("http://192.168.178.1:49000/tamcalllist.lua")


def test_parse_soap_response_handles_corrupt():
    with pytest.raises(Tr064Error):
        _parse_soap_response("not xml", "GetSomething")


def test_parse_soap_fault_codes():
    code, desc = _parse_soap_fault(UPNP_FAULT_401)
    assert code == 401
    assert "Invalid Action" in desc

    code, desc = _parse_soap_fault(UPNP_FAULT_606)
    assert code == 606

    code, desc = _parse_soap_fault(UPNP_FAULT_713)
    assert code == 713


def test_tr064_disabled_is_subclass_of_tr064_error():
    assert issubclass(Tr064Disabled, Tr064Error)


def test_parse_message_xml_extracts_two_messages():
    msgs = _parse_message_xml(TAM_MESSAGE_LIST_XML, tam_index=0)
    assert len(msgs) == 2

    # Index 1 ist neuer (reverse-chronologisch)
    by_idx = {m["message_index"]: m for m in msgs}

    m1 = by_idx[1]
    assert m1["tam_index"] == 0
    assert m1["caller_name"] == "Papa"
    assert m1["caller_number"] == "017644551736"
    assert m1["called_number"] == "4133051"
    assert m1["date"] == "28.04.26 21:12"
    assert m1["duration"] == "0:01"
    assert m1["is_new"] is True
    assert m1["in_phonebook"] is True
    assert m1["audio_path"] == "/download.lua?path=/data/tam/rec/rec.0.001"

    m0 = by_idx[0]
    assert m0["is_new"] is False
    assert m0["in_phonebook"] is False
    assert m0["caller_name"] == ""


def test_parse_message_xml_handles_corrupt():
    assert _parse_message_xml("<not valid", 0) == []


def test_parse_message_xml_handles_empty_root():
    assert _parse_message_xml("<Root></Root>", 0) == []


WEBUI_TABLE_HTML = """
<table id="uiTamCalls" class="zebra">
  <tr class="thead"><th></th><th>Datum</th><th>Name/Rufnummer</th><th>Eigene</th><th>Dauer</th><th></th></tr>
  <tr><td class="newicon"><img src="/x.svg"/></td>
      <td>28.04.26 21:12</td><td>Papa</td><td>4133051</td><td>0:01</td>
      <td><a href="/download.lua?path=/data/tam/rec/rec.0.001">Download</a></td></tr>
  <tr><td></td><td>28.04.26 21:10</td><td>017644551736</td><td>4133051</td><td>0:01</td>
      <td><a href="/download.lua?path=/data/tam/rec/rec.0.000">Download</a></td></tr>
</table>
"""


def test_parse_webui_rows_extracts_messages_and_audio_paths():
    rows = _parse_webui_rows(WEBUI_TABLE_HTML, tam_index=0)
    assert len(rows) == 2
    assert rows[0]["caller_name"] == "Papa"
    assert rows[0]["audio_path"] == "/download.lua?path=/data/tam/rec/rec.0.001"
    assert rows[0]["is_new"] is True
    assert rows[1]["is_new"] is False
    assert rows[1]["audio_path"].endswith("rec.0.000")


def test_parse_webui_rows_handles_empty_table():
    html = '<table id="uiTamCalls"><tr><td colspan="6">keine Nachrichten</td></tr></table>'
    rows = _parse_webui_rows(html, tam_index=0)
    # Eine Zeile mit colspan/keine echten Daten — Heuristik liefert evtl. einen Eintrag
    # Wichtig: kein Crash, audio_path leer
    for r in rows:
        assert r["audio_path"] == ""


def test_parse_webui_rows_handles_missing_table():
    assert _parse_webui_rows("<html><body>nichts</body></html>", 0) == []
