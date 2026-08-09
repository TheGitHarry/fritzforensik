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


# ───────────────────────── Sicherungszeitraum im Report ─────────────────────

def test_report_zeigt_gerechneten_zeitraum_mit_d1(synth_bundle):
    """Ohne Marker-Log wird der Zeitraum abgeleitet — und muss als solcher
    gekennzeichnet sein, sonst sieht Gerechnetes aus wie Protokolliertes.

    D1, nicht D3: Die beiden Werte stehen wörtlich in den signierten Hüllen
    (min/max der extracted_at). Abgeleitet ist allein der Schluss, dass sie den
    Sicherungszeitraum begrenzen — das ist „plausibel innerhalb Rohdaten".
    Nur die Dauer ist ein errechneter Wert und trägt deshalb D3."""
    b = load_bundle(synth_bundle)
    assert b.secured_source == "berechnet"

    m = build_model(b)
    res = analyze(b, m.real_aps, m.master.get("name", ""))
    html = build_html(b, m, res, {"case_id": "", "item_id": "", "sb": "",
                                  "date": "2026-01-06", "generated_at": "x"})
    assert "Gesichert von" in html
    assert "Export erstellt am" not in html
    # die Zeitraum-Zeilen tragen das D3-Badge
    zeile = html.split("Gesichert von", 1)[1].split("</tr>", 1)[0]
    assert 'class="grade gD1"' in zeile, "gerechneter Zeitraum ohne D1-Kennzeichnung"
    assert 'class="grade gD3"' not in zeile, "Rohwerte dürfen nicht als Interpretation gelten"

    # die Dauer dagegen steht nirgends in den Rohdaten → D3
    dauer_zeile = html.split("<th>Dauer", 1)[1].split("</tr>", 1)[0]
    assert 'class="grade gD3"' in dauer_zeile, "errechnete Dauer ohne D3"


def test_report_zeigt_protokollierten_zeitraum_ohne_badge(synth_bundle):
    """Mit Marker-Log stammt der Zeitraum aus dem Protokoll — ohne Badge, und
    die Werte weichen bewusst von min/max ab, damit der Test beides unterscheidet."""
    (synth_bundle / "fritzexport_20260106T095500Z.log").write_text(
        "2026-01-06 10:55:00,001 INFO SICHERUNG BEGINN 2026-01-06T09:55:00Z\n"
        "2026-01-06 11:07:42,880 INFO SICHERUNG ENDE 2026-01-06T10:07:42Z\n",
        encoding="utf-8")

    b = load_bundle(synth_bundle)
    assert b.secured_source == "log"
    # Fixture-Datensätze tragen 10:00:00 — der Log-Wert ist ein anderer
    assert b.secured_from == "2026-01-06T09:55:00Z"

    m = build_model(b)
    res = analyze(b, m.real_aps, m.master.get("name", ""))
    html = build_html(b, m, res, {"case_id": "", "item_id": "", "sb": "",
                                  "date": "2026-01-06", "generated_at": "x"})
    zeile = html.split("Gesichert von", 1)[1].split("</tr>", 1)[0]
    assert "2026-01-06 09:55:00 UTC" in zeile
    assert "grade g" not in zeile, "protokollierter Zeitraum ist Rohdaten-Wiedergabe — kein Badge"
    assert "12 min 42 s" in html, "Dauer fehlt oder falsch berechnet"


def test_report_weist_fehlendes_ende_aus(synth_bundle):
    """Abgebrochener Lauf: Beginn ohne Ende darf nicht als leeres Feld erscheinen."""
    (synth_bundle / "fritzexport_20260106T095500Z.log").write_text(
        "2026-01-06 10:55:00,001 INFO SICHERUNG BEGINN 2026-01-06T09:55:00Z\n",
        encoding="utf-8")

    b = load_bundle(synth_bundle)
    m = build_model(b)
    res = analyze(b, m.real_aps, m.master.get("name", ""))
    html = build_html(b, m, res, {"case_id": "", "item_id": "", "sb": "",
                                  "date": "2026-01-06", "generated_at": "x"})
    assert "nicht protokolliert" in html


