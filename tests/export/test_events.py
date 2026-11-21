"""Offline-Tests für den Ereignislog-Extractor (data.lua page=log)."""
from __future__ import annotations

from unittest.mock import MagicMock

from fritzexport.extractors import events as events_mod


def _client(antworten: dict[str, object]) -> MagicMock:
    """``antworten`` ordnet filter-Werten das JSON zu; Exception-Instanzen werden geworfen."""
    client = MagicMock()

    def post(path, data):
        wert = antworten.get(data["filter"], {"data": {"log": []}})
        resp = MagicMock()
        if isinstance(wert, Exception):
            resp.json.side_effect = wert
        else:
            resp.json.return_value = wert
        return resp

    client.post.side_effect = post
    return client


ZEILE = ["01.01.26", "10:00:00", "Anmeldung an der Benutzeroberfläche", "1234", "sys"]


def test_listenzeile_wird_auf_felder_abgebildet():
    records = events_mod.extract(_client({"0": {"data": {"log": [ZEILE]}}}))
    assert len(records) == 1
    rec = records[0]
    assert rec["date"] == "01.01.26"
    assert rec["time"] == "10:00:00"
    assert rec["message"] == "Anmeldung an der Benutzeroberfläche"
    assert rec["id"] == "1234"
    assert rec["category"] == "sys"
    assert rec["raw"] == ZEILE
    assert rec["found_in_filters"] == ["all"]


def test_kurze_listenzeile_wird_mit_leeren_feldern_aufgefuellt():
    records = events_mod.extract(_client({"0": {"data": {"log": [["01.01.26", "10:00:00"]]}}}))
    assert records[0]["message"] == ""
    assert records[0]["id"] == ""
    assert records[0]["category"] == ""


def test_dictzeile_mit_beiden_feldnamen():
    """Firmware-Stände nennen die Felder msg/group oder message/category."""
    log = [
        {"date": "01.01.26", "time": "10:00:00", "msg": "A", "id": "1", "group": "net"},
        {"date": "01.01.26", "time": "10:00:01", "message": "B", "category": "fon"},
    ]
    records = events_mod.extract(_client({"0": {"data": {"log": log}}}))
    assert [(r["message"], r["category"]) for r in records] == [("A", "net"), ("B", "fon")]
    assert records[1]["id"] == ""


def test_zeilen_anderer_form_werden_uebergangen():
    log = ["kein Eintrag", 42, None, ZEILE]
    records = events_mod.extract(_client({"0": {"data": {"log": log}}}))
    assert len(records) == 1


def test_mehrfach_gefundenes_ereignis_einmal_mit_allen_filtern():
    """Gleiches Datum, Uhrzeit und Text gelten als dasselbe Ereignis."""
    antwort = {"data": {"log": [ZEILE]}}
    records = events_mod.extract(_client({"0": antwort, "sys": antwort}))
    assert len(records) == 1
    assert records[0]["found_in_filters"] == ["all", "sys"]


def test_schluessel_ist_datum_zeit_text_nicht_kategorie():
    """Liefert ein Kategorie-Filter dasselbe Ereignis mit anderer ID oder Kategorie,
    bleibt es ein Datensatz; Felder und Rohzeile stammen aus dem ersten Fund."""
    anders = ["01.01.26", "10:00:00", "Anmeldung an der Benutzeroberfläche", "9999", "net"]
    records = events_mod.extract(_client({
        "0": {"data": {"log": [ZEILE]}},
        "net": {"data": {"log": [anders]}},
    }))
    assert len(records) == 1
    assert records[0]["found_in_filters"] == ["all", "net"]
    assert records[0]["category"] == "sys"
    assert records[0]["raw"] == ZEILE


def test_ereignis_nur_in_kategorie_wird_aufgenommen():
    """Manche Firmware liefert Einträge nur im Kategorie-Filter, nicht in "all"."""
    nur_wlan = ["01.01.26", "11:00:00", "WLAN-Gerät angemeldet", "", "wlan"]
    records = events_mod.extract(_client({
        "0": {"data": {"log": [ZEILE]}},
        "wlan": {"data": {"log": [nur_wlan]}},
    }))
    assert len(records) == 2
    assert records[1]["found_in_filters"] == ["wlan"]


def test_fehlschlag_eines_filters_bricht_die_anderen_nicht_ab():
    records = events_mod.extract(_client({
        "0": ValueError("kein JSON"),
        "net": {"data": {"log": [ZEILE]}},
    }))
    assert len(records) == 1
    assert records[0]["found_in_filters"] == ["net"]


def test_antwort_ohne_daten_leer():
    assert events_mod.extract(_client({"0": {}, "sys": {"data": None}})) == []


def test_alle_filter_werden_abgefragt():
    client = _client({})
    events_mod.extract(client)
    gefragt = [c.kwargs["data"]["filter"] for c in client.post.call_args_list]
    assert gefragt == list(events_mod._FILTERS.values())
