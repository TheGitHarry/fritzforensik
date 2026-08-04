"""Der Formatvertrag zwischen fritzexport (schreibt) und fritzreport (liest).

Genau diese Prüfungen fehlten, solange die beiden Werkzeuge in getrennten Repos
lagen: die Datenart-Listen und das Bundle-Layout waren auf beiden Seiten von
Hand gepflegt, eine Abweichung wäre erst im Feld aufgefallen.
"""
from __future__ import annotations

import json

from fritzformat import (
    CASE_FILENAME,
    JSON_TYPES,
    SUPPORT_VARIANTS,
    TOOL_NAME,
    build_case,
    compact_from_iso,
    dataset_filename,
    read_case,
    run_slug,
    read_envelope_meta,
    sha256_bytes,
    support_filename,
    verify,
    write_case,
    write_sidecar,
)
from fritzexport import output
from fritzexport.extractors import EXTRACTORS
from fritzexport.extractors.supportdata import _VARIANTS
from fritzreport.bundle import load_bundle
from fritzreport.cli import is_bundle


# ─────────────────────── Listen auf beiden Seiten identisch ──────────────────

def test_extractor_registry_deckt_sich_mit_den_datenarten() -> None:
    """Jeder Extractor erzeugt genau eine Datenart, die der Report auch sucht."""
    assert set(EXTRACTORS) == set(JSON_TYPES), (
        "Extractor-Registry und fritzformat.JSON_TYPES sind auseinandergelaufen: "
        f"nur im Export {set(EXTRACTORS) - set(JSON_TYPES)}, "
        f"nur im Format {set(JSON_TYPES) - set(EXTRACTORS)}"
    )


def test_supportdaten_varianten_decken_sich() -> None:
    kurznamen = {short for _feld, short in _VARIANTS}
    assert kurznamen == set(SUPPORT_VARIANTS)


# ──────────────────────────── Schreiben → Lesen ──────────────────────────────

def test_bundle_rundlauf(tmp_path) -> None:
    """Was fritzexport schreibt, muss fritzreport vollständig zurücklesen."""
    host = "https://192.168.178.1"
    ts = "20260724T101530Z"
    for type_name in JSON_TYPES:
        output.write(tmp_path, host, type_name, [{"probe": type_name}], timestamp=ts)

    # Roh-Supportdatei wie der supportdata-Extractor sie ablegt
    raw = tmp_path / support_filename("standard", ts)
    body = b"##### TITLE Version 8.20\n"
    raw.write_bytes(body)
    write_sidecar(raw, sha256_bytes(body))

    assert is_bundle(tmp_path), "geschriebenes Bundle wird nicht als solches erkannt"

    b = load_bundle(tmp_path)
    for type_name in JSON_TYPES:
        ds = b.ds(type_name)
        assert ds.present, f"Datenart '{type_name}' nicht wiedergefunden"
        assert ds.status == "ok", f"Integritätsprüfung für '{type_name}': {ds.status}"
        assert ds.records == [{"probe": type_name}]
    assert b.support["standard"].present
    assert b.integrity_ok
    assert b.meta["tool"] == TOOL_NAME


def test_dateiname_und_huelle_passen_zusammen(tmp_path) -> None:
    path = output.write(tmp_path, "https://fritz.box", "hosts", [], timestamp="20260724T101530Z")
    assert path.name == dataset_filename("https://fritz.box", "20260724T101530Z", "hosts")
    meta = read_envelope_meta(json.loads(path.read_text(encoding="utf-8")))
    assert meta["tool"] == TOOL_NAME
    assert meta["host"] == "https://fritz.box"


def test_sidecar_ueberlebt_umbenennung(tmp_path) -> None:
    """Verifiziert wird der Digest, nicht der Dateiname — ein umbenanntes
    Bundle bleibt prüfbar (genutzt beim Aufbau des Golden-Korpus)."""
    path = output.write(tmp_path, "https://fritz.box", "hosts", [{"a": 1}])
    sidecar = path.with_suffix(path.suffix + ".sha256")
    neu = path.with_name("umbenannt_hosts.json")
    path.rename(neu)
    sidecar.rename(neu.with_suffix(neu.suffix + ".sha256"))
    status, _digest = verify(neu)
    assert status == "ok"


def test_mismatch_wird_erkannt(tmp_path) -> None:
    """Gegenprobe zur Integritätsprüfung — sie darf nicht blind 'ok' sagen."""
    path = output.write(tmp_path, "https://fritz.box", "hosts", [{"a": 1}])
    path.write_bytes(path.read_bytes() + b" ")
    status, _digest = verify(path)
    assert status == "mismatch"