def test_kein_irrefuehrender_report_hash_im_dokument(synth_bundle):
    """Der Report darf keinen Wert als „Report-Hash" ausweisen, der keiner ist.

    Früher stand in Metadaten und Druckbanner ein SHA256 über
    extracted_at + host, beschriftet als „Roh-Report-Hash". Wer ihn mit
    `sha256sum report.html` prüfte, bekam einen anderen Wert — genau die Art
    Abweichung, die in einer Hauptverhandlung erklärungsbedürftig wird.
    Der echte Hash steht seit #6 in der Sidecar; im Report kann er nicht stehen,
    er würde sich selbst verändern.
    """
    b = load_bundle(synth_bundle)
    m = build_model(b)
    res = analyze(b, m.real_aps, m.master.get("name", ""))
    html = build_html(b, m, res, {"case_id": "C-1", "item_id": "A-1", "sb": "X",
                                  "date": "2026-01-06", "generated_at": "x"})

    assert "Roh-Report-Hash" not in html
    # der Druckbanner verweist stattdessen auf die Sidecar
    banner = html.split('id="pbanner"', 1)[1].split("</div>", 1)[0]
    assert ".sha256" in banner, "Ausdruck nennt nicht, wo der echte Hash zu finden ist"
    assert "Gesichert" in banner, "Ausdruck ohne Zuordnung zum Sicherungszeitraum"


def test_varianten_mit_eigenen_zeitstempeln_bleiben_ein_bundle(synth_bundle):
    """Seit jede Roh-Supportdatei ihren eigenen Abruf datiert, teilen die Varianten
    eines Bundles **keinen** gemeinsamen Zeitstempel mehr.

    Bestätigt, was `support_glob` zusagt (Wildcard auf dem Stempel): Der Report ordnet
    beide Dateien demselben Bundle zu und verifiziert sie einzeln. Der Test hätte auch
    vor der Umstellung gehalten — er hält die Annahme fest, statt sie zu glauben.
    """
    from fritzformat import sha256_bytes, support_filename, write_sidecar
    body = b"##### BEGIN SECTION mesh\nx\n##### END SECTION mesh\n"
    mesh = synth_bundle / support_filename("mesh", "20260106T101530Z")  # 15 min später
    mesh.write_bytes(body)
    write_sidecar(mesh, sha256_bytes(body))

    b = load_bundle(synth_bundle)
    assert b.support["standard"].present and b.support["mesh"].present
    assert b.support["mesh"].name == mesh.name
    assert {e.status for e in b.coc} == {"ok"}


# ─────────────────────────── Betriebszeit ────────────────────────────────────

def _uptime(zeile: str, extracted_at: str = "2026-08-03T13:20:12Z") -> dict:
    """`_parse_uptime` über eine einzelne ``uptime:``-Zeile."""
    from fritzreport.bundle import SupportFile
    from fritzreport.supportdata import _parse_uptime
    sf = SupportFile(variant="standard", path=None, name="supportdata_standard.txt",
                     text=f"{zeile}\nip4_uptime=3600\n")
    return _parse_uptime(sf, extracted_at)


@pytest.mark.parametrize("zeile,text,boot", [
    # belegt im Korpus: alle Golden-Bundles
    ("uptime: 11:41:13 up 85 days, 14:24,  load average: 0.1",
     "85 days, 14:24", "2026-05-09"),
    # belegt: 7690 nach Firmware-Neustart, 21 min Laufzeit
    ("uptime: 15:20:12 up 21 min,  load average: 0.21, 0.14, 0.10",
     "21 min", "2026-08-03"),
    # Einzahl-Variante
    ("uptime: 15:20:12 up 1 day, 2:03,  load average: 0.1",
     "1 day, 2:03", "2026-08-02"),
    # 1–24 h: nur Stunden:Minuten, ohne Tagesangabe
    ("uptime: 15:20:12 up  1:23,  load average: 0.1", "1:23", "2026-08-03"),
    # procps schreibt bei vollen Stunden Minuten aus, auch mit Tagen davor
    ("uptime: 15:20:12 up 2 days, 21 min,  load average: 0.1",
     "2 days, 21 min", "2026-08-01"),
])
def test_uptime_formen_werden_geparst(zeile, text, boot):
    """Vier der fünf Formen fielen früher durch: Erkannt wurden nur ganze Tage.

    Forensisch ist die kurze Laufzeit der wahrscheinliche Fall — eine beschlagnahmte
    Box wird für den Transport vom Netz genommen und am Auswerteplatz neu gestartet.
    Genau dann blieb das abgeleitete Boot-Datum leer und die Rohzeile stand samt
    ``load average`` im Bericht.
    """
    up = _uptime(zeile)
    assert up["uptime_text"] == text
    assert up["boot_derived"] == boot


