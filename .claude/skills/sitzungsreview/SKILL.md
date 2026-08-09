---
name: sitzungsreview
description: Projektwissen für die Review-Agenten des Sitzungsreviews — was die Testsuite bereits garantiert (und deshalb nicht zu prüfen ist), wem welche Doku-Aussage gehört, und die Fallen des Repos. Wird von jedem Agenten des Workflows gelesen, nicht direkt vom Nutzer aufgerufen.
---

# Prüfwissen für das Sitzungsreview

Diese Datei ist für die **Agenten** des Workflows `sitzungsreview`, nicht für den
direkten Gebrauch. Sie ist das, was `fritzformat` für die Werkzeuge ist: **eine**
Wahrheit, von allen gelesen. Ohne sie trüge jeder Agenten-Prompt dieselben Projektregeln
noch einmal — genau die Vervielfachung, gegen die dieses Repo an anderer Stelle bereits
angetreten ist.

## Belegpflicht — gilt für jeden Befund

Ein Befund nennt **Datei und Zeile** oder ein **wörtliches Zitat**. Ohne Beleg wird er
verworfen, nicht nachrecherchiert.

Der Grund ist nicht Formalismus: Der Nutzer geht jedem Befund nach. Ein unbelegter
Befund kostet ihn die Zeit, die der Agent sich gespart hat.

**Keine Vermutungen als Befund.** „Könnte problematisch sein" ist kein Befund. Entweder
zeigen, dass es bricht — oder weglassen.

## Was bereits mechanisch garantiert ist — NICHT prüfen

206 Tests laufen offline (`python3 -m pytest`). Die folgenden Punkte sind darüber
abgedeckt. Sie zu melden ist doppelte Arbeit und verwässert den Bericht:

| Datei | Garantiert |
|---|---|
| `tests/format/test_docs.py` | Grade-Tabellen in ANFORDERUNGEN.md **und** README.md geben `fritzreport.model.GRADE_LABEL` wörtlich wieder · jeder Backtick-Testname in der Nachweisspalte existiert als Funktion · Status ∈ {erfüllt, erfüllt angepasst, offen, entfällt} · `offen` nennt eine Issue-Nummer · `entfällt` nennt eine Begründung · Anforderungs-IDs sind eindeutig · sechs wörtliche KI-Zusagen in README stehen |
| `tests/format/test_stdlib_only.py` | `fritzformat`/`fritzreport` ohne Fremdpakete und ohne netzfähige stdlib-Module (Ausnahme `webbrowser`) · `fritzexport` kennt nur erlaubte Hosts · SSDP-TTL ≤ 4 · mit Gegenproben, die den Wächter scharf halten |
| `tests/format/test_abdeckung.py` | Erzeugte Matrix und verschickter Auszug enthalten keine Serials, MACs, Aktenzeichen, Hostnamen, IPs, Zeitstempel oder Zählerstände |
| `tests/format/test_contract.py` | `EXTRACTORS` == `JSON_TYPES` · Bundle-Rundlauf schreiben→lesen über alle Datenarten · Fallkopf · Namensstamm Abzug↔Report · Sicherungszeitraum · Uhrzeit-Klammern |

**Zwei stille Löcher** — hier ist ein grüner Lauf *kein* Beleg:

- `tests/report/test_filter.py` überspringt sich wortlos, wenn `node` und `jsdom` fehlen.
  Die Client-seitige Filterlogik ist damit faktisch ungeprüft.
- `test_abdeckung_ist_aktuell` läuft nur mit `-m golden`. `ABDECKUNG.md` kann veraltet
  sein, ohne dass der normale Lauf etwas merkt.

## Wo die Tests blind sind — hier liegt der Auftrag

1. **CLAUDE.md prüft kein einziger Test.** Auch ihre Grade-Definition nicht: Sie steht
   dort in **Prosa** (Zeile ~90), und `test_docs.py` matcht nur Tabellenzeilen. Weicht
   sie von `GRADE_LABEL` ab, fällt es niemandem auf.
2. **„Kein Status in Prosa"** — eigene Regel des Repos, ohne Wächter.
3. **methode.md und SECURITY.md** haben null mechanische Abdeckung.
4. **Nachweise werden nur auf Existenz geprüft.** Dass ein in ANFORDERUNGEN.md genannter
   Test die Anforderung *inhaltlich* belegt, prüft niemand.
