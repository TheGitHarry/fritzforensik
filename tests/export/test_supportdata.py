"""Offline-Tests für den Supportdaten-Extractor, insbesondere den
Probe-First-Ablauf der erweiterten Supportdaten (mit/ohne Tastendruck)."""
from __future__ import annotations

from unittest.mock import MagicMock

from fritzexport.extractors import supportdata as sd


def _client(content: bytes = b"##### TITLE Datum Sat Aug  8 00:01:38 CEST 2026\n") -> MagicMock:
    client = MagicMock()
    client.base_url = "https://192.168.2.1"
    client.sid = "abc"
    client.session.post.return_value.content = content
    client.session.post.return_value.status_code = 200
    return client


def _uhr_marker(caplog) -> list[str]:
    """Nur die Uhrzeit-Markerzeilen, in Reihenfolge — ohne Log-Kopf."""
    return [r.getMessage() for r in caplog.records
            if r.getMessage().startswith(("UHRZEIT ANFRAGE", "UHRZEIT ANTWORT"))]


def test_enhanced_ohne_tastendruck(monkeypatch):
    """Box mit deaktivierter erweiterter Sicherheit: Direktversuch liefert
    Daten, es wird nicht auf einen Tastendruck gewartet."""
    calls = []
    monkeypatch.setattr(sd, "_fetch_one", lambda c, f, s: calls.append(f) or b"DATA")

    def fail_wait(_timeout):
        raise AssertionError("Es darf nicht auf Bestätigung gewartet werden.")

    monkeypatch.setattr(sd, "_wait_for_enter", fail_wait)

    assert sd._fetch_enhanced(_client()) == b"DATA"
    assert calls == ["SupportDataEnhanced"]


def test_enhanced_mit_tastendruck(monkeypatch):
    """Box verlangt Bestätigung: erster Abruf None → nach bestätigtem
    Tastendruck zweiter Abruf mit Daten."""
    responses = iter([None, b"DATA"])
    monkeypatch.setattr(sd, "_fetch_one", lambda c, f, s: next(responses))
    monkeypatch.setattr(sd, "_wait_for_enter", lambda _timeout: True)

    assert sd._fetch_enhanced(_client()) == b"DATA"


def test_enhanced_timeout(monkeypatch):
    """Box verlangt Bestätigung, aber Timeout → None, kein zweiter Abruf."""
    responses = iter([None])
    monkeypatch.setattr(sd, "_fetch_one", lambda c, f, s: next(responses))
    monkeypatch.setattr(sd, "_wait_for_enter", lambda _timeout: False)

    assert sd._fetch_enhanced(_client()) is None


def test_extract_ohne_tastendruck_liefert_alle_drei(monkeypatch, tmp_path):
    """Vollständiger Extract-Lauf: alle drei Varianten liefern Daten,
    kein interaktives Warten."""
    monkeypatch.setattr(sd, "_fetch_one", lambda c, f, s: b"RAW-" + f.encode())
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


# ─────────────────────────── Uhrzeit-Klammern ────────────────────────────────

def test_fetch_one_klammert_den_abruf(caplog) -> None:
    """Anfrage vor dem Abruf, Antwort danach — mit der Kurzform der Variante.
    Der Report bildet aus dieser Klammer den Versatz der Box-Uhr."""
    caplog.set_level("INFO", logger="fritzexport.extractors.supportdata")
    sd._fetch_one(_client(), "SupportData", "standard")

    marker = _uhr_marker(caplog)
    assert len(marker) == 2
    assert marker[0].startswith("UHRZEIT ANFRAGE supportdata:standard ")
    assert marker[1].startswith("UHRZEIT ANTWORT supportdata:standard ")


def test_anfrage_steht_vor_dem_request(monkeypatch) -> None:
    """Die Anfrage-Marke muss **vor** dem HTTP-Aufruf fallen und die Antwort-Marke
    danach — sonst klammerte die Messung den Abruf nicht ein.

    Marker und POST laufen deshalb in **eine** Liste, nicht in zwei getrennte
    Kanäle: Nur so wird ihre Reihenfolge zueinander tatsächlich geprüft.
    """
    ablauf: list[str] = []
    monkeypatch.setattr(sd.log, "info", lambda msg, *a: ablauf.append(msg.split()[1]))
    client = _client()

    def post(*_a, **_kw):
        ablauf.append("POST")
        antwort = MagicMock()
        antwort.content = b"DATA"
        return antwort

    client.session.post = post
    sd._fetch_one(client, "SupportData", "standard")

    assert ablauf == ["ANFRAGE", "POST", "ANTWORT"]


def test_enhanced_schreibt_zwei_anfragen(caplog, monkeypatch) -> None:
    """Der Tastendruck-Pfad ruft zweimal ab. Beide Paare stehen im Log; der
    Report nimmt das letzte, weil nur dessen Antwort abgelegt wurde."""
    caplog.set_level("INFO", logger="fritzexport.extractors.supportdata")
    antworten = iter([b"", b"DATA"])   # 1. HTML-Ersatz → None, 2. echte Daten
    client = _client()

    def post(*_a, **_kw):
        antwort = MagicMock()
        antwort.content = next(antworten)
        return antwort

    client.session.post = post
    monkeypatch.setattr(sd, "_wait_for_enter", lambda _timeout: True)

    assert sd._fetch_enhanced(client) == b"DATA"

    marker = _uhr_marker(caplog)
    anfragen = [m for m in marker if m.startswith("UHRZEIT ANFRAGE")]
    assert len(anfragen) == 2, "beide Abrufversuche müssen datiert sein"
    assert all("supportdata:enhanced" in m for m in anfragen)
