# CLAUDE.md — legacy_report

Guidance für Claude Code in **diesem** Unterprojekt.

## Was das ist
Schwestertool zu **legacy_export**: der Export *saugt* forensische Daten live aus einer
FRITZ!Box und legt sie als JSON-Bundle ab (je Datenart eine `…_<typ>.json` + `.sha256`, plus
Roh-`supportdata_*.txt`). **legacy_report** *spuckt* daraus einen **self-contained forensischen
HTML-Report**. Kein erneuter Datenabzug — nur Aufbereitung eines vorhandenen Bundles.

Eigenständiges Feldwerkzeug wie der Export: **stdlib-only**, PyInstaller-Single-File-Binary,
**vollständig vom `it-forensic-automat` abgekoppelt** (keine Automat-Importe).

## Host / Daten (nicht verwechseln)
Läuft **lokal im LAN** (`claude.lan`), **nicht** auf dem Hetzner-VPS. Alle Ressourcen
liegen lokal: Testdaten unter `~/testdata/export/` (4 Boxen: 7490/7530ax/7590/7690).

## Herkunft / Referenzmaterial
- `_material/` (gitignored, **nicht** ausliefern): der HTML-Report-**PoC** (`poc/build_report.py`
  + `report.html` + `ANFORDERUNGSKATALOG.md` + JS-Tests) und die **Supportdaten-Methode**
  (`supportdata-methode/fritz_processor.py`). legacy_report produktiviert den PoC + webt die
  Methode ein.
- `ressourcen/methode.md` (**eingecheckt**): die forensische Supportdaten-Methodik.

## Belegtheits-Grade (3 Grade, kombinierbar)
- **D1** plausibel innerhalb Rohdaten · **D2** durch eigene forensische Tests verifiziert
  (methode.md) · **D3** abgeleitet / Interpretation.
- Zeile ohne Badge = reine Rohdaten-Wiedergabe (impliziter Normalfall).
- Verbindungsnachweise: methode.md-Parser → D1+D2, 802.11-Log-Parser → D1+D3.

## Struktur
`legacy_report/{cli,bundle,model,supportdata,render}.py` — Launcher `legacy_report.py`.
Umsetzungsplan: `~/.claude/plans/piped-chasing-raven.md`.

## Library-Recherche
Erst **deepwiki** (nur public GitHub), Fallback **exa**.
