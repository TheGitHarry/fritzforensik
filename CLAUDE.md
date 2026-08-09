# CLAUDE.md

Guidance für Claude Code in diesem Repository.

## Was das Repo enthält

Zwei zusammengehörige Feldwerkzeuge für FRITZ!Box-Forensik plus ihr gemeinsames
Formatmodul:

| Paket | Rolle | Abhängigkeiten |
|---|---|---|
| `fritzexport/` | **Live-Abzug** aus einer laufenden Box → Bundle-Verzeichnis | `requests` |
| `fritzreport/` | Bundle → **self-contained HTML-Report** (kein Box-Zugriff) | **stdlib-only** |
| `fritzformat/` | gemeinsamer **Formatvertrag** beider Seiten | **stdlib-only** |

Hervorgegangen aus den vormals getrennten Repos `legacy_export` (→ fritzexport) und
`legacy_report` (→ fritzreport); beide Historien stecken in diesem Repo.

## fritzformat — bitte hier zuerst schauen

`fritzformat` ist die **einzige Wahrheit** über das Bundle-Format: Dateinamen
(`names.py`), Hüllformat (`envelope.py`), SHA256-Sidecars (`digest.py`), Fallkopf
(`casefile.py` — `case.json` plus die von beiden Werkzeugen genutzte Abfrage),
Sicherungszeitraum (`sessionlog.py` — die Marker im Sitzungslog, Export schreibt,
Report liest).

Vorher lag dieses Wissen **vierfach** vor — Schreibseite in `output.py`, nochmal im
Supportdaten-Extractor, Leseseite in `bundle.py`, und ein viertes Mal im Test-Fixture.
Eine Abweichung wäre erst im Feld aufgefallen. **Formatänderungen deshalb ausschließlich
in `fritzformat` vornehmen**, nie in den Werkzeugen nachbauen.

`fritzformat` **muss stdlib-only bleiben** — es wird von `fritzreport` importiert, das
seine Abhängigkeitsfreiheit behalten soll (schlankes, netzwerkfreies Report-Binary).
`tests/format/test_stdlib_only.py` wacht statisch darüber.

## Wie fritzexport arbeitet

- **Auth**: AVM Web-UI-SID-Verfahren (PBKDF2-Challenge-Response, MD5-Fallback für ältere
  Firmware) — [auth.py](fritzexport/auth.py).
- **Discovery**: SSDP-Multicast im LAN; bei genau einer Box automatischer Login, sonst
  Auswahlmenü oder `--host` — [discover.py](fritzexport/discover.py).
- **Protokolle**: primär TR-064 (SOAP über UPnP), Web-UI-Fallback wo möglich; reine
  Web-UI-Pfade für Daten ohne TR-064-Pendant (Anrufliste, Telefonbuch, Events, Supportdaten).
- **Extractoren**: ein Modul je Datenart in [fritzexport/extractors/](fritzexport/extractors/),
  CLI-Glue in [cli.py](fritzexport/cli.py). Die Registry `EXTRACTORS` muss deckungsgleich
  mit `fritzformat.JSON_TYPES` bleiben — ein Test prüft das.

## Wie fritzreport arbeitet

`{bundle,model,supportdata,render}.py`. `bundle.py` lädt und **verifiziert** jede Datei
gegen ihre Sidecar und stellt je Datensatz die Fundstelle bereit (Zeilennummer + wörtlicher
Auszug). `supportdata.py` parst die Roh-Supportdaten (Sektionen, 802.11-Logs) — der Export
*holt* diese Dateien nur, er parst sie nicht; hier gibt es keine doppelte Logik.

**Belegtheits-Grade** (kombinierbar): **D1** plausibel innerhalb der Rohdaten · **D2** durch
eigene forensische Tests verifiziert ([ressourcen/methode.md](ressourcen/methode.md)) ·
**D3** abgeleitet/Interpretation. Zeile ohne Badge = reine Rohdaten-Wiedergabe.
Verbindungsnachweise: methode.md-Parser → D1+D2, 802.11-Log-Parser → D1+D3.

## Tests

```bash
python3 -m pytest             # volle Suite, offline
python3 -m pytest -m golden   # NUR die Golden-Tests gegen ~/testdata/_work
```

`tests/{format,export,report}/`. Standardmäßig deselektiert: `network` (echtes LAN) und
`golden` (echte Forensikdaten, liegen bewusst nicht im Repo).

`tests/report/test_filter.py` treibt das Filter-JS über `node` + `jsdom` und **skippt
stillschweigend**, wenn beides fehlt — ein grüner Lauf heißt also nicht zwingend, dass
die Client-seitige Filterlogik geprüft wurde.

Die Vertragstests in `tests/format/` sind der Kern der Absicherung: Listen-Synchronität,
Rundlauf *schreiben → lesen* über beide Werkzeuge, stdlib-Wächter.

## Release / CI

**Eine** Workflow-Datei: [.github/workflows/release.yml](.github/workflows/release.yml).
Beide Werkzeuge werden **unabhängig versioniert**, das Tag-Präfix entscheidet:

