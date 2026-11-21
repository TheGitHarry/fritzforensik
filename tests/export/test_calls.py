"""Offline-Tests für den Anruflisten-Extractor (CSV aus foncalls_list.lua)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests

from fritzexport.extractors import calls as calls_mod


def _client(text: str) -> MagicMock:
    client = MagicMock()
    client.get.return_value = MagicMock(text=text)
    return client


CSV_DE = (
    "sep=;\n"
    "Typ;Datum;Name;Rufnummer;Nebenstelle;Eigene Rufnummer;Dauer\n"
    "1;01.01.26 10:00; Erika Mustermann ;0301234567;FON 1;Festnetz;0:05\n"
    "3;02.01.26 11:30;;0309876543;;Festnetz;0:00\n"
)


def test_csv_kopfzeile_davor_wird_uebersprungen():
    """Die Box stellt dem CSV eine sep=-Zeile voran; gelesen wird ab der Spaltenzeile."""
    records = calls_mod.extract(_client(CSV_DE))
    assert len(records) == 2
    assert records[0]["Typ"] == "1"
    assert records[0]["Rufnummer"] == "0301234567"


def test_werte_werden_getrimmt_und_leere_bleiben_leer():
    records = calls_mod.extract(_client(CSV_DE))
    assert records[0]["Name"] == "Erika Mustermann"
    assert records[1]["Name"] == ""
    assert records[1]["Nebenstelle"] == ""


def test_englische_spaltenzeile_wird_erkannt():
    text = "Type;Date;Name;Number\n2;03.01.26 09:00;Max Mustermann;0301111111\n"
    records = calls_mod.extract(_client(text))
    assert records == [{"Type": "2", "Date": "03.01.26 09:00",
                        "Name": "Max Mustermann", "Number": "0301111111"}]


def test_ohne_spaltenzeile_leer():
    """Eine Login-Seite oder Fehlermeldung statt CSV liefert keine Phantomzeilen."""
    assert calls_mod.extract(_client("<html>Anmeldung</html>\n")) == []


def test_nur_spaltenzeile_leer():
    assert calls_mod.extract(_client("Typ;Datum;Name\n")) == []


def test_fragt_csv_an():
    client = _client(CSV_DE)
    calls_mod.extract(client)
    client.get.assert_called_once_with(calls_mod.CALLS_PATH, params={"csv": ""})


def test_http_fehler_wird_weitergereicht():
    """Kein stilles []: cli.py soll den Fehlschlag sehen und protokollieren."""
    client = _client("")
    client.get.return_value.raise_for_status.side_effect = requests.HTTPError("403")
    with pytest.raises(requests.HTTPError):
        calls_mod.extract(client)
