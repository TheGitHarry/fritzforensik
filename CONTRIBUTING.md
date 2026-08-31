# Beiträge

Das hier ist ein Feldprojekt ohne Bereitschaftsdienst. Beiträge sind willkommen,
eine Antwort kann ein paar Tage dauern.

## Was am meisten hilft

Das Projekt kennt nur die Geräte, die es gesehen hat. Welche Modelle und
FRITZ!OS-Stände das sind und wo die größten Lücken liegen, steht in
[ABDECKUNG.md](ABDECKUNG.md).

Sie können die Matrix erweitern, **ohne uns Ihre Daten zu geben**. Aus einem
eigenen Abzug erzeugen Sie einen datenfreien Auszug:

```bash
python3 scripts/abdeckung.py <verzeichnis-mit-bundles> --json > auszug.json
```

Darin stehen Modell, Revision, Firmware und je Datenart, ob sie gefüllt war —
keine Seriennummern, keine Aktenzeichen, keine Hostnamen, keine Zählerstände.
Dass das so bleibt, prüft `tests/format/test_abdeckung.py` mechanisch. Den Auszug
hängen Sie an ein Issue nach der Vorlage „Abdeckung melden"; er wird dann in die
Gesamtmatrix aufgenommen.

Ein vollständiges Bundle brauchen wir dafür nicht. Falls Sie eines
bereitstellen wollen, lesen Sie bitte vorher
[ABDECKUNG.md](ABDECKUNG.md#bevor-sie-einen-abzug-bereitstellen): Die Entwicklung
ist KI-gestützt, ein bereitgestellter Abzug wird also von einem KI-Assistenten
verarbeitet und damit an dessen Anbieter übermittelt. Abzüge aus einem Testlabor
sind deshalb der bessere Weg als Abzüge aus einem echten Fall.

## Fehler und Wünsche

Als [GitHub-Issue](https://github.com/TheGitHarry/fritzforensik/issues), formlos.
Der offene Stand des Projekts steht ausschließlich dort — es gibt bewusst keine
zweite Liste in einer Markdown-Datei.

Hilfreich sind Modell und FRITZ!OS-Stand der Box, die Version des Werkzeugs
(`--version`) und der Ausschnitt aus dem Sitzungslog, der zum Fehler gehört.
Bitte keine vollständigen Bundles oder Reports anhängen, die enthalten
personenbezogene Daten.

Sicherheitslücken nicht als Issue, sondern auf dem Weg in
[SECURITY.md](SECURITY.md). Dort steht auch, welche Eigenschaften wie eine Lücke
aussehen, aber Zweck des Werkzeugs sind.

## Code

Vor einem Pull Request:

```bash
python3 -m pytest
```

Die Suite läuft offline und ohne Box. Wenn Sie an der Filterlogik des Reports
arbeiten, einmalig `npm ci` — sonst überspringt `tests/report/test_filter.py`
still, und der grüne Lauf sagt über die Filter nichts aus.

Drei Zusagen halten die Werkzeuge zusammen, und Tests wachen über sie:

- **Das Bundle-Format lebt in `fritzformat/`.** Dateinamen, Hüllformat und
  Sidecars stehen dort einmal und werden von beiden Seiten benutzt. Nie in einem
  der Werkzeuge nachbauen.
- **`fritzreport` und `fritzformat` sind stdlib-only und netzfrei** — kein
  Fremdpaket, und auch kein netzfähiges Modul aus der Standardbibliothek. README
  und ABDECKUNG.md sagen nach außen zu, dass das Werkzeug nichts sendet.
- **Auf der Box wird nichts verändert.** Wo Lesen den Status ändert, etwa das
  Read-Flag des Anrufbeantworters, stellt der Extractor den Originalzustand
  wieder her und schreibt das in den Record.

Doku, Log- und Fehlermeldungen auf Deutsch; Bezeichner im Code, JSON-Feldnamen
und Commit-Messages auf Englisch. Commits im Conventional-Commit-Stil (`feat:`,
`fix:`, `docs:`, `refactor:`), mit der Issue-Nummer in Klammern, wo eine
dahintersteht.

Abzüge und erzeugte Reports gehören nie ins Repository. Die `.gitignore` deckt
die üblichen Pfade ab, verlassen Sie sich aber nicht darauf.

## Lizenz

Mit einem Pull Request stellen Sie Ihren Beitrag unter dieselbe Lizenz wie das
Projekt: Apache-2.0, siehe [LICENSE](LICENSE).