def test_boot_datum_rechnet_die_stunden_mit():
    """Nur die Tage abzuziehen verschiebt das Boot-Datum um einen Tag, sobald die
    Stunden der Laufzeit über der Tageszeit des Abzugs liegen.

    Abzug am 13.07. um 11:41 Uhr, Laufzeit 85 Tage 14:24 → der Start liegt am
    **18.04.** um 21:17, nicht am 19.04.
    """
    up = _uptime("uptime: 11:41:13 up 85 days, 14:24,  load average: 0.1",
                 extracted_at="2026-07-13T11:41:13Z")
    assert up["boot_derived"] == "2026-04-18"


def test_unbekannte_uptime_form_behauptet_kein_boot_datum():
    """Was nicht geparst wird, wird nicht gerechnet — und die Zeile im Bericht sagt
    das, statt ein leeres Feld neben Label und D3-Badge zu zeigen."""
    up = _uptime("uptime: irgendwas ganz anderes")
    assert up["boot_derived"] == ""

    from fritzreport.render import _uptime_block
    assert "nicht ableitbar" in _uptime_block(up)


# ─────────────────── Selbstauskunft der Box (TR-064) ─────────────────────────

def test_deviceinfo_erscheint_im_bericht(synth_bundle):
    """Modellname und Laufzeit stehen roh im Bericht — beide unabhängig von den
    Supportdaten und damit eine zweite Quelle neben deren `uptime:`-Zeile."""
    html = _render(load_bundle(synth_bundle))
    assert "FRITZ!Box 7590" in _zeile(html, "Modell laut TR-064")
    assert "441000" in _zeile(html, "Uptime laut TR-064 (DeviceInfo), roh")


def test_ohne_deviceinfo_keine_leeren_zeilen(tmp_path):
    """Boxen ohne TR-064 liefern die Datenart nicht. Dann fehlen die Zeilen ganz,
    statt mit leerem Wert dazustehen."""
    from fritzformat import build_envelope, dataset_filename, sha256_bytes, write_sidecar
    import json
    body = json.dumps(build_envelope(tool="fritzexport", version="0.1", host="h",
                                     type_name="hosts", records=[])).encode("utf-8")
    p = tmp_path / dataset_filename("h", "20260106T100000Z", "hosts")
    p.write_bytes(body)
    write_sidecar(p, sha256_bytes(body))

    html = _render(load_bundle(tmp_path))
    assert "Modell laut TR-064" not in html


# ──────────────────── Speichergrenze der Anrufliste ──────────────────────────

def _mit_anrufen(d, anzahl: int):
    """Ersetzt die calls.json des Bundles durch `anzahl` Datensätze."""
    import json
    from fritzformat import build_envelope, sha256_bytes, write_sidecar
    p = next(d.glob("*_calls.json"))
    records = [{"Typ": "1", "Datum": f"01.01.26 {i // 60:02d}:{i % 60:02d}",
                "Name": "", "Rufnummer": "0048123",
                "Landes-/Ortsnetzbereich": "", "Nebenstelle": "",
                "Eigene Rufnummer": "", "Dauer": "0:30"} for i in range(anzahl)]
    body = json.dumps(build_envelope(tool="fritzexport", version="0.3.1",
                                     host="https://fritz.box", type_name="calls",
                                     records=records, extracted_at="2026-01-06T10:00:00Z"),
                      indent=2, ensure_ascii=False).encode("utf-8")
    p.write_bytes(body)
    write_sidecar(p, sha256_bytes(body))
    return d


