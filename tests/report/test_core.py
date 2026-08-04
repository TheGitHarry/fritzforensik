"""Kern-Invarianten: Bundle/Verifikation, Modell/Grade, Supportdaten, Herkunft, Render."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from fritzreport.bundle import load_bundle
from fritzreport.model import build_model
from fritzreport.render import build_html, build_timeline
from fritzreport.supportdata import analyze


# ───────────────────────── Bundle / Verifikation ─────────────────────────────

def test_bundle_loads_and_verifies(synth_bundle):
    b = load_bundle(synth_bundle)
    assert b.meta["tool"] == "fritzexport"
    assert b.ds("hosts").present
    assert all(e.status == "ok" for e in b.coc), "alle Sidecars müssen verifizieren"
    assert b.integrity_ok


def test_hash_mismatch_detected(synth_bundle):
    # eine JSON nachträglich verändern → Sidecar passt nicht mehr
    p = next(synth_bundle.glob("*_hosts.json"))
    p.write_text(p.read_text(encoding="utf-8") + "\n// tampered", encoding="utf-8")
    b = load_bundle(synth_bundle)
    statuses = {e.file: e.status for e in b.coc}
    assert statuses[p.name] == "mismatch"
    assert not b.integrity_ok


# ───────────────────────── Modell / 3-Grade-System ──────────────────────────

def test_grades_scheme(synth_bundle):
    m = build_model(load_bundle(synth_bundle))
    # kein D4 mehr irgendwo
    for coll in (m.hosts, m.mesh_nodes, m.wifi, m.calls, m.phonebook, m.events):
        for r in coll:
            assert "D4" not in r["grades"]
    # Anrufe/Telefonbuch: reine Rohdaten → kein Badge
    assert m.calls[0]["grades"] == []
    assert m.phonebook[0]["grades"] == []
    # Host mit IP+Interface → D1; ohne → kein Badge
    by_mac = {h["mac"]: h for h in m.hosts}
    assert by_mac["AA:BB:CC:DD:EE:01"]["grades"] == ["D1"]
    assert by_mac["AA:BB:CC:DD:EE:02"]["grades"] == []
    # Master-Mesh-Knoten (is_meshed + master) → D1+D2
    assert m.mesh_nodes[0]["grades"] == ["D1", "D2"]
    assert m.real_aps == ["fritzbox"]


# ───────────────────────── Supportdaten (beide Parser) ──────────────────────

def test_support_both_parsers_and_grades(synth_bundle):
    b = load_bundle(synth_bundle)
    m = build_model(b)
    res = analyze(b, m.real_aps, m.master.get("name", ""))
    proofs = res["proofs"]
    assert proofs, "es müssen Verbindungsnachweise entstehen"
    grade_sets = {tuple(p["grades"]) for p in proofs}
    assert ("D1", "D2") in grade_sets, "methode.md-Treffer fehlen"
    assert ("D1", "D3") in grade_sets, "802.11-Treffer fehlen"
    # Dedup: Schlüssel (iso, mac, event) eindeutig
    keys = [(p["iso"], p["mac"], p["event"]) for p in proofs]
    assert len(keys) == len(set(keys))
    # nach sortkey sortiert
    assert [p["sortkey"] for p in proofs] == sorted(p["sortkey"] for p in proofs)
    # Uptime abgeleitet: 2026-01-06 minus 5 Tage
    assert res["uptime"]["boot_derived"] == "2026-01-01"


def test_timestamps_second_precision(synth_bundle):
    b = load_bundle(synth_bundle)
    m = build_model(b)
    res = analyze(b, m.real_aps, m.master.get("name", ""))
    for p in res["proofs"]:
        # Anzeige ohne Millisekunden
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", p["display"]), p["display"]


# ───────────────────────── Herkunft zeichengenau ────────────────────────────

def test_provenance_exact(synth_bundle):
    b = load_bundle(synth_bundle)
    m = build_model(b)
    h = m.hosts[0]
    o = h["origin"]
    src = (synth_bundle / o["file"]).read_text(encoding="utf-8").split("\n")
    excerpt = "\n".join(src[o["line"] - 1:o["line_end"]])
    assert excerpt == o["text"], "JSON-Herkunft muss zeichengenau sein"

    res = analyze(b, m.real_aps, m.master.get("name", ""))
    p = next(pp for pp in res["proofs"] if "D3" in pp["grades"])
    sup = b.support["standard"]
    assert sup.lines[p["origin"]["line"] - 1] == p["origin"]["text"]


# ───────────────────────── Timeline / Render ────────────────────────────────

def test_timeline_merges_sources(synth_bundle):
    b = load_bundle(synth_bundle)
    m = build_model(b)
    res = analyze(b, m.real_aps, m.master.get("name", ""))
    tl = build_timeline(m, res["proofs"])
    quellen = {t["quelle"].split(" ·")[0].split(" ")[0] for t in tl}
    assert "WLAN-Verbindung" in {t["quelle"] for t in tl}
    assert any(t["quelle"].startswith("Ereignis") for t in tl)
    assert any(t["quelle"] == "Anruf" for t in tl)
    # chronologisch
    assert [t["sortkey"] for t in tl] == sorted(t["sortkey"] for t in tl)


def test_render_structure(synth_bundle):
    b = load_bundle(synth_bundle)
    m = build_model(b)
    res = analyze(b, m.real_aps, m.master.get("name", ""))
    html = build_html(b, m, res, {"case_id": "C-1", "item_id": "I-1", "sb": "Müller",
                                  "date": "2026-01-06", "generated_at": "2026-01-06T10:00:00Z"})
    assert html.count('class="section"') == 12
    assert html.count('class="datarow"') == html.count('class="originrow"')
    assert ">None<" not in html
    assert html.rstrip().endswith("</html>")
    assert "C-1" in html and "Müller" in html
    # kein D4-Badge/-Toggle mehr
    assert 'data-grade="D4"' not in html


# ───────────────────────── Report-Sidecar ───────────────────────────────────

def test_report_sidecar_written_and_verifies(synth_bundle, tmp_path, monkeypatch):
    """Der Report bekommt eine eigene .sha256-Sidecar, die zur Datei passt."""
    from fritzformat.digest import STATUS_OK, verify
    from fritzreport.cli import main

    out = tmp_path / "report.html"
    monkeypatch.setattr("sys.argv", [
        "fritzreport", str(synth_bundle), "-o", str(out),
        "--case-id", "C-1", "--item-id", "A-1", "--sb", "Test", "--date", "2026-01-01",
    ])
    assert main() == 0

    sidecar = out.with_suffix(out.suffix + ".sha256")
    assert sidecar.exists(), "Sidecar zum Report fehlt"

    status, digest = verify(out)
    assert status == STATUS_OK, f"Report verifiziert nicht gegen seine Sidecar: {status}"

    # sha256sum-kompatibles Format: "<digest>  <dateiname>"
    raw = sidecar.read_text(encoding="utf-8").strip()
    assert raw == f"{digest}  {out.name}"


def test_report_sidecar_detects_tampering(synth_bundle, tmp_path, monkeypatch):
    """Nachträgliche Änderung am Report wird über die Sidecar erkannt."""
    from fritzformat.digest import STATUS_OK, verify
    from fritzreport.cli import main

    out = tmp_path / "report.html"
    monkeypatch.setattr("sys.argv", [
        "fritzreport", str(synth_bundle), "-o", str(out),
        "--case-id", "C-1", "--item-id", "A-1", "--sb", "Test", "--date", "2026-01-01",
    ])
    assert main() == 0

    out.write_text(out.read_text(encoding="utf-8") + "<!-- tampered -->", encoding="utf-8")
    status, _ = verify(out)
    assert status != STATUS_OK, "Manipulation am Report muss auffallen"


# ───────────────────────── Fallkopf aus dem Bundle ──────────────────────────

def test_fallkopf_belegt_report_kopf_vor(synth_bundle, tmp_path, monkeypatch):
    """Liegt eine case.json im Bundle, landen ihre Werte ohne Rückfrage im Report."""
    from fritzformat import build_case, write_case
    from fritzreport.cli import main

    write_case(synth_bundle, build_case(case_id="C-2026-0815", item_id="A-01",
                                        sb="Killefiz", date="2026-08-04"))
    out = tmp_path / "report.html"
    monkeypatch.setattr("sys.argv", ["fritzreport", str(synth_bundle), "-o", str(out),
                                     "--no-prompt"])
    assert main() == 0

    html = out.read_text(encoding="utf-8")
    assert "C-2026-0815" in html
    assert "A-01" in html
    assert "Killefiz" in html


def test_cli_schlaegt_fallkopf_aus_dem_bundle(synth_bundle, tmp_path, monkeypatch):
    """CLI-Argumente gewinnen gegen die case.json — sonst ließe sich nichts korrigieren."""
    from fritzformat import build_case, write_case
    from fritzreport.cli import main

    write_case(synth_bundle, build_case(case_id="ALT", item_id="ALT", sb="ALT"))
    out = tmp_path / "report.html"
    monkeypatch.setattr("sys.argv", ["fritzreport", str(synth_bundle), "-o", str(out),
                                     "--no-prompt", "--case-id", "NEU"])
    assert main() == 0

    html = out.read_text(encoding="utf-8")
    assert "NEU" in html
    # die nicht überschriebenen Felder kommen weiter aus dem Bundle
    assert "ALT" in html


# ───────────────────────── Report-Name ──────────────────────────────────────

def test_reportname_traegt_den_abzugszeitpunkt(synth_bundle, tmp_path, monkeypatch):
    """Der Reportname teilt seinen Stamm mit dem Bundle-Verzeichnis — der
    Zeitstempel kommt aus der Hülle, nicht aus dem Verzeichnisnamen."""
    from fritzformat import build_case, write_case
    from fritzreport.cli import main

    write_case(synth_bundle, build_case(case_id="C-2026-0815", item_id="A-01"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["fritzreport", str(synth_bundle), "--no-prompt"])
    assert main() == 0

    erzeugt = list(tmp_path.glob("*.html"))
    assert len(erzeugt) == 1
    # Fixture-Bundle trägt extracted_at = 2026-01-06T10:00:00Z
    assert erzeugt[0].name == "C-2026-0815_A-01_20260106T100000Z.html"


def test_zwei_reports_kollidieren_nicht(synth_bundle, tmp_path, monkeypatch):
    """Früher nutzte der Name nur das Datum: Zwei Abzüge desselben Asservats am
    selben Tag ergaben denselben Reportnamen, der zweite überschrieb den ersten
    kommentarlos. Der Abzugszeitpunkt im Namen verhindert das."""
    import json

    from fritzreport.cli import main

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["fritzreport", str(synth_bundle), "--no-prompt",
                                     "--case-id", "C-1", "--item-id", "A-01"])
    assert main() == 0

    # zweiter Abzug desselben Asservats, eine Stunde später
    zweit = tmp_path / "zweiter_abzug"
    zweit.mkdir()
    for p in synth_bundle.iterdir():
        if p.is_file():
            (zweit / p.name).write_bytes(p.read_bytes())
    for p in zweit.glob("*.json"):
        if p.name.endswith(".sha256"):
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        if "extracted_at" in data:
            data["extracted_at"] = "2026-01-06T11:00:00Z"
            p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    monkeypatch.setattr("sys.argv", ["fritzreport", str(zweit), "--no-prompt",
                                     "--case-id", "C-1", "--item-id", "A-01"])
    assert main() == 0

    namen = sorted(p.name for p in tmp_path.glob("*.html"))
    assert len(namen) == 2, f"zweiter Report hat den ersten überschrieben: {namen}"


# ───────────────────────── Optional: echte Boxen ────────────────────────────

def test_real_boxes_end_to_end(real_boxes):
    for d in real_boxes:
        b = load_bundle(d)
        m = build_model(b)
        res = analyze(b, m.real_aps, m.master.get("name", "") or (m.real_aps[0] if m.real_aps else ""))
        html = build_html(b, m, res, {"case_id": "", "item_id": "", "sb": "",
                                      "date": "2026-01-01", "generated_at": "x"})
        assert html.count('class="section"') == 12
        assert ">None<" not in html
        assert res["proofs"], f"{d.name}: keine Verbindungsnachweise"


# ───────────────────────── Mehrfachfund-Schleife (#3) ────────────────────────

def _zweites_bundle(quelle, ziel, extracted_at="2026-01-06T14:30:00Z"):
    """Kopie eines Bundles mit abweichendem Abzugszeitpunkt."""
    import json
    ziel.mkdir(parents=True, exist_ok=True)
    for p in quelle.iterdir():
        if p.is_file():
            (ziel / p.name).write_bytes(p.read_bytes())
    for p in ziel.glob("*.json"):
        if p.name.endswith(".sha256") or p.name == "case.json":
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        if "extracted_at" in d:
            d["extracted_at"] = extracted_at
            p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return ziel


def test_mehrere_bundles_werden_nacheinander_ausgewertet(synth_bundle, tmp_path, monkeypatch):
    """Nach dem ersten Report wird das nächste Bundle angeboten — im Feld liegen
    mehrere Asservate nebeneinander, ein Neustart je Objekt hält auf."""
    from fritzreport.cli import main

    arbeit = tmp_path / "arbeit"
    arbeit.mkdir()
    for p in synth_bundle.iterdir():
        if p.is_file():
            (arbeit / "asservat_1" ).mkdir(exist_ok=True)
            (arbeit / "asservat_1" / p.name).write_bytes(p.read_bytes())
    _zweites_bundle(synth_bundle, arbeit / "asservat_2")

    monkeypatch.chdir(arbeit)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    # 1) erstes Bundle, dann 1) das verbliebene, dann fertig
    antworten = iter(["1", "1"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(antworten, ""))
    monkeypatch.setattr("sys.argv", ["fritzreport", "--case-id", "C-1", "--item-id", "A-1",
                                     "--sb", "X", "--date", "2026-08-04"])
    assert main() == 0

    erzeugt = sorted(p.name for p in arbeit.glob("*.html"))
    assert len(erzeugt) == 2, f"nicht beide Bundles ausgewertet: {erzeugt}"


def test_abbruch_beendet_die_schleife(synth_bundle, tmp_path, monkeypatch):
    """Der Anwender kann nach jedem Report aussteigen."""
    from fritzreport.cli import main

    arbeit = tmp_path / "arbeit"
    (arbeit / "asservat_1").mkdir(parents=True)
    for p in synth_bundle.iterdir():
        if p.is_file():
            (arbeit / "asservat_1" / p.name).write_bytes(p.read_bytes())
    _zweites_bundle(synth_bundle, arbeit / "asservat_2")

    monkeypatch.chdir(arbeit)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    # erstes Bundle auswerten, dann "3" = fertig (2 Rest-Einträge + Abbruch)
    antworten = iter(["1", "2"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(antworten, "2"))
    monkeypatch.setattr("sys.argv", ["fritzreport", "--case-id", "C-1", "--item-id", "A-1",
                                     "--sb", "X", "--date", "2026-08-04"])
    assert main() == 0

    assert len(list(arbeit.glob("*.html"))) == 1, "Abbruch hat nicht gegriffen"


def test_explizites_bundle_laeuft_ohne_schleife(synth_bundle, tmp_path, monkeypatch):
    """Mit Argument bleibt es bei genau einem Report — keine Rückfrage."""
    from fritzreport.cli import main

    out = tmp_path / "r.html"
    monkeypatch.setattr("sys.argv", ["fritzreport", str(synth_bundle), "-o", str(out),
                                     "--no-prompt"])
    assert main() == 0
    assert out.exists()
