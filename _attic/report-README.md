# legacy_report 🫧

Erzeugt aus einem **legacy_export**-Export einer AVM FRITZ!Box einen **self-contained
forensischen HTML-Report** — alle Daten eingebettet, Filter setzt der Betrachter nachträglich
im Browser, jede Zeile mit Herkunftsnachweis und Belegtheits-Grad.

---

## Der Workflow: Export zieht, Report berichtet

legacy_report ist die zweite Hälfte einer Zwei-Werkzeug-Kette für die FRITZ!Box-Forensik:

```
   ┌─────────────────┐        Bundle (Verzeichnis)        ┌──────────────────┐
   │  legacy_export  │  ──▶   legacy_export_*_*.json      │   legacy_report   │  ──▶  report.html
   │  (saugt live    │        + .sha256-Sidecars          │  (spuckt den     │       (self-contained,
   │   aus der Box)  │        + supportdata_*.txt         │   Report aus)    │        offline lesbar)
   └─────────────────┘                                    └──────────────────┘
```

1. **[legacy_export](../legacy_export)** verbindet sich live mit der Box und legt pro Datenart
   eine JSON-Datei + SHA-256-Sidecar ab (Anrufe, Telefonbuch, WLAN, Ereignisse, Mesh, Hosts,
   DHCP, Supportdaten …). Ergebnis: ein **Bundle-Verzeichnis**.
2. **legacy_report** liest dieses Bundle — **kein erneuter Box-Zugriff** —, verifiziert die
   Integrität, wertet die Supportdaten aus und rendert **einen HTML-Report**.

Beide Werkzeuge sind eigenständige, stdlib-only Single-File-Binaries für den USB-Stick-Feldeinsatz.

---

## Features

- **Ein self-contained `.html`** je Box — offline lesbar, keine externen Ressourcen, Dark Mode.
- **Alle Rohdaten eingebettet** (jede JSON-Zeile, Supportdaten-Blöcke) plus Auswertungen.
- **Clientseitige Filter** (MAC, Gerätename, Telefonnummer, Zeitraum, Access Point,
  Belegtheits-Grad) — konsistent über alle Sektionen, nachträglich im Browser gesetzt.
- **Belegtheits-Grade D1–D3** je Datenzeile (plausibel · testverifiziert · abgeleitet).
- **Herkunftsnachweis** je Zeile: Quelldatei, SHA-256, Fundstelle als Zeilennummer, wörtlicher
  Original-Auszug (zeichengenau, kopierbar).
- **SHA-256-Verifikation** aller Bundle-Dateien gegen ihre `.sha256`-Sidecars (Badge ✔/✘).
- **Verbindungsnachweise** aus den Supportdaten — zwei Parser vereint (Methoden-Parser + 802.11-Logs).
- **Quellenübergreifende Timeline** — alle zeitgestempelten Daten in einer chronologischen Achse.
- **Browser-Druck** der gefilterten Sicht mit Filter-Banner + Roh-Report-Hash.

---

## Installation

**Als Binary (Feldeinsatz):** die Single-File-Binaries aus dem Release herunterladen
(`legacy_report-<version>-linux-x86_64`, `…-windows-x86_64.exe`, …) — kein Python nötig.

**Aus dem Quellcode (Entwicklung):**
```bash
git clone https://github.com/TheGitHarry/legacy_report && cd legacy_report
python -m venv .venv && source .venv/bin/activate
# keine Laufzeit-Abhängigkeiten (stdlib-only)
pip install -e '.[dev]'   # nur für Build/Tests (pyinstaller, pytest)
```

---

## Bedienung — Kommandozeile

```
legacy_report [bundle] [-o report.html] [--open]
             [--case-id …] [--item-id …] [--sb …] [--date …] [--no-prompt]
```

### Geführter Ablauf (empfohlen)
Ohne Argumente im Verzeichnis mit den Bundles ausführen:
```bash
legacy_report
```
- **Auto-Discovery:** legacy_report sucht legacy_export-Bundles im aktuellen Verzeichnis.
  Genau eines → wird direkt genommen. Mehrere → nummerierte Auswahl.
- **Kopf-Felder-Abfrage** (Prompt): Case-ID · Asservat/Item-ID · Sachbearbeiter (SB) · Datum
  (Enter = leer, Datum-Default = heute).