def test_anrufliste_an_der_speichergrenze_wird_gekennzeichnet(synth_bundle):
    """Die Box hält nur die neuesten 400 Anrufe — nachgewiesen an lückenlosen, weit
    über 400 hinaus laufenden `Id`-Werten (#26). Genau 400 Einträge heißen deshalb:
    Es gab mehr, der Rest ist **auf der Box** verloren, nicht beim Export.

    Eine Liste an der Grenze sieht aus wie eine vollständige. Wer aus der Abwesenheit
    eines Anrufs schließt, muss das sehen."""
    html = _render(load_bundle(_mit_anrufen(synth_bundle, 400)))
    hinweis = html.split('id="s7"', 1)[1].split("</details>", 1)[0]
    assert "Speichergrenze" in hinweis
    assert "400" in hinweis


def test_kurze_anrufliste_ohne_hinweis(synth_bundle):
    """Unter der Grenze ist die Liste vollständig — ein Hinweis wäre dort eine
    Behauptung ins Blaue."""
    html = _render(load_bundle(_mit_anrufen(synth_bundle, 399)))
    assert "Speichergrenze" not in html


# ─────────────────── system_kpi (ab FRITZ!OS 08.25) ──────────────────────────

#: Wörtlich gekürzt aus einem 7690-Abzug (285.08.25) — Feldreihenfolge wie dort.
KPI_SEKTION = (
    "##### BEGIN SECTION system_kpi\n"
    '{ "sv":"gen/v1", "kpi": { "socType": null, "memoryUsage": 44, "starts": 32,'
    ' "lifetime": "17 hours 24 days 6 months 1 years", "uptime": 1347,'
    ' "power": 8.76 } }\n'
    "##### END SECTION system_kpi\n"
)


def _kpi(text: str) -> dict:
    from fritzreport.bundle import SupportFile
    from fritzreport.supportdata import parse_system_kpi
    return parse_system_kpi(SupportFile(variant="standard", path=None,
                                        name="supportdata_standard.txt", text=text))


def test_system_kpi_wird_gelesen():
    """Drei Felder sind forensisch verwertbar: Startzähler, Gesamtbetriebsdauer und
    die maschinenlesbare Uptime in Sekunden."""
    kpi = _kpi("uptime: 15:20:12 up 21 min\n" + KPI_SEKTION)
    assert kpi["starts"] == 32
    assert kpi["lifetime"] == "17 hours 24 days 6 months 1 years"
    assert kpi["uptime_s"] == 1347
    assert kpi["line"] == 3, "Fundstelle zeigt nicht auf den JSON-Blob"


def test_ohne_system_kpi_bleibt_der_bericht_still(synth_bundle):
    """Vor FRITZ!OS 08.25 gibt es die Sektion nicht — und auch danach nicht überall
    (die 7590 des Korpus führt sie unter 08.25 nicht). Ihr Fehlen ist kein Fehler und
    darf keine leeren Zeilen erzeugen."""
    b = load_bundle(synth_bundle)
    m = build_model(b)
    assert analyze(b, m.real_aps, m.master.get("name", ""))["system_kpi"] == {}
    assert "system_kpi" not in _render(b)


def test_wlan_kpi_sektion_ist_nicht_system_kpi():
    """Die 7590 führt unter 08.25 eine Sektion ``KPI Current KPI data`` — WLAN-Zahlen
    ohne ``starts``/``lifetime``. Ein unvollständig gematchter Sektionsname zöge daraus
    Kennzahlen, die dort nicht stehen."""
    assert _kpi("##### BEGIN SECTION KPI Current KPI data\n"
                'KPI version 10:\n{ "sv": "gen/v1", "cfg": {} }\n'
                "##### END SECTION KPI\n") == {}


