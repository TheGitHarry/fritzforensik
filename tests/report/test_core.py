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