# ───────────────────────── Fallkopf (case.json) ──────────────────────────────

def test_fallkopf_rundlauf(tmp_path) -> None:
    """Was fritzexport schreibt, liest fritzreport unverändert zurück."""
    geschrieben = build_case(case_id="C-2026-0815", item_id="A-01",
                             sb="Killefiz", date="2026-08-04",
                             written_at="2026-08-04T12:00:00Z")
    write_case(tmp_path, geschrieben)

    gelesen = read_case(tmp_path)
    assert gelesen == {"case_id": "C-2026-0815", "item_id": "A-01",
                       "sb": "Killefiz", "date": "2026-08-04"}


def test_fallkopf_fehlt_ist_kein_fehler(tmp_path) -> None:
    """Ein Bundle ohne Fallkopf ist gültig — der Report darf nicht scheitern."""
    assert read_case(tmp_path) == {}


def test_fallkopf_kaputt_wird_ignoriert(tmp_path) -> None:
    """Beschädigte case.json blockiert den Report nicht (sie ist Bequemlichkeit,
    keine Voraussetzung) — Gegenprobe zum Rundlauf oben."""
    (tmp_path / CASE_FILENAME).write_text("{kein json", encoding="utf-8")
    assert read_case(tmp_path) == {}

    (tmp_path / CASE_FILENAME).write_text('["liste statt objekt"]', encoding="utf-8")
    assert read_case(tmp_path) == {}


def test_fallkopf_traegt_keine_sidecar(tmp_path) -> None:
    """Bewusst ohne Sidecar: eine Bearbeiterangabe ist kein Beweismittel aus der
    Box und muss korrigierbar bleiben, ohne die Bundle-Integrität zu verletzen."""
    write_case(tmp_path, build_case(case_id="C-1"))
    assert not (tmp_path / f"{CASE_FILENAME}.sha256").exists()


# ───────────────────────── Gemeinsamer Namensstamm ───────────────────────────

def test_run_slug_verbindet_abzug_und_report() -> None:
    """Beide Werkzeuge bilden denselben Stamm — sonst finden sie nicht zusammen."""
    stamm = run_slug("C-2026-0815", "A-01", "20260804T184059Z")
    assert stamm == "C-2026-0815_A-01_20260804T184059Z"


def test_run_slug_ohne_fallkopf_faellt_zurueck() -> None:
    """Ohne Case/Item bleibt der Zeitstempelname — ein Abzug ohne Fallkopf ist
    der Normalfall im Feld, kein Fehler."""
    assert run_slug("", "", "20260804T184059Z") == "export_20260804T184059Z"
    assert run_slug("", "", "").startswith("export")


def test_run_slug_laesst_leere_teile_weg() -> None:
    assert run_slug("C-1", "", "20260804T184059Z") == "C-1_20260804T184059Z"
    assert run_slug("", "A-01", "20260804T184059Z") == "A-01_20260804T184059Z"


def test_run_slug_entschaerft_sonderzeichen() -> None:
    """Case-IDs aus der Praxis enthalten Schrägstriche und Leerzeichen — die
    dürfen nicht im Dateinamen landen."""
    stamm = run_slug("ST/0815-26", "Asservat 1", "20260804T184059Z")
    assert "/" not in stamm and " " not in stamm
    assert stamm == "ST-0815-26_Asservat-1_20260804T184059Z"


def test_compact_from_iso() -> None:
    """Der Report kennt den Abzugszeitpunkt nur als ISO-Wert, braucht ihn für den
    Dateinamen aber kompakt — sonst weicht sein Stamm vom Verzeichnis ab."""
    assert compact_from_iso("2026-08-04T18:40:59Z") == "20260804T184059Z"
    assert compact_from_iso("") == ""
    assert compact_from_iso("kein zeitstempel") == ""


def test_stamm_von_abzug_und_report_ist_identisch() -> None:
    """Der eigentliche Vertrag: Verzeichnisname und Reportname teilen den Stamm."""
    case = {"case_id": "C-2026-0815", "item_id": "A-01"}
    verzeichnis = run_slug(case["case_id"], case["item_id"], "20260804T184059Z")
    # der Report geht vom ISO-Wert der Hülle aus
    report = run_slug(case["case_id"], case["item_id"],
                      compact_from_iso("2026-08-04T18:40:59Z"))
    assert verzeichnis == report