def test_unlesbares_system_kpi_wird_verworfen():
    """Ein Blob, der kein JSON ist, darf den Report nicht abbrechen — und erst recht
    keine halb geratenen Zahlen liefern."""
    assert _kpi("##### BEGIN SECTION system_kpi\nkein json\n"
                "##### END SECTION system_kpi\n") == {}


def test_system_kpi_erscheint_im_bericht(synth_bundle):
    """Die ganze Strecke: Sektion in der Datei → analyze → gerenderte Zeilen."""
    from fritzformat import sha256_bytes, write_sidecar
    p = next(synth_bundle.glob("supportdata_standard_*.txt"))
    body = p.read_bytes() + KPI_SEKTION.encode()
    p.write_bytes(body)
    write_sidecar(p, sha256_bytes(body))

    html = _render(load_bundle(synth_bundle))
    zeile = _zeile(html, "Startvorgänge (system_kpi)")
    assert "32" in zeile
    assert "17 hours 24 days 6 months 1 years" in html
    assert "1347" in html


def test_startzaehler_nennt_seinen_offenen_bezugspunkt():
    """Was `starts` zählt — seit Werksauslieferung, Reset oder Firmware-Update — ist
    aus den Daten nicht ableitbar. Eine nackte „32" liest sich wie eine Aussage über
    die Lebensdauer des Geräts; die Einschränkung gehört daneben."""
    from fritzreport.render import _system_kpi_block
    block = _system_kpi_block({"starts": 32, "lifetime": "1 years", "uptime_s": 1347,
                               "file": "f.txt", "line": 3})
    assert "nicht belegt" in block


# ───────────────────────── Versatz der Box-Uhr ───────────────────────────────

def _zeilen(html: str, schluessel: str) -> list[str]:
    """Alle Metadaten-Zeilen zu diesem Schlüssel — samt Badge-Spalte.

    Bewusst über den Schlüssel geankert statt über das ganze Dokument: Ein Test, der
    nur `in html` prüft, bleibt grün, wenn die Zeile ganz verschwindet oder der Text
    zufällig anderswo steht.
    """
    marke = f"<th>{schluessel}</th>"
    assert marke in html, f"Metadaten-Zeile fehlt: {schluessel}"
    return [rest.split("</tr>", 1)[0] for rest in html.split(marke)[1:]]


def _zeile(html: str, schluessel: str) -> str:
    """Wie `_zeilen`, für Schlüssel, die genau einmal vorkommen."""
    zeilen = _zeilen(html, schluessel)
    assert len(zeilen) == 1, f"{len(zeilen)} Zeilen für {schluessel}, erwartet: 1"
    return zeilen[0]


def _versatz_zeile(html: str, herkunft: str) -> str:
    """Die Zeitversatz-Zeile *einer* Quelle — der Report zeigt je Quelle eine."""
    treffer = [z for z in _zeilen(html, "Zeitversatz Box ↔ Referenz") if herkunft in z]
    assert len(treffer) == 1, f"keine eindeutige Zeitversatz-Zeile für {herkunft}"
    return treffer[0]


def _offset(b, quelle: str):
    """Die Uhr-Messung einer Quelle aus dem geladenen Bundle."""
    treffer = [c for c in b.clock_offsets if c.quelle == quelle]
    assert len(treffer) == 1, f"genau eine Messung je Quelle erwartet: {quelle}"
    return treffer[0]


def _render(b):
    m = build_model(b)
    res = analyze(b, m.real_aps, m.master.get("name", ""))
    return build_html(b, m, res, {"case_id": "C-1", "item_id": "A-1", "sb": "X",
                                  "date": "2026-01-06", "generated_at": "x"})


def test_supportdata_klammer_wird_berechnet(synth_bundle):
    """Box meldet 11:00:02 CET (= 10:00:02Z), Marken 10:00:00Z / 10:00:40Z.
    Obere Schranke = 2 s Differenz + 1 s Quantisierung."""
    c = _offset(load_bundle(synth_bundle), "supportdata:standard")
    assert c.versatz_max_s == 3
    assert c.beidseitig is False
    assert c.herkunft == "marker"