5. **Ein grüner Test, der nichts prüft**, besteht jeden Wächter — und erzeugt falsche
   Sicherheit. Das ist real vorgekommen: Ein Test hieß
   `test_anfrage_steht_vor_dem_request`, sammelte die beiden zu vergleichenden Ereignisse
   aber in getrennten Kanälen und verglich ihre Reihenfolge nie. Grün, ohne die
   Behauptung seines Namens je zu prüfen.

## Doku-Eigentum — jede Aussage hat genau einen Ort

| Datei | besitzt |
|---|---|
| `ANFORDERUNGEN.md` | Was die Werkzeuge leisten müssen, mit stabilen IDs (A1, B7 …), inkl. entfallener Anforderungen |
| `README.md` | Bedienung, Flags, Bundle-Format, Distribution |
| `CLAUDE.md` | Orientierung, Fallen, Konventionen |
| `methode.md` | **Externes Methodenpapier** — Zusammenfassung des nicht öffentlichen Methodenpapiers v1.0. Es trägt den Belegtheitsgrad **D2** |
| `ABDECKUNG.md` | **Erzeugt** (`scripts/abdeckung.py`), nie von Hand geändert |
| `SECURITY.md` | Meldeweg für Sicherheitslücken |
| GitHub-Issues | Backlog — **ausschließlich** |

**methode.md ist der empfindlichste Fall.** Sie fasst ein externes, validiertes
Methodenpapier zusammen („Bei Abweichungen gilt das Methodenpapier"); validiert ist dort
FRITZ!OS 8.20 auf HW 259. Eigene Messreihen dort einzutragen liehe ihnen fälschlich diese
Autorität — sie gehören in Modul-Docstrings und benannte Tests. Ein Befund dieser Art
wiegt schwer.

## Fallen des Repos

- **`fritzformat` ist die einzige Wahrheit über das Bundle-Format.** Dateinamen,
  Hüllformat, Sidecars, Marker. Wird etwas davon in `fritzexport` oder `fritzreport`
  nachgebaut, ist das ein Befund — dieses Wissen lag schon einmal vierfach vor.
- **Kein Status in Prosa.** Testanzahlen, Versionsnummern, „alles grün", „funktioniert
  jetzt", „vollständig" veralten mit dem nächsten Commit. Einzige Ausnahme:
  `ABDECKUNG.md`, weil erzeugt.
- **Backlog nur in Issues.** Keine „Offen/später"-Liste in einer Markdown-Datei. Genau
  daran ist das frühere `CONCEPT.md` gescheitert.
- **`fritzreport` und `fritzformat` bleiben stdlib-only** und benutzen **kein netzfähiges
  Modul** — auch keines aus der Standardbibliothek. Nach außen ist zugesagt, dass das
  Werkzeug nichts sendet.
- **Zeitversatz wird nie im Extractor gerechnet.** Beide Quellen sind sekundengenau; eine
  Differenz `box − referenz` ist deshalb systematisch verschoben. Die Klammer bildet
  `fritzreport` einmal für beide Quellen.
- **Die `services`-Vergleichsbasis wird eingesammelt, nie gepflegt.** Eine zweite Liste
  veraltete still.
- **Sprache**: Doku, Log- und Fehlermeldungen **Deutsch**; Code-Identifier und
  JSON-Feldnamen **Englisch**.
- **Forensik-Prinzip**: nichts auf der Box verändern. Wo Lesen den Status ändert, wird
  der Originalzustand wiederhergestellt und im Record dokumentiert.
- **Nie Forensikdaten einchecken** — Abzüge und erzeugte Reports gehören nicht ins Repo.

## Schwere eines Befunds

| Stufe | Wann |
|---|---|
| `hoch` | Falsche Aussage im erzeugten Bericht · gebrochene Zusage nach außen (Netzfreiheit, Datenschutz, Grade-Bedeutung) · Test, der grün ist und nichts prüft · Datenverlust |
| `mittel` | Doppelte Logik · Docstring widerspricht Code · Doku-Widerspruch ohne Außenwirkung · fehlende Grenzfallbehandlung |
| `niedrig` | Stil, Benennung, Formulierung, Konvention |

Im Zweifel **niedriger** einstufen. Der Bericht deckelt die oberen Ränge hart; wer alles
`hoch` nennt, verdrängt echte Funde.
