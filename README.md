# legacy_report

Erzeugt aus einem **legacy_export**-Export einer AVM FRITZ!Box einen **self-contained
forensischen HTML-Report** — alle Daten eingebettet, Filter setzt der Betrachter nachträglich
im Browser, jede Zeile mit Herkunftsnachweis und Belegtheits-Grad.

> Schwestertool zu [legacy_export](../legacy_export): der Export *saugt* die Daten aus der
> Box, legacy_report *spuckt* den Bericht aus. **Kein** erneuter Datenabzug — legacy_report liest
> nur ein bereits gezogenes Bundle.

## Eigenschaften
- **Ein self-contained `.html`** je Box — offline lesbar, keine externen Ressourcen, Dark Mode.
- **Alle Rohdaten eingebettet** (jede JSON-Zeile, Supportdaten-Blöcke) plus Auswertungen.
- **Clientseitige Filter** (MAC, Gerätename, Telefonnummer, Zeitraum, Access Point,
  Belegtheits-Grad) — konsistent über alle Sektionen, nachträglich im Browser.
- **Belegtheits-Grade D1–D3** je Datenzeile (D1 plausibel · D2 testverifiziert · D3 abgeleitet).
- **Herkunftsnachweis** je Zeile: Quelldatei, SHA-256, Fundstelle als Zeilennummer, wörtlicher
  Original-Auszug (zeichengenau, kopierbar).
- **SHA-256-Verifikation** aller Bundle-Dateien gegen ihre `.sha256`-Sidecars (Badge ✔/✘).
- **Quellenübergreifende Timeline** — alle zeitgestempelten Daten (Ereignisse, WLAN-
  Verbindungsnachweise aus Supportdaten, Anrufe, `last_seen`) in einer chronologischen Achse.
- **Browser-Druck** der gefilterten Sicht mit Filter-Banner.

## Nutzung
```bash
python legacy_report.py <bundle-verzeichnis> --output report.html
# Beispiel:
python legacy_report.py ~/testdata/export/export_20260713T114105Z_7690 -o 7690.html
```

## Installation (Entwicklung)
```bash
git clone <repo> legacy_report && cd legacy_report
python -m venv .venv && source .venv/bin/activate
# keine Laufzeit-Abhängigkeiten (stdlib-only)
pip install -e '.[dev]'   # nur für Build/Tests (pyinstaller, pytest)
```

## Status
In Entwicklung (v0.1.0). Siehe `CLAUDE.md` und den Umsetzungsplan.