def test_supportdata_zeigt_keine_untere_schranke(synth_bundle):
    """Der Wächter gegen die Rückkehr einer irreführenden Zahl.

    ``versatz_min_s`` ist bei dieser Quelle die Übertragungsdauer, kein gemessener
    Rückstand — im Bericht gelesen würde „−38 s" zu einer Behauptung über die
    Box-Uhr, die niemand gemessen hat.
    """
    b = load_bundle(synth_bundle)
    assert _offset(b, "supportdata:standard").versatz_min_s == -38   # im Modell …
    html = _render(b)
    assert "-38" not in html and "−38" not in html   # … aber nie im Bericht
    assert "geht nicht mehr als 3 s vor" in html


def test_rueckwaerts_laufende_klammer_wird_verworfen(synth_bundle):
    """Steht die Antwort *vor* ihrer Anfrage — gekürztes oder manipuliertes Log —,
    ist das keine Messung, sondern eine negative Klammerbreite.

    `parse_uhr_spans` paart die Marken zwar in Logreihenfolge und erzeugt diesen Fall
    nicht mehr selbst; die Leseseite darf sich darauf aber nicht verlassen. Ungeprüft
    ergäbe die Klammer hier „geht nachweislich mindestens 37 s nach".
    """
    from fritzformat import session_log_filename
    (synth_bundle / session_log_filename("20260106T100000Z")).write_text(
        "2026-01-06 11:00:40,000 INFO UHRZEIT ANFRAGE supportdata:standard "
        "2026-01-06T10:00:40.000Z\n"
        "2026-01-06 11:00:00,000 INFO UHRZEIT ANTWORT supportdata:standard "
        "2026-01-06T10:00:00.000Z\n",
        encoding="utf-8")

    b = load_bundle(synth_bundle)
    assert b.clock_offsets == []
    assert "nicht geprüft" in _render(b)


def test_zeitversatz_zeile_sagt_genau_das_gemessene(synth_bundle):
    """Die Zeile trägt die belegte Aussage samt Quelle und Belegtheitsgrad — und
    nichts Stärkeres: Gemessen ist eine Schranke, keine Übereinstimmung.

    Der Vorgänger dieses Tests verbot nur vier Wendungen („Uhr ist korrekt",
    „synchron" …). Keine davon kam je im Produktionscode vor; entfernte man die
    gesamte Uhr-Darstellung aus dem Report, blieb er grün. Er ankert deshalb jetzt
    auf der Zeile selbst statt auf dem ganzen Dokument.
    """
    html = _render(load_bundle(synth_bundle))
    zeile = _versatz_zeile(html, "Supportdaten-Kopf, standard")
    assert "geht nicht mehr als 3 s vor" in zeile
    assert 'class="grade gD3"' in zeile, "gerechneter Versatz ohne D3-Badge"
    for verboten in ("Uhr ist korrekt", "korrekte Uhr", "synchron", "Uhr stimmt"):
        assert verboten not in html, f"zu starke Aussage im Report: {verboten}"


def test_box_zeit_wird_woertlich_wiedergegeben(synth_bundle):
    """Die Kopfzeile wird zeichengenau gezeigt. Eine nach UTC umgerechnete Zeit mit
    dem Ortszeit-Kürzel dahinter („10:00:02 CET") wäre falsch etikettiert."""
    html = _render(load_bundle(synth_bundle))
    assert "Tue Jan  6 11:00:02 CET 2026" in html


def test_ohne_quelle_steht_nicht_geprueft(tmp_path):
    """Bundle ohne Supportdaten und ohne boxtime: Der Report muss das benennen,
    statt die Zeile wegzulassen — „ungeprüft" ist selbst eine Aussage."""
    from fritzformat import dataset_filename, sha256_bytes, write_sidecar, build_envelope
    import json
    body = json.dumps(build_envelope(tool="fritzexport", version="0.1", host="h",
                                     type_name="hosts", records=[]),
                      indent=2).encode("utf-8")
    p = tmp_path / dataset_filename("h", "20260106T100000Z", "hosts")
    p.write_bytes(body)
    write_sidecar(p, sha256_bytes(body))

    b = load_bundle(tmp_path)
    assert b.clock_offsets == []
    html = _render(b)
    assert "nicht geprüft" in html
    assert ">None<" not in html


