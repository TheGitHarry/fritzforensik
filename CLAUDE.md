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

Dieselbe Datei hält eine zweite, schärfere Zusage fest: `fritzreport` und `fritzformat`
dürfen **kein netzfähiges Modul** verwenden — auch keines aus der Standardbibliothek.
Der Fremdpaket-Wächter allein genügt dafür nicht, denn `sys.stdlib_module_names`
enthält `socket`, `urllib` und Verwandte; ein Netzzugriff darüber liefe unbemerkt durch.
README und ABDECKUNG.md sagen nach außen zu, dass das Werkzeug nichts sendet — diese
Zusage darf nicht ohne Not aufgeweicht werden. Ausgenommen ist `webbrowser`
(`--open` öffnet den fertigen Report lokal als `file://`, das sendet nichts).

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
- **`services` ist der Selbstprüfer**: `extractors/services.py` liest das
  TR-064-Dienstverzeichnis der Box (`/tr64desc.xml`) und hält es gegen die Dienste, die
  die übrigen Extractoren aufrufen. Was mit `genutzt: false` erscheint, ist keine
  Fehlfunktion, sondern die Kandidatenliste für künftige Extractoren. Die Vergleichsbasis
  wird aus den `*_SERVICE`-Modulkonstanten **eingesammelt**, nie gepflegt — eine zweite
  Liste veraltete still, sobald jemand einen Extractor ergänzt.
  Das Verzeichnis ist **nur beim Abzug** erfassbar: Es steht in keiner anderen
  Bundle-Datei, auch nicht in den Supportdaten (dort tauchen nur die Dienste auf, die
  fritzexport selbst aufgerufen hat).

- **Zeitmarken statt Rechnung**: `boxtime` (TR-064 `Time:1`) und `supportdata` holen
  beide eine Zeitangabe der Box und klammern ihren Abruf in zwei Markerzeilen
  (`UHRZEIT ANFRAGE`/`ANTWORT` je Quelle, siehe `fritzformat/sessionlog.py`). Den
  Versatz rechnet **keiner der beiden** — das tut `fritzreport` einmal für beide
  Quellen. Wer hier eine Differenz `box − referenz` einbaut, baut einen Fehler ein:
  Beide Quellen sind sekundengenau, die Differenz ist deshalb systematisch verschoben.

## Wie fritzreport arbeitet

`{bundle,model,supportdata,render}.py`. `bundle.py` lädt und **verifiziert** jede Datei
gegen ihre Sidecar und stellt je Datensatz die Fundstelle bereit (Zeilennummer + wörtlicher
Auszug). `supportdata.py` parst die Roh-Supportdaten (Sektionen, 802.11-Logs) — der Export
*holt* diese Dateien nur, er parst sie nicht; hier gibt es keine doppelte Logik.

`_resolve_clock_offset` (in `bundle.py`, neben `_resolve_secured_span`) bildet den
**Versatz der Box-Uhr** — aus Box-Zeit und Sitzungslog-Marken, für beide Quellen
gleich. Zwei Fallen, die dort im Docstring belegt sind:

- Die Klammer der Supportdaten ist **einseitig**: Ihr Kopf entsteht am Anfang der
  Erzeugung, die untere Schranke enthält also nur die Übertragungsdauer. Sie wird
  deshalb nie als Messwert gezeigt — „−189 s" läse sich wie ein Rückstand, den
  niemand gemessen hat. Bei TR-064 (Round-Trip) tragen beide Schranken.
- Rückwirkend ist **nur `standard`** auswertbar. Bei `enhanced` liegt ohne eigene
  Marker die Wartezeit auf den Tastendruck mit in der Klammer (7490: 595 s).

**Belegtheits-Grade** (kombinierbar): **D1** plausibel innerhalb der Rohdaten · **D2** durch
eigene forensische Tests verifiziert ([methode.md](methode.md)) ·
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
| [methode.md](methode.md) | Forensische Methodik + empirische Parser-Begründung |
| [ABDECKUNG.md](ABDECKUNG.md) | Welche Modelle/Firmware getestet sind — **erzeugt**, nie von Hand ändern |
| [SECURITY.md](SECURITY.md) | Meldeweg für Sicherheitslücken, und was ausdrücklich keine ist |
| [LICENSE](LICENSE) | Apache-2.0 |
| GitHub-Issues | Backlog — **ausschließlich** |

Alle Doku liegt im **Stammverzeichnis**, bewusst ohne `docs/`-Unterordner: Es sind
wenige Dateien, und README/LICENSE/SECURITY/CLAUDE müssen ohnehin dort liegen, damit
GitHub und Claude Code sie finden. Ein Unterordner hätte nur einzelne davon versteckt.

Drei Regeln, die verhindern, dass es wieder auseinanderläuft:

- **Backlog nur in Issues.** Keine „Offen / später"-Liste in einer Markdown-Datei; die
  hat keinen Zustand und wird nie geschlossen. Genau daran ist das frühere `CONCEPT.md`
  gescheitert. Umgekehrt gilt *nicht*, dass jedes Issue Backlog wäre: Meldungen mit dem
  Label **`abdeckung`** sind eingegangene Beiträge zur Matrix, keine offenen Aufgaben.
  Wer den Backlog liest, filtert sie heraus:
  `gh issue list --state open --search "-label:abdeckung"`.
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

Für einen **neuen Abzug** gibt es den Skill `neuer-abzug` — er führt den ganzen Ablauf
(entpacken → Integrität → Report → Golden-Tests → Matrix → KORPUS.md → Bericht) samt
der Fallen, die dabei schon aufgetreten sind.

**Beiträge von außen** brauchen kein Bündel: Wer das Repo klont, erzeugt mit
`scripts/abdeckung.py <verzeichnis> --json > auszug.json` einen datenfreien Auszug
(nur Modell/Revision/Firmware und je Datenart ob gefüllt). Hier wird er per
`--beitrag=auszug.json` in die Gesamtmatrix aufgenommen — beliebig oft wiederholbar.
**Achtung:** Der Generator kennt nur, was er beim Aufruf bekommt. Wird er ohne die
eingegangenen Auszüge gestartet, fallen fremde Geräte wieder aus der Matrix. Die
Auszüge deshalb aufbewahren (die Issues mit Label `abdeckung` sind das Archiv).
Der Auszug wird **verschickt**: `tests/format/test_abdeckung.py` prüft gegen ein
präpariertes Bündel, dass er nichts Identifizierendes und keine Zählerstände enthält.

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