| Tag | baut |
|---|---|
| `export-v0.3.2` | nur fritzexport |
| `report-v0.1.1` | nur fritzreport |

`workflow_dispatch` erlaubt zusätzlich einen manuellen Lauf mit Auswahl (`all`/`export`/`report`).

Release auslösen:
1. Version im jeweiligen Paket hochzählen — `fritzexport/__init__.py` **oder**
   `fritzreport/__init__.py`. `scripts/build.py` zieht die Version von dort; sie steht im
   Binary-Namen. Die Version in `pyproject.toml` ist die **Repo**-Version und wird bewusst
   nicht mitgezogen.
2. Commit, dann `git tag export-v0.3.2 && git push --tags`.

Kein CI-Lauf auf normalen Pushes/PRs — Tests laufen als Teil des Release-Builds; schlägt
der Test-Step fehl, gibt es kein Artefakt.

### Stolperfallen im Build

- **`--runtime-tmpdir .`** wird in [scripts/build.py](scripts/build.py) nur auf
  Nicht-Windows gesetzt: auf Windows knallt der Bootstrap-Extract im Drive-Root (`F:\`)
  wegen fehlender Permissions.
- **certifi** wird nur für fritzexport gebündelt (`--collect-data certifi`); ohne das ist
  TLS gegen Boxen mit selbstsigniertem Zertifikat kaputt. fritzreport braucht es nicht.
- Im Report-Build wird `requests` zwar installiert (die gemeinsame Testsuite braucht es),
  landet aber **nicht** im Binary — fritzreport importiert es nicht.

## Doku-Eigentum

Jede Aussage hat **genau einen** Ort — dasselbe Prinzip wie bei `fritzformat`:

| Datei | besitzt |
|---|---|
| [ANFORDERUNGEN.md](ANFORDERUNGEN.md) | Was die Werkzeuge leisten müssen, inkl. entfallener Anforderungen |
| [README.md](README.md) | Bedienung, Flags, Bundle-Format, Distribution |
| CLAUDE.md | Orientierung, Fallen, Konventionen (diese Datei) |
| [ressourcen/methode.md](ressourcen/methode.md) | Forensische Methodik + empirische Parser-Begründung |
| [ABDECKUNG.md](ABDECKUNG.md) | Welche Modelle/Firmware getestet sind — **erzeugt**, nie von Hand ändern |
| GitHub-Issues | Backlog — **ausschließlich** |

Drei Regeln, die verhindern, dass es wieder auseinanderläuft:

- **Backlog nur in Issues.** Keine „Offen / später"-Liste in einer Markdown-Datei; die
  hat keinen Zustand und wird nie geschlossen. Genau daran ist das frühere `CONCEPT.md`
  gescheitert.
- **Anforderungen nur in ANFORDERUNGEN.md**, mit stabilen IDs (A1, B7, E2 …). IDs werden
  nie wiederverwendet; Weggefallenes bleibt mit Status `entfällt` und Begründung stehen.
- **Kein Status in Prosa.** Testanzahlen, Versionen, „alles grün" veralten ab dem
  nächsten Commit. Was nirgends steht, kann nicht falsch werden.

`ABDECKUNG.md` ist die eine Ausnahme von „kein Status": Sie *ist* Status, wird deshalb
aber **erzeugt** (`scripts/abdeckung.py`) statt gepflegt. Nur mit dem vollständigen
Korpus neu erzeugen — läuft das Skript über ein Teilverzeichnis, schrumpft die Matrix
stillschweigend. Sie ist zur Veröffentlichung bestimmt und darf keine Seriennummern,
Aktenzeichen, Hostnamen oder Datensatzzahlen enthalten; `tests/format/test_abdeckung.py`
prüft beides mechanisch.

Dass sie zum Korpus passt, bewacht `test_abdeckung_ist_aktuell` in `test_golden.py`:
Kommt ein Abzug dazu, schlägt `pytest -m golden` fehl und nennt den Befehl zur
Neuerzeugung. Der Wächter greift nur dort, wo der Korpus liegt — in fremden Klonen
und auf CI-Runnern ist er deselektiert. Einen automatischen Trigger beim Build kann
es nicht geben: Der Generator braucht die Abzüge, und die sind bewusst nicht im Repo.

`tests/format/test_docs.py` erzwingt die gefährlichsten Punkte mechanisch: Die
Grade-Tabellen in README und ANFORDERUNGEN müssen `fritzreport.model.GRADE_LABEL`
wörtlich wiedergeben, Nachweise müssen auf existierende Tests zeigen.

## Konventionen

- Sprache von Doku, Logmeldungen, Fehlermeldungen: **Deutsch**.
- Code-Identifier, JSON-Feldnamen: **Englisch**.
- Forensik-Prinzip: **nichts auf der Box verändern**. Wo Lesen den Status ändert (z.B.
  TAM-Read-Flag), wird der Originalzustand per Restore-Aufruf wiederhergestellt und im
  Record dokumentiert.
- Abzüge und erzeugte Reports enthalten echte Forensikdaten und werden **nie** eingecheckt
  (siehe `.gitignore`).

## Library-Recherche

Erst **deepwiki** (nur public GitHub), Fallback **exa**.
