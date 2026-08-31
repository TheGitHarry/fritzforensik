"""Sprachnachrichten gegen ihren Hash im Datensatz prüfen (#35).

Die WAV-Dateien unter ``tam_audio/`` bekommen bewusst **keine** Sidecar: Ihr
SHA256 steht im Datensatz der ``tam``-JSON, und die hat ihrerseits eine Sidecar.
Der Hash liegt damit eine Ebene höher als die Datei, die er schützt — wer die WAV
austauscht, müsste auch die JSON nachziehen und brächte deren Sidecar zu Fall.

Genau diese Kette blieb bis #35 unbenutzt: Die Chain-of-Custody-Tabelle entstand
allein aus den vorhandenen Sidecars, und was keine hat, war nicht etwa bemängelt,
sondern unsichtbar.
"""
from __future__ import annotations

import json
import shutil

from fritzformat import TOOL_NAME, build_envelope, dataset_filename, sha256_bytes, write_sidecar
from fritzreport.bundle import STATUS_MISSING, load_bundle

HOST = "https://fritz.box"
EXTRACTED = "2026-01-06T10:00:00Z"
WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + bytes(range(64))


def _bundle_mit_audio(synth_bundle, tmp_path, *, datei=WAV, hash_von=WAV, schreiben=True):
    """Kopie des synthetischen Bundles, um eine tam-Datenart samt WAV ergänzt.

    ``datei`` ist der Inhalt auf der Platte, ``hash_von`` der Inhalt, aus dem der
    Hash im Datensatz gebildet wird — so lässt sich beides gezielt entkoppeln.
    """
    d = tmp_path / "bundle"
    shutil.copytree(synth_bundle, d)
    if schreiben:
        (d / "tam_audio").mkdir()
        (d / "tam_audio" / "tam00_msg000.wav").write_bytes(datei)

    records = [{
        "tam_index": 0, "message_index": 0, "duration": "0:01", "is_new": True,
        "audio_file": "tam_audio/tam00_msg000.wav",
        "audio_sha256": sha256_bytes(hash_von),
        "audio_bytes": len(hash_von),
    }]
    p = d / dataset_filename(HOST, "20260106T100000Z", "tam")
    body = json.dumps(build_envelope(tool=TOOL_NAME, version="0.3.1", host=HOST,
                                     type_name="tam", records=records,
                                     extracted_at=EXTRACTED),
                      indent=2, ensure_ascii=False).encode("utf-8")
    p.write_bytes(body)
    write_sidecar(p, sha256_bytes(body))
    return d


def _audio_zeilen(b):
    return [e for e in b.coc if e.file.startswith("tam_audio/")]


def test_audio_steht_in_der_coc_mit_eigener_herkunft(synth_bundle, tmp_path):
    b = load_bundle(_bundle_mit_audio(synth_bundle, tmp_path))

    zeilen = _audio_zeilen(b)
    assert len(zeilen) == 1, f"Sprachnachricht fehlt in der CoC: {[e.file for e in b.coc]}"
    assert zeilen[0].status == "ok"
    assert zeilen[0].quelle == "datensatz", \
        "Herkunft der Erwartung muss von einer Sidecar unterscheidbar sein"
    assert zeilen[0].size == len(WAV)
    assert b.integrity_ok


def test_veraenderte_audiodatei_faellt_auf(synth_bundle, tmp_path):
    """Der Befund aus #35, am Korpus nachgestellt: ein gekipptes Byte blieb
    unbemerkt, während der Report alles als verifiziert meldete."""
    kaputt = bytearray(WAV)
    kaputt[20] ^= 0xFF
    b = load_bundle(_bundle_mit_audio(synth_bundle, tmp_path, datei=bytes(kaputt)))

    assert _audio_zeilen(b)[0].status == "mismatch"
    assert not b.integrity_ok


def test_fehlende_audiodatei_hat_einen_eigenen_status(synth_bundle, tmp_path):
    """Datensatz ohne Datei ist kein stiller Durchlauf — und auch kein
    MISMATCH: Es gibt nichts zu vergleichen, es fehlt schlicht etwas."""
    b = load_bundle(_bundle_mit_audio(synth_bundle, tmp_path, schreiben=False))

    assert _audio_zeilen(b)[0].status == STATUS_MISSING
    assert not b.integrity_ok


def test_pfad_aus_dem_bundle_heraus_wird_nicht_gelesen(synth_bundle, tmp_path):
    """``audio_file`` kommt aus einer Datei, die der Report nicht geschrieben hat.
    Ein Verweis nach außen darf nichts außerhalb des Bundles einlesen."""
    d = _bundle_mit_audio(synth_bundle, tmp_path)
    fremd = tmp_path / "fremd.wav"
    fremd.write_bytes(WAV)

    p = next(d.glob("*_tam.json"))
    daten = json.loads(p.read_text(encoding="utf-8"))
    daten["records"][0]["audio_file"] = "../fremd.wav"
    body = json.dumps(daten, indent=2, ensure_ascii=False).encode("utf-8")
    p.write_bytes(body)
    write_sidecar(p, sha256_bytes(body))

    b = load_bundle(d)
    zeile = [e for e in b.coc if "fremd" in e.file]
    assert zeile and zeile[0].status == STATUS_MISSING, \
        "Pfad außerhalb des Bundles muss als fehlend gelten, nicht als geprüft"
    assert not b.integrity_ok


def test_datensatz_ohne_audio_erzeugt_keine_zeile(synth_bundle, tmp_path):
    """Eine Nachricht, deren Audio der Abzug nicht holen konnte (``audio_error``),
    hat keinen Hash — dafür gibt es nichts zu prüfen."""
    d = _bundle_mit_audio(synth_bundle, tmp_path)
    p = next(d.glob("*_tam.json"))
    daten = json.loads(p.read_text(encoding="utf-8"))
    daten["records"][0] = {"tam_index": 0, "message_index": 0, "audio_error": "HTTP 500"}
    body = json.dumps(daten, indent=2, ensure_ascii=False).encode("utf-8")
    p.write_bytes(body)
    write_sidecar(p, sha256_bytes(body))

    b = load_bundle(d)
    assert not _audio_zeilen(b)
    assert b.integrity_ok


def test_report_weist_die_herkunft_in_der_zeile_aus(synth_bundle, tmp_path, monkeypatch):
    """Im gerenderten Report muss **in der Zeile selbst** ablesbar sein, dass die
    Erwartung für die Sprachnachricht nicht aus einer Sidecar stammt — das Wort
    irgendwo auf der Seite genügt nicht."""
    from fritzreport.cli import main

    d = _bundle_mit_audio(synth_bundle, tmp_path)
    out = tmp_path / "report.html"
    monkeypatch.setattr("sys.argv", [
        "fritzreport", str(d), "-o", str(out),
        "--case-id", "C-1", "--item-id", "A-1", "--sb", "Test", "--date", "2026-01-01",
    ])
    assert main() == 0
    html = out.read_text(encoding="utf-8")

    zeilen = [z for z in html.split("<tr>") if "tam_audio/tam00_msg000.wav" in z]
    assert len(zeilen) == 1, "Sprachnachricht steht nicht (oder mehrfach) in der Tabelle"
    assert "Datensatz (tam)" in zeilen[0]
    assert "✔ verifiziert" in zeilen[0]

    # Gegenprobe: eine gewöhnliche Bundle-Datei bleibt bei „Sidecar"
    json_zeilen = [z for z in html.split("<tr>") if "_hosts.json<" in z]
    assert json_zeilen and "Sidecar" in json_zeilen[0]
