"""Zeit-Hilfsfunktionen des Reports: Unlesbares ergibt leer, kein Absturz.

Die except-Klauseln dort fangen gezielt die Ausnahmen, die Standardbibliothek und
Eingabe erzeugen können, statt pauschal ``Exception``. Diese Tests halten fest,
dass dabei keine nötige Ausnahme fehlt.
"""
from __future__ import annotations

import pytest

from fritzreport.bundle import SupportFile
from fritzreport.model import _iso_from_epoch, _parse_dt, _parse_dt_short
from fritzreport.supportdata import _parse_uptime


def test_epoch_gueltig():
    assert _iso_from_epoch(1700000000) == "2023-11-14T22:13:20+00:00"
    assert _iso_from_epoch("1700000000") == "2023-11-14T22:13:20+00:00"


@pytest.mark.parametrize("wert", [
    None, 0, "",                 # leer
    "kaputt",                    # ValueError
    [1],                         # TypeError
    10**20, -10**20,             # OverflowError
    253402300800,                # ValueError: Jahr außerhalb des Bereichs
])
def test_epoch_unlesbar_ergibt_leer(wert):
    assert _iso_from_epoch(wert) == ""


def test_datum_zeit_gueltig():
    assert _parse_dt("01.01.26", "10:00:00").isoformat() == "2026-01-01T10:00:00+00:00"
    assert _parse_dt_short("01.01.26 10:00").isoformat() == "2026-01-01T10:00:00+00:00"


@pytest.mark.parametrize("datum,zeit", [
    ("kaputt", "10:00:00"),
    ("31.02.26", "10:00:00"),    # gibt es nicht
    ("01.01.26", ""),
    (None, None),                # wird per f-String zu "None None" → ValueError
])
def test_datum_zeit_unlesbar_ergibt_none(datum, zeit):
    assert _parse_dt(datum, zeit) is None


@pytest.mark.parametrize("wert", ["kaputt", "31.02.26 10:00", "", None, 5])
def test_kurzes_datum_unlesbar_ergibt_none(wert):
    assert _parse_dt_short(wert) is None


def _uptime(extracted_at):
    sf = SupportFile(variant="standard", path=None, name="supportdata_standard.txt",
                     text="uptime: 11:41:13 up 85 days, 14:24,  load average: 0.1\n")
    return _parse_uptime(sf, extracted_at)


@pytest.mark.parametrize("extracted_at", [
    "kaputt",                    # ValueError
    None,                        # AttributeError: null im Datensatzkopf
    "0001-01-02T00:00:00Z",      # OverflowError: Start läge vor dem Jahr 1
])
def test_boot_datum_bei_unlesbarem_abzugszeitpunkt_leer(extracted_at):
    """Die Laufzeit wird trotzdem wiedergegeben, nur das Boot-Datum bleibt leer."""
    up = _uptime(extracted_at)
    assert up["uptime_text"] == "85 days, 14:24"
    assert up["boot_derived"] == ""
