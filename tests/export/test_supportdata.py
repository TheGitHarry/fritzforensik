"""Offline-Tests für den Supportdaten-Extractor, insbesondere den
Probe-First-Ablauf der erweiterten Supportdaten (mit/ohne Tastendruck)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from fritzexport.extractors import supportdata as sd
from fritzformat import parse_uhr_spans


def _client(content: bytes = b"##### TITLE Datum Sat Aug  8 00:01:38 CEST 2026\n") -> MagicMock:
    client = MagicMock()
    client.base_url = "https://192.168.2.1"
    client.sid = "abc"
    client.session.post.return_value.content = content
    client.session.post.return_value.status_code = 200
    return client


#: Dateinamen-Stempel, den `_fetch_one` neben den Rohdaten zurückgibt.
TS = "20260722T141807Z"


def _uhr_marker(caplog) -> list[str]:
    """Nur die Uhrzeit-Markerzeilen, in Reihenfolge — ohne Log-Kopf."""
    return [r.getMessage() for r in caplog.records
            if r.getMessage().startswith(("UHRZEIT ANFRAGE", "UHRZEIT ANTWORT"))]


def test_enhanced_ohne_tastendruck(monkeypatch):
    """Box mit deaktivierter erweiterter Sicherheit: Direktversuch liefert
    Daten, es wird nicht auf einen Tastendruck gewartet."""
    calls = []
    monkeypatch.setattr(sd, "_fetch_one",
                        lambda c, f, s: calls.append(f) or (b"DATA", TS))

    def fail_wait(_timeout):
        raise AssertionError("Es darf nicht auf Bestätigung gewartet werden.")

    monkeypatch.setattr(sd, "_wait_for_enter", fail_wait)

    assert sd._fetch_enhanced(_client()) == (b"DATA", TS)
    assert calls == ["SupportDataEnhanced"]


def test_enhanced_mit_tastendruck(monkeypatch):
    """Box verlangt Bestätigung: erster Abruf None → nach bestätigtem
    Tastendruck zweiter Abruf mit Daten."""
    responses = iter([None, (b"DATA", TS)])
    monkeypatch.setattr(sd, "_fetch_one", lambda c, f, s: next(responses))
    monkeypatch.setattr(sd, "_wait_for_enter", lambda _timeout: True)

    assert sd._fetch_enhanced(_client()) == (b"DATA", TS)


def test_enhanced_timeout(monkeypatch):
    """Box verlangt Bestätigung, aber Timeout → None, kein zweiter Abruf."""
    responses = iter([None])
    monkeypatch.setattr(sd, "_fetch_one", lambda c, f, s: next(responses))
    monkeypatch.setattr(sd, "_wait_for_enter", lambda _timeout: False)

    assert sd._fetch_enhanced(_client()) is None


def test_extract_ohne_tastendruck_liefert_alle_drei(monkeypatch, tmp_path):
    """Vollständiger Extract-Lauf: alle drei Varianten liefern Daten,
    kein interaktives Warten."""
    monkeypatch.setattr(sd, "_fetch_one",
                        lambda c, f, s: (b"RAW-" + f.encode(), TS))
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


# ──────────────────────── Datierung der Rohdateien ───────────────────────────

def test_jede_variante_traegt_ihren_eigenen_zeitstempel(monkeypatch, tmp_path) -> None:
    """Der Zeitstempel im Dateinamen ist die einzige Zeitangabe, die eine Roh-
    Supportdatei von sich aus trägt — die Hülle mit ``extracted_at`` gibt es nur für
    die JSON-Datenarten. Ein gemeinsamer Stempel für alle drei Varianten datierte
    zwei von drei Dateien auf den Request der ersten.
    """
    zeiten = iter([
        "2026-07-22T14:18:07.000Z", "2026-07-22T14:18:52.000Z",   # standard
        "2026-07-22T14:19:00.000Z", "2026-07-22T14:19:30.000Z",   # mesh
        "2026-07-22T14:23:12.000Z", "2026-07-22T14:23:41.000Z",   # enhanced
    ])
    monkeypatch.setattr(sd, "uhr_jetzt_iso", lambda: next(zeiten))

    records, _ = sd.extract(_client(b"DATA"), output_dir=tmp_path)

    assert [r["filename"] for r in records] == [
        "supportdata_standard_20260722T141807Z.txt",
        "supportdata_mesh_20260722T141900Z.txt",
        "supportdata_enhanced_20260722T142312Z.txt",
    ]
    for r in records:
        assert (tmp_path / r["filename"]).exists()


def test_enhanced_wird_auf_den_zweiten_abruf_datiert(monkeypatch) -> None:
    """Der Tastendruck-Pfad ruft zweimal ab; abgelegt wird die Datei des **zweiten**
    Abrufs. Der Dateiname muss ihn datieren, nicht den verworfenen Probeversuch —
    dazwischen liegt die Wartezeit auf den Knopf (7490 des Korpus: 595 s).

    Es ist derselbe Fehler wie beim ersten Marker-Paar in `parse_uhr_spans`: Wer den
    verworfenen Versuch datiert, klebt der abgelegten Datei eine fremde Zeit an.
    """
    zeiten = iter([
        "2026-07-22T14:18:07.000Z", "2026-07-22T14:18:08.000Z",   # Probe → HTML
        "2026-07-22T14:23:12.000Z", "2026-07-22T14:23:41.000Z",   # nach Tastendruck
    ])
    monkeypatch.setattr(sd, "uhr_jetzt_iso", lambda: next(zeiten))
    monkeypatch.setattr(sd, "_wait_for_enter", lambda _timeout: True)
    antworten = iter([b"", b"DATA"])
    client = _client()

    def post(*_a, **_kw):
        antwort = MagicMock()
        antwort.content = next(antworten)
        return antwort

    client.session.post = post

    assert sd._fetch_enhanced(client) == (b"DATA", "20260722T142312Z")


# ─────────────────────────── Uhrzeit-Klammern ────────────────────────────────

def test_fetch_one_datiert_das_paar_mit_quellenkennung(caplog) -> None:
    """Beide Marken tragen die Kurzform der Variante (`supportdata:standard`) — daran
    ordnet der Report Marker und Messung einander zu, ohne raten zu müssen.

    Bewusst **nicht** mehr: Dass die Marken den Abruf auch wirklich einklammern, prüft
    `test_anfrage_steht_vor_dem_request` (Marker und POST in *einer* Liste). Dieser
    Test hier sähe eine Anfrage-Marke, die hinter den POST rutscht, nicht — er sagte
    das früher trotzdem im Docstring zu.
    """
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


def test_fetch_one_datiert_auch_den_abgebrochenen_abruf(caplog) -> None:
    """Wirft der POST selbst (Timeout, Verbindungsabbruch), muss die Antwort-Marke
    trotzdem fallen — wie in `boxtime.py`.

    Sonst bliebe eine Anfrage ohne Partner im Log stehen. `cli.py` fängt die Ausnahme
    ab und schreibt das Bundle mit genau diesem Log; ein zweiter Abruf derselben
    Quelle (erweiterte Supportdaten nach Tastendruck) verklammerte sich dann mit der
    Marke des abgebrochenen Versuchs.
    """
    caplog.set_level("INFO", logger="fritzexport.extractors.supportdata")
    client = _client()
    client.session.post.side_effect = TimeoutError("read timeout")

    with pytest.raises(TimeoutError):
        sd._fetch_one(client, "SupportData", "standard")

    marker = _uhr_marker(caplog)
    assert marker[0].startswith("UHRZEIT ANFRAGE supportdata:standard ")
    assert len(marker) == 2, "Abbruch bleibt undatiert — Anfrage ohne Partner im Log"
    assert marker[1].startswith("UHRZEIT ANTWORT supportdata:standard ")


def test_enhanced_klammert_beide_versuche_getrennt(caplog, monkeypatch) -> None:
    """Der Tastendruck-Pfad ruft zweimal ab. Beide Versuche stehen als **eigenes,
    vollständiges Paar** im Log, und die Leseseite greift daraus das zweite — nur
    dessen Antwort wurde abgelegt.

    Geprüft wird das hier mit `parse_uhr_spans` selbst, über das tatsächlich
    geschriebene Log: Der Vorgänger dieses Tests zählte nur die ANFRAGE-Zeilen und
    behauptete die Auswertung bloß im Docstring.
    """
    caplog.set_level("INFO", logger="fritzexport.extractors.supportdata")
    antworten = iter([b"", b"DATA"])   # 1. HTML-Ersatz → None, 2. echte Daten
    client = _client()

    def post(*_a, **_kw):
        antwort = MagicMock()
        antwort.content = next(antworten)
        return antwort

    client.session.post = post
    monkeypatch.setattr(sd, "_wait_for_enter", lambda _timeout: True)

    inhalt, _ts = sd._fetch_enhanced(client)
    assert inhalt == b"DATA"

    marker = _uhr_marker(caplog)
    assert [m.split()[1] for m in marker] == ["ANFRAGE", "ANTWORT", "ANFRAGE", "ANTWORT"]
    assert all("supportdata:enhanced" in m for m in marker)

    zweites_paar = (marker[2].split()[-1], marker[3].split()[-1])
    assert parse_uhr_spans("\n".join(marker)) == {
        "supportdata:enhanced": zweites_paar}
