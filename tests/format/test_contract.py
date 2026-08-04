"""Der Formatvertrag zwischen fritzexport (schreibt) und fritzreport (liest).

Genau diese Prüfungen fehlten, solange die beiden Werkzeuge in getrennten Repos
lagen: die Datenart-Listen und das Bundle-Layout waren auf beiden Seiten von
Hand gepflegt, eine Abweichung wäre erst im Feld aufgefallen.
"""
from __future__ import annotations

import json

from fritzformat import (
    CASE_FILENAME,
    MARKER_BEGIN,
    MARKER_END,
    begin_line,
    JSON_TYPES,
    SUPPORT_VARIANTS,
    TOOL_NAME,
    build_case,
    compact_from_iso,
    dataset_filename,
    end_line,
    parse_span,
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


# ───────────────────────── Sicherungszeitraum im Log ─────────────────────────

def test_parse_span_liest_beide_marker() -> None:
    text = (f"2026-07-13 11:34:58,004 INFO {MARKER_BEGIN} 2026-07-13T09:34:58Z\n"
            "2026-07-13 11:34:58,120 INFO Starte Extractor: calls\n"
            f"2026-07-13 11:41:25,880 INFO {MARKER_END} 2026-07-13T09:41:25Z\n")
    assert parse_span(text) == ("2026-07-13T09:34:58Z", "2026-07-13T09:41:25Z")


def test_parse_span_ohne_marker_ist_leer() -> None:
    """Altbestand: Logs von vor der Einführung dürfen nicht zu Fehlern führen."""
    assert parse_span("2026-07-13 11:34:58 INFO Starte Extractor: calls\n") == ("", "")
    assert parse_span("") == ("", "")


def test_parse_span_nur_beginn_bei_abbruch() -> None:
    """Abgebrochener Lauf: Beginn steht, Ende fehlt — der Report muss das zeigen
    können, statt einen erfundenen Endzeitpunkt anzugeben."""
    von, bis = parse_span(f"INFO {MARKER_BEGIN} 2026-07-13T09:34:58Z\nINFO Abbruch\n")
    assert von == "2026-07-13T09:34:58Z"
    assert bis == ""


def test_parse_span_mehrere_laeufe_umspannen_alles() -> None:
    """Mehrere Läufe in einem Log → erster Beginn, letztes Ende."""
    text = (f"{MARKER_BEGIN} 2026-07-13T09:00:00Z\n{MARKER_END} 2026-07-13T09:10:00Z\n"
            f"{MARKER_BEGIN} 2026-07-13T10:00:00Z\n{MARKER_END} 2026-07-13T10:30:00Z\n")
    assert parse_span(text) == ("2026-07-13T09:00:00Z", "2026-07-13T10:30:00Z")


def test_marker_rundlauf_export_zu_report(tmp_path) -> None:
    """Was fritzexport ins Log schreibt, liest fritzreport unverändert zurück."""
    log = tmp_path / "fritzexport_20260713T093458Z.log"
    log.write_text(
        f"2026-07-13 11:34:58,004 INFO {begin_line('2026-07-13T09:34:58Z')}\n"
        f"2026-07-13 11:41:25,880 INFO {end_line('2026-07-13T09:41:25Z')}\n",
        encoding="utf-8")

    output.write(tmp_path, "https://fritz.box", "hosts", [{"a": 1}])
    b = load_bundle(tmp_path)

    assert b.secured_source == "log"
    assert b.secured_from == "2026-07-13T09:34:58Z"
    assert b.secured_to == "2026-07-13T09:41:25Z"


def test_zeitraum_ohne_log_wird_gerechnet(tmp_path) -> None:
    """Ohne Marker: Minimum und Maximum über die extracted_at der Datensätze."""
    import json

    for type_name, stamp in (("hosts", "2026-07-13T09:35:00Z"),
                             ("calls", "2026-07-13T09:41:22Z"),
                             ("wifi", "2026-07-13T09:37:10Z")):
        p = output.write(tmp_path, "https://fritz.box", type_name, [{"a": 1}])
        d = json.loads(p.read_text(encoding="utf-8"))
        d["extracted_at"] = stamp
        body = json.dumps(d, indent=2, ensure_ascii=False).encode("utf-8")
        p.write_bytes(body)
        write_sidecar(p, sha256_bytes(body))

    b = load_bundle(tmp_path)
    assert b.secured_source == "berechnet"
    assert b.secured_from == "2026-07-13T09:35:00Z"
    assert b.secured_to == "2026-07-13T09:41:22Z"