def test_tr064_klammer_wird_aus_boxtime_gebildet(synth_bundle):
    """Die ganze Strecke des TR-064-Zweigs: `boxtime.json` → `load_bundle` →
    `ClockOffset` → gerenderte Zeile.

    Der frühere Test dieses Zweigs setzte `clock_offsets` von Hand und übersprang
    damit genau diese Strecke. Sie war deshalb von keinem Test abgedeckt: Ließ man
    `_parse_box_iso` immer `None` liefern, blieben beide Suiten grün — auch die
    Golden-Tests, denn alle Abzüge des Korpus stammen aus der Zeit vor `boxtime`.
    """
    b = load_bundle(synth_bundle)
    c = _offset(b, "tr064:time")
    assert c.beidseitig is True
    assert c.herkunft == "marker"
    assert c.box_lokal == "2026-01-06T11:00:02+01:00", "Box-Zeit nicht wörtlich"
    assert (c.versatz_min_s, c.versatz_max_s) == (0, 1)
    assert c.fundstelle["file"].endswith(".json"), "Messung ohne Fundstelle"

    zeile = _versatz_zeile(_render(b), "TR-064 Time:1")
    assert "Abweichung zwischen +0 s und +1 s" in zeile
    assert "Klammer 1 s" in zeile, "beidseitige Quelle ohne Fehlerschranke"
    assert "geht nicht mehr als" not in zeile, "einseitige Formulierung bei TR-064"


def test_beide_quellen_stehen_nebeneinander(synth_bundle):
    """Liegen TR-064 **und** Supportdaten vor, beantwortet der Report das mit zwei
    Zeilen — die schärfere zuerst. Dieser Fall trat in keinem Test je auf."""
    zeilen = _zeilen(_render(load_bundle(synth_bundle)), "Zeitversatz Box ↔ Referenz")
    assert len(zeilen) == 2
    assert "TR-064 Time:1" in zeilen[0]
    assert "Supportdaten-Kopf" in zeilen[1]


def _mit_offset(b, **kw):
    """Ersetzt die Uhr-Messungen des Bundles durch eine beidseitige (TR-064)."""
    from fritzreport.bundle import ClockOffset
    felder = dict(quelle="tr064:time", box_lokal="2026-01-06T11:00:02+01:00",
                  ref_von="2026-01-06T10:00:01.900Z",
                  ref_bis="2026-01-06T10:00:02.100Z",
                  beidseitig=True, herkunft="marker")
    b.clock_offsets = [ClockOffset(**{**felder, **kw})]
    return b


def test_klammer_um_die_null_benennt_den_befund(synth_bundle):
    """H9 verlangt, dass auch der *negative* Befund benannt wird. Schließt die
    beidseitige Klammer die Null ein, ist kein Versatz nachweisbar — das ist eine
    Aussage und muss dastehen, statt dass der Leser das Intervall selbst gegen die
    Null hält."""
    html = _render(_mit_offset(load_bundle(synth_bundle),
                               versatz_min_s=-1, versatz_max_s=1))
    zeile = _zeile(html, "Zeitversatz Box ↔ Referenz")
    assert "Abweichung zwischen -1 s und +1 s" in zeile
    assert "kein Versatz nachweisbar" in zeile


def test_nachgewiesener_versatz_wird_nicht_wegerklaert(synth_bundle):
    """Kehrseite: Liegt die Null außerhalb der Klammer, *ist* ein Versatz belegt.
    Der Befund darf dann nicht danebenstehen."""
    html = _render(_mit_offset(load_bundle(synth_bundle),
                               versatz_min_s=4, versatz_max_s=6))
    zeile = _zeile(html, "Zeitversatz Box ↔ Referenz")
    assert "Abweichung zwischen +4 s und +6 s" in zeile
    assert "nachweisbar" not in zeile
