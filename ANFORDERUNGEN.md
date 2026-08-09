# Anforderungen

Was `fritzexport` und `fritzreport` leisten müssen — der fachliche Vertrag, gegen den
geprüft wird. Dieses Dokument ändert sich nur, wenn sich die **forensische
Anforderung** ändert, nicht wenn sich der Code ändert.

**Kein Backlog hier.** Offene Punkte stehen ausschließlich in den GitHub-Issues; eine
Zeile mit Status `offen` nennt die Issue-Nummer.
**Keine Statusangaben in Prosa** (Testzahlen, Versionen, „grün") — die veralten sofort.

## Herkunft

Die IDs A1–G4 stammen aus dem ursprünglichen **ANFORDERUNGSKATALOG.md**, geschrieben
für den serverseitigen `it-forensic-automat` (Worker-Pipeline, Datenbank, ODT/PDF).
Er liegt außerhalb dieses Repos im archivierten `legacy_report`-Klon unter
`_material/poc/` und ist **nicht mehr maßgeblich** — maßgeblich ist diese Datei.

Die Werkzeuge hier sind **eigenständige Feldwerkzeuge** ohne Server, Datenbank und
Job-Verwaltung. Anforderungen, die daran hängen, tragen Status `entfällt` mit
Begründung (siehe [Abweichungen](#abweichungen-vom-ursprungskatalog)).

## Regeln für dieses Dokument

- **Eine Anforderung wird nie gelöscht.** Fällt sie weg, bekommt sie Status
  `entfällt` **mit Begründung**. Eine verschwundene Anforderung ist die Art, wie
  Kataloge verrotten — in fünf Jahren soll die Frage „warum eigentlich nicht?" eine
  Antwort finden, kein Loch.
- **IDs werden nie wiederverwendet.** Neues kommt hinten dran (H1, H2 …).
- **Statuswerte — genau diese fünf:**

| Status | Bedeutung |
|---|---|
| `erfüllt` | Umgesetzt wie formuliert |
| `erfüllt, angepasst` | Umgesetzt, aber abweichend — Abweichung ist dokumentiert |
| `offen` | Noch nicht umgesetzt — **muss eine Issue-Nummer nennen** |
| `entfällt` | Gilt für diese Werkzeuge nicht — **muss eine Begründung nennen** |
| `ersetzt durch <ID>` | Von einer anderen Anforderung abgelöst |

---

## A. Datenumfang

| ID | Anforderung | Status | Nachweis |
|---|---|---|---|
| A1 | Report enthält **alle Daten** eines Abzugs; keine Vorabfilterung bei der Erzeugung | erfüllt | — |
| A2 | Rohdaten 1:1 abgebildet (jede JSON-Zeile, jeder relevante Supportdaten-Block) plus abgeleitete Aggregate | erfüllt | `test_provenance_exact` |
| A3 | Report offline eigenständig lesbar — keine externen Ressourcen (kein CDN, kein Nachladen) | erfüllt | — |

## B. Filter im Report

| ID | Anforderung | Status | Nachweis |
|---|---|---|---|
| B1 | Filter werden **nach** der Report-Erstellung im Betrachter gesetzt, nicht vorab bei der Erzeugung | erfüllt | `test_filter_logic_in_browser` |
| B2 | Filter für MAC-Adresse, Zeitraum, Access Point, Gerätename, Telefonnummer | erfüllt | `test_filter_logic_in_browser` |
| B3 | Filter wirken über alle Sektionen konsistent (eine MAC filtert Hosts, Mesh, Wifi, Events gemeinsam) | erfüllt | `test_filter_logic_in_browser` |
| B4 | Aktive Filter oben sichtbar, Rückmeldung „X von Y Zeilen ausgeblendet" | erfüllt | — |
| B5 | Filter zurücksetzbar | erfüllt | — |
| B6 | Zusätzlich Filter nach Belegtheits-Grad (siehe D) | erfüllt | — |
| B7 | AP-Dropdown enthält **ausschließlich echte Access Points** (`is_meshed == true`), nicht alle Geräte im Netz | erfüllt | — |

## C. Ausdruck

| ID | Anforderung | Status | Nachweis |
|---|---|---|---|
| C1 | Gefilterte Sicht per Browser-Druck (Ctrl+P) ausdruckbar | erfüllt | — |
| C2 | Ausdruck erkennbar als **gefilterte Sicht** gekennzeichnet: Kopf mit aktiven Filterkriterien und Bezug zum Ur-Report; nicht als „der Report" ausgewiesen | erfüllt, angepasst | `test_kein_irrefuehrender_report_hash_im_dokument` · siehe [Abweichungen](#abweichungen-vom-ursprungskatalog) |

## D. Belegtheits-Grade

**Achtung — das Schema wurde umnummeriert.** Der Ursprungskatalog kannte vier Grade,
dieses Werkzeug hat drei. Die Bedeutungen haben sich dabei **verschoben**:

```
alt D1 (aus signierter Rohdatei)             → kein Badge   (trivial: alles kommt aus Rohdaten)
alt D2 (innerhalb Rohdaten vertrauenswürdig) → D1
alt D3 (durch eigene forensische Versuche)   → D2   ← HIER liegt die Verwechslungsgefahr
alt D4 (abgeleitet / Interpretation)         → D3
```

> **Ein Dokument, das „D3 = durch eigene Versuche belegt" sagt, folgt dem alten
> Schema und ist auf Reports dieses Werkzeugs nicht anwendbar.** Dort bedeutet D3
> „abgeleitet/Interpretation" — also das Gegenteil an Belastbarkeit. Reports dieses
> Werkzeugs weisen ihr Schema selbst aus (Sektion „Belegtheits-Legende").

**Gültiges Schema (v2, 3 Grade, kombinierbar).** Die Bedeutungen sind im Code in
`fritzreport/model.py` (`GRADE_LABEL`) hinterlegt und werden von dort in den Report
gerendert — ein Vertragstest hält diese Tabelle damit synchron:

| Grad | Bedeutung |
|---|---|
| D1 | Plausibel innerhalb Rohdaten |
| D2 | Durch eigene forensische Tests verifiziert |
| D3 | Abgeleitet / Interpretation |

Zeile ohne Badge = reine Rohdaten-Wiedergabe.
Verbindungsnachweise: methode.md-Parser → **D1+D2**, 802.11-Log-Parser → **D1+D3**.

| ID | Anforderung | Status | Nachweis |
|---|---|---|---|
| D-a | Grade sind pro Datenpunkt vergeben und **kombinierbar** | erfüllt | `test_grades_scheme` |
| D-b | Grade werden bei der Auswertung bestimmt, nicht im Betrachter | erfüllt | `test_support_both_parsers_and_grades` |
| D-c | **Keine** Anmerkungs-/Kommentarfunktion für den Sachverständigen im Report | erfüllt | — |
| D-d | Grade sind einheitlich über alle Auswertungswege vergeben | entfällt | Bezog sich auf „alle Worker" des Automaten; hier gibt es nur ein Werkzeug |

## E. Forensische Integrität

| ID | Anforderung | Status | Nachweis |
|---|---|---|---|
| E1a | HTML-Report selbst SHA256-signiert | erfüllt | `test_report_sidecar_written_and_verifies`, `test_report_sidecar_detects_tampering` |
| E1b | Report in der Datenbank als Beweismittel registriert | entfällt | Eigenständiges Feldwerkzeug ohne Datenbank; die Sidecar tritt an diese Stelle |
| E2 | Filter/Druck manipulieren nur die Anzeige — Ur-Report bleibt hash-stabil | erfüllt | `test_report_sidecar_written_and_verifies` |
| E3 | Report-Kopf enthält: Erstellungs-Zeitstempel, Werkzeug-Versionen, Case-ID, Chain-of-Custody-Tabelle aller Quelldateien mit SHA256 | erfüllt, angepasst | siehe [Abweichungen](#abweichungen-vom-ursprungskatalog) |
| E3b | Job-ID im Report-Kopf | entfällt | Keine Job-Verwaltung; an ihre Stelle treten Case-ID und Asservat-/Item-ID |
| E4 | HTML-Report zusätzlich zu ODT/PDF, ersetzt sie nicht | entfällt | Es gibt keine ODT/PDF-Erzeugung; der HTML-Report ist das Ergebnis. Langzeitarchivierung ist Sache des einsetzenden Hauses |

## F. Struktur

| ID | Anforderung | Status | Nachweis |
|---|---|---|---|
| F1 | Ein Report pro Abzug (zwei Abzüge → zwei Reports, kein fallübergreifender Report) | erfüllt | — |
| F2 | Sektionen einzeln auf-/zuklappbar, im Grundzustand **alle zugeklappt**; TOC-Klick klappt auf und springt | erfüllt | — |
| F3 | Sektions-Kopfzeilen zeigen die Trefferzahl auch im zugeklappten Zustand | erfüllt | — |

## G. Herkunftsreferenz

| ID | Anforderung | Status | Nachweis |
|---|---|---|---|
| G1 | Jede Datenzeile aufklappbar, zeigt Quelldatei, deren SHA256, Fundstelle und den Roh-Datensatz | erfüllt | `test_provenance_exact` |
| G2 | Quelldatei-Name und SHA256 per Klick kopierbar | erfüllt | — |
| G3 | Im zugeklappten Zustand bleibt die Zeile schmal — die Referenz drängt sich nicht auf | erfüllt | — |
| G4 | ZIP-Auslieferung der Rohdaten neben dem Report | entfällt | Bedarf durch A2 (Rohdaten 1:1 im Report), G1/G2 (zeichengenaue Herkunft je Datensatz) und die Chain-of-Custody-Tabelle gedeckt; das Bundle-Verzeichnis ist selbst die Rohdatenauslieferung. Siehe #11 |

## H. Feldeinsatz (neu, nicht aus dem Ursprungskatalog)

Anforderungen, die erst durch den eigenständigen Feldeinsatz entstanden sind.

| ID | Anforderung | Status | Nachweis |
|---|---|---|---|
| H1 | Bundle-Auto-Discovery: genau eines → direkt nehmen, mehrere → Auswahl | erfüllt | — |
| H2 | Sprechender Ausgabename aus Fallkopf und Gerät | erfüllt | — |
| H6 | Export-Verzeichnis und Report-Name teilen einen Namensstamm, sodass die Zusammengehörigkeit ohne Nachschlagen erkennbar ist | erfüllt | `test_stamm_von_abzug_und_report_ist_identisch`, `test_verzeichnis_bekommt_fallkopf_namen` |
| H7 | Ein zweiter Abzug desselben Asservats überschreibt den Report des ersten nicht | erfüllt | `test_zwei_reports_kollidieren_nicht` |
| H3 | Fallkopf einmal erfassen, mit dem Bundle transportieren, im Report vorbelegen | erfüllt | `test_fallkopf_rundlauf`, `test_fallkopf_belegt_report_kopf_vor` |
| H4 | Mehrere Objekte am Stück abarbeiten, ohne Neustart je Objekt | offen | #1, #3 |
| H5 | Nichts auf der Box verändern; wo Lesen den Status ändert, Originalzustand wiederherstellen und dokumentieren | erfüllt | — |
| H8 | Der Report weist den **Sicherungszeitraum** aus (erster bis letzter Datenabruf), nicht einen einzelnen Zeitpunkt; ist er abgeleitet statt protokolliert, ist das erkennbar | erfüllt | `test_report_zeigt_gerechneten_zeitraum_mit_d1`, `test_report_zeigt_protokollierten_zeitraum_ohne_badge` |
| H9 | Die **Uhr der Box** wird gegen eine Referenzzeit abgeglichen und der Versatz mit seiner Messunsicherheit ausgewiesen — auch der Befund „kein Versatz nachweisbar" wird benannt. Wo eine Schranke nur die Übertragungsdauer misst, wird sie nicht als Messwert gezeigt | erfüllt | `test_supportdata_zeigt_keine_untere_schranke`, `test_zeitversatz_zeile_sagt_genau_das_gemessene`, `test_klammer_um_die_null_benennt_den_befund`, `test_rueckwaerts_laufende_klammer_wird_verworfen`, `test_box_uhr_wird_im_altbestand_geprueft` |

---

## Nicht Teil dieser Anforderungen

Übernommen aus dem Ursprungskatalog, gilt unverändert:

- Serverseitige Filter-Round-Trips
- Nachträgliche Sachverständigen-Anmerkungen im Report
- PDF/A-Erzeugung aus gefilterter Sicht (Browser-Druck genügt)
- Fallübergreifende Reports (mehrere Abzüge in einem Report)

---

## Abweichungen vom Ursprungskatalog

**Kontextwechsel.** Der Katalog beschrieb einen HTML-Report als Zusatzausgabe des
`it-forensic-automat`: Ein Worker erzeugte die Daten samt Belegtheits-Graden, eine
Middleware legte den Report ab, eine Datenbank registrierte ihn, ODT/PDF liefen
parallel weiter. Nichts davon existiert hier. `fritzexport` und `fritzreport` sind
Einzelbinaries für den USB-Stick, ohne Netz, ohne Datenbank, ohne Job-Verwaltung.

Daraus folgen die Umformulierungen:

- **A1, B1** — „keine Vorabfilterung durch den *Worker*" → „bei der *Erzeugung*".
  Inhaltlich unverändert: Gefiltert wird nachträglich im Betrachter, nie vorab.
- **D-b** — die Gradzuweisung erfolgt bei der Auswertung (`fritzreport/supportdata.py`)
  statt „im Worker". Entscheidend bleibt: nicht im Betrachter-UI.
- **D-d** — „einheitlich für alle Worker" ist gegenstandslos, es gibt nur ein Werkzeug.
- **E1** — aufgeteilt: Die SHA256-Signatur des Reports (E1a) ist erfüllt, die
  Datenbank-Registrierung (E1b) entfällt mangels Datenbank. Die Sidecar neben dem
  Report übernimmt deren Funktion: Sie ist mit `sha256sum -c` prüfbar, auch ohne
  unsere Werkzeuge.
- **E3b** — die Job-ID entfällt; Case-ID und Asservat-/Item-ID treten an ihre Stelle.
- **E4** — ohne ODT/PDF-Erzeugung gegenstandslos.

**C2 und E3 — der Hash steht in der Sidecar, nicht im Report (#12, erledigt).**
Beide verlangen den „Hash des Ur-Reports" im Kopf bzw. im Druckbanner. Das ist so
nicht erfüllbar: **Ein Dokument kann seinen eigenen Hash nicht enthalten** — der Wert
verändert das Dokument und damit sich selbst.

Der Report wies zeitweise einen Wert unter diesem Namen aus, tatsächlich ein SHA256
über *Bundle-Metadaten* (Extraktionszeitpunkt + Host). Wer ihn mit
`sha256sum report.html` prüfte, erhielt einen anderen — genau die Art Abweichung, die
in einer Hauptverhandlung erklärungsbedürftig wird. Der Wert ist entfernt; er trug
zudem nichts bei, was Host-URL, Sicherungszeitraum und Chain-of-Custody-Tabelle nicht
schon zeigen.

**Stattdessen:** Der echte Digest liegt seit E1a in der `.sha256`-Sidecar neben dem
Report, mit `sha256sum -c` prüfbar. Report und Druckbanner **verweisen** darauf,
statt einen Wert zu behaupten. Die Zuordnung eines Ausdrucks zum Abzug leistet im
Banner der **Sicherungszeitraum** zusammen mit dem Fallkopf.
