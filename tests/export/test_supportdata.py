"""Offline-Tests für den Supportdaten-Extractor, insbesondere den
Probe-First-Ablauf der erweiterten Supportdaten (mit/ohne Tastendruck)."""
from __future__ import annotations

from unittest.mock import MagicMock

from legacy_export.extractors import supportdata as sd


def _client() -> MagicMock:
    client = MagicMock()
    client.base_url = "https://192.168.2.1"
    client.sid = "abc"
    return client


def test_enhanced_ohne_tastendruck(monkeypatch):
    """Box mit deaktivierter erweiterter Sicherheit: Direktversuch liefert
    Daten, es wird nicht auf einen Tastendruck gewartet."""
    calls = []
    monkeypatch.setattr(sd, "_fetch_one", lambda c, f: calls.append(f) or b"DATA")

    def fail_wait(_timeout):
        raise AssertionError("Es darf nicht auf Bestätigung gewartet werden.")

    monkeypatch.setattr(sd, "_wait_for_enter", fail_wait)

    assert sd._fetch_enhanced(_client()) == b"DATA"
    assert calls == ["SupportDataEnhanced"]


def test_enhanced_mit_tastendruck(monkeypatch):
    """Box verlangt Bestätigung: erster Abruf None → nach bestätigtem
    Tastendruck zweiter Abruf mit Daten."""
    responses = iter([None, b"DATA"])
    monkeypatch.setattr(sd, "_fetch_one", lambda c, f: next(responses))
    monkeypatch.setattr(sd, "_wait_for_enter", lambda _timeout: True)

    assert sd._fetch_enhanced(_client()) == b"DATA"


def test_enhanced_timeout(monkeypatch):
    """Box verlangt Bestätigung, aber Timeout → None, kein zweiter Abruf."""
    responses = iter([None])
    monkeypatch.setattr(sd, "_fetch_one", lambda c, f: next(responses))
    monkeypatch.setattr(sd, "_wait_for_enter", lambda _timeout: False)

    assert sd._fetch_enhanced(_client()) is None


def test_extract_ohne_tastendruck_liefert_alle_drei(monkeypatch, tmp_path):
    """Vollständiger Extract-Lauf: alle drei Varianten liefern Daten,
    kein interaktives Warten."""
    monkeypatch.setattr(sd, "_fetch_one", lambda c, f: b"RAW-" + f.encode())
    monkeypatch.setattr(
        sd, "_wait_for_enter",
        lambda _t: (_ for _ in ()).throw(AssertionError("kein Warten erwartet")),
    )

    records, meta = sd.extract(_client(), output_dir=tmp_path)

    assert meta["supportdata_fetched"] == ["standard", "mesh", "enhanced"]
    assert meta["supportdata_missing"] == []
    assert {r["type"] for r in records} == {"standard", "mesh", "enhanced"}
    for r in records:
        assert (tmp_path / r["filename"]).exists()
        assert (tmp_path / f"{r['filename']}.sha256").exists()
