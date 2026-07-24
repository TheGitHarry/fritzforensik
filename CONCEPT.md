# fritzreport — Konzept & Architektur (Stand 2026-07-22, v0.1.0)

> Schwestertool zu **fritzexport**. Der Export *saugt* die Daten live aus der
> FRITZ!Box (JSON-Bundle je Datenart + `.sha256`, plus Roh-`supportdata_*.txt`).
> **fritzreport** *spuckt* daraus einen **self-contained forensischen HTML-Report**.

## Zweck / Abgrenzung
- **Kein** erneuter Datenabzug — liest ein bereits gezogenes fritzexport-Bundle.
- Eigenständiges Feldwerkzeug: **stdlib-only**, PyInstaller-Single-File-Binary,
  **vollständig vom `it-forensic-automat` abgekoppelt** (keine DB-/ESB-/Job-Importe).
- Übernommen wurden genau zwei Dinge: die **Supportdaten-Methode** aus dem `fritz`-Worker
  (`fritz_processor.py`) und der **HTML-Report-PoC** (`build_report.py`), beide produktiviert.

## Datenfluss
```
Bundle-Verzeichnis
   │  bundle.py     Erkennung · SHA-256-VERIFIKATION · Metadaten · Herkunfts-Slices
   ▼
   ├─ model.py      JSON-Records → Anzeige/Filter/Herkunft/Grade (Hosts, Mesh, wifi,
   │                calls, phonebook, events, dhcp, Aggregate)
   ├─ supportdata.py  Roh-.txt → Verbindungsnachweise (BEIDE Parser, vereint)
   ▼
   render.py        12 Sektionen, Inline-CSS/JS, Filter/Druck/DarkMode → ein .html
   ▲
   cli.py           fritzreport <bundle> -o report.html  (Kopf-Felder per Prompt)
```

## Module (`fritzreport/`)
| Datei | Aufgabe |
|-------|---------|
| `bundle.py` | Bundle laden; **jede Datei gegen ihre `.sha256` verifizieren** (ok/mismatch/no_sidecar); Metadaten (`tool/version/host/extracted_at`); `record_slices` = Fundstelle jedes JSON-Records (Zeilennummer + wörtlicher Auszug). |
| `model.py` | Rohdatensätze → Anzeige-Dicts mit Filterschlüsseln (`f_mac/name/phone/ap/iso`), `grades`, `origin`. Enthält das **3-Grade-System** und die Umnummerierung. |
| `supportdata.py` | **methode.md-Parser** (aus fritz_processor: dhcpd→Register, dann dhcp/STATION_MODULE/WLAN_EVENTS/Events/MESH) **+ 802.11-Log-Parser** (aus PoC), beide auf jeder Box, Ergebnisse vereint/dedupliziert. Plus Betriebszeit. |
| `render.py` | HTML/CSS/JS (aus PoC), 12 Sektionen, Zellen-Renderer, Herkunftszeilen, quellenübergreifende Timeline. |
| `cli.py` | Argparse + **interaktive Abfrage** der Kopf-Felder (CLI-Args überspringen die Abfrage; `--no-prompt` erzwingt nicht-interaktiv). |

## Belegtheits-Grade (3 Grade, kombinierbar)
Das alte „D1 = aus signierter Rohdatei" **entfällt** (trivial — alles wird aus Rohdaten
aufbereitet; Zeile ohne Badge = reine Rohdaten). Umnummerierung: alt D2→**D1**, D3→**D2**, D4→**D3**.
- **D1** — plausibel innerhalb Rohdaten
- **D2** — durch eigene forensische **Tests verifiziert** (methode.md-Methode)
- **D3** — abgeleitet / Interpretation
- Verbindungsnachweise: **methode.md-Parser → D1+D2**, **802.11-Log-Parser → D1+D3**.

## Supportdaten — beide Parser (empirisch begründet)
Marker-Zählung über die 4 Testboxen: kein Weg allein genügt.
| Box | methode.md-Treffer (D1+D2) | 802.11-Treffer (D1+D3) | Interface |
|-----|---:|---:|---|
| 7530ax | 1958 | 238 | `wl0/wl1` (Broadcom) |
| 7690 | 1401 | 21 | `ath0/1` (Atheros) |
| 7590 | 1937 | 0 | nur Zähler, keine Einzel-Events |
| 7490 | 1840 | 0 | nur Kernel-Tick-Logs (keine Wall-Clock) |
→ Beide laufen auf jeder Box; Dedup-Schlüssel `(Sekunde, MAC, Event)`; Grade je Herkunft.

## Report-Aufbau (12 Sektionen, Anforderungen A–G erfüllt)
Fixe Filterleiste (MAC · Name · Telefon · Zeitraum · AP-Dropdown nur echte Mesh-APs ·
Grade D1–D3 · Reset · „X von Y ausgeblendet"), 2-spaltiges TOC mit Live-Zählern.
1 Übersicht/Metadaten · 2 Chain of Custody **(Integritäts-Badge ✔/✘)** · 3 Hosts · 4 Mesh ·
5 Clients · 6 **Verbindungsnachweise (Supportdaten)** · 7 Anrufe · 8 Telefonbuch · 9 Ereignisse ·
10 **Vollständige Timeline (quellenübergreifend)** · 11 DHCP · 12 Belegtheits-Legende.
- Sektionen `<details>`, **Grundzustand zu**, Kopfzeile zeigt Trefferzahl auch zugeklappt.
- Je Zeile aufklappbare **Herkunftszeile**: Quelldatei · SHA256 · **Zeilennummer** ·
  wörtlicher Original-Auszug (zeichengenau, kopierbar).
- **Zeitstempel** auf Sekunde gekürzt; Millisekunden bleiben als Sortierschlüssel + im
  Original-Auszug erhalten.
- Self-contained (Inline-CSS/JS, keine externen Ressourcen), Dark Mode, Browser-Druck der
  gefilterten Sicht mit Banner + Roh-Report-Hash.

## Kopf-Felder
**CaseID · ItemID · SB (Sachbearbeiter) · Date** — v0.1.0 per **interaktivem Prompt** erhoben
(CLI-Args als Override/Automation). Datum-Default = heute.

## Distribution & Tests
- **PyInstaller-Single-File-Binary** (`scripts/build.py`), Linux/Windows/arm; CI in
  `.github/workflows/release.yml` (Tag `v*` → Matrix-Build, Tests vorab).
- **Tests**: `tests/` — 9 pytest-Kern-Invarianten (Verifikation, Grade, beide Parser,
  zeichengenaue Herkunft, Render-Struktur, 4 echte Boxen) + jsdom-Filtertest im echten DOM.
  Selbst-enthaltenes synthetisches Bundle als Fixture.

## Verifiziert (Stand v0.1.0)
- 10/10 Tests grün · alle 4 Boxen erzeugen valide Reports · alle Hashes ✔ ·
  Herkunft zeichengenau · Binary gebaut und gegen die 7690 getestet.

## Offen / später
- Archiv-Eingabe (ZIP-Bundle) zusätzlich zum Verzeichnis.
- Owner-Korrelation WLAN↔Telefonbuch. · D2 (Test-verifiziert) auf weitere Methoden ausweiten.
- 7490/7590: 802.11-Nachweise nur über methode.md — falls dort weitere Zeitquellen nötig werden.

## Herkunft des Materials
`_material/` (gitignored): PoC (`poc/`) + fremde Methode (`supportdata-methode/`).
`ressourcen/methode.md` (**eingecheckt**): die forensische Supportdaten-Methodik.
Umsetzungsplan: `~/.claude/plans/piped-chasing-raven.md`.