- **Ausgabe:** sprechender Name `<Case>_<Item>_<Box>_<Datum>.html` im **aktuellen
  Arbeitsverzeichnis** — bewusst *nicht* in den Beweismittel-Ordner.

### Explizit / nicht-interaktiv (Automation)
```bash
legacy_report ~/export_20260722_7690 \
  --case-id CASE-2026-042 --item-id Asservat-7690 --sb "Müller" --date 2026-07-22 \
  -o /pfad/report.html
```
Per Flag gesetzte Kopf-Felder überspringen die Abfrage. `--no-prompt` erzwingt nicht-interaktiv
(keine Abfrage, leere/CLI-Werte). `--open` öffnet den Report anschließend im Browser.

---

## Bedienung — der Report im Browser

Der Report ist eine einzige HTML-Datei. Einfach im Browser öffnen (Doppelklick / aus dem
Dateisystem) — er funktioniert offline, ohne Server.

- **Sektionen** (12) starten **zugeklappt**. Das Dokument ist dadurch beim Öffnen kurz.
  Klick auf einen Eintrag im **Inhaltsverzeichnis** öffnet die Sektion und springt hin.
  Die Kopfzeile jeder Sektion zeigt die Trefferzahl auch im zugeklappten Zustand.
- **Filterleiste** (oben, immer sichtbar): MAC · Gerätename · Telefonnummer · Zeitraum von/bis ·
  Access Point · Belegtheits-Grad. Filter wirken **clientseitig über alle Sektionen** gemeinsam;
  „X von Y ausgeblendet" zeigt die Wirkung. **Zurücksetzen** stellt alles wieder her.
- **Herkunft** je Zeile: das „▸"-Symbol links klappt die Herkunftszeile auf — Quelldatei,
  SHA-256, **Fundstelle als Zeilennummer** und der wörtliche Original-Auszug (zeichengenau,
  per Knopf kopierbar).
- **Belegtheits-Grad-Filter:** „nur D2" isoliert die Methoden-Verbindungsnachweise,
  „nur D3" die aus den 802.11-Logs.
- **Drucken:** Knopf „Gefilterte Sicht drucken" (oder Strg+P) druckt nur die sichtbaren Zeilen,
  mit Banner im Kopf (aktive Filter + Roh-Report-Hash), als *gefilterte Sicht* gekennzeichnet.

---

## Belegtheits-Grade

Jede Zeile ohne Badge ist reine Rohdaten-Wiedergabe (impliziter Normalfall). Badges markieren
die besonderen Fälle, kombinierbar:

| Grad | Bedeutung |
|------|-----------|
| **D1** | Plausibel innerhalb der Rohdaten |
| **D2** | Durch eigene forensische **Tests verifiziert** (dokumentierte Methodik, `ressourcen/methode.md`) |
| **D3** | Abgeleitet / Interpretation (aus Rohdaten berechnet oder skizziert) |

**Verbindungsnachweise** (Sektion 6, aus den Supportdaten): Treffer des Methoden-Parsers tragen
**D1+D2**, Treffer aus den 802.11-Logs **D1+D3**. Beide Parser laufen auf jeder Box; ihre
Ergebnisse werden vereint (dedupliziert nach Zeitpunkt/MAC/Ereignis). Zeitstempel werden auf die
**Sekunde** angezeigt; Millisekunden bleiben als Sortierschlüssel und im Original-Auszug erhalten.

---

## Distribution (Binary bauen)

```bash
scripts/build-linux.sh          # → dist/legacy_report-<version>-linux-x86_64
# oder plattformneutral:
python scripts/build.py
```
CI (`.github/workflows/release.yml`) baut bei einem Tag `v*` die Matrix (Linux x86_64/aarch64,
Windows) und lädt die Artefakte hoch; Tests laufen vorab.

## Entwicklung & Tests

```bash
python -m pytest tests/      # 10 Tests: Kern-Invarianten + jsdom-Filtertest
```
Die Tests nutzen ein selbst-enthaltenes synthetisches Bundle — keine echten Daten nötig.
Architektur & Ist-Stand: siehe [CONCEPT.md](CONCEPT.md); Methodik: [ressourcen/methode.md](ressourcen/methode.md).

---

*Schwestertool zu [legacy_export](../legacy_export). Der Export saugt, der Report spuckt.*
