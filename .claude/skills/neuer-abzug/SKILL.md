---
name: neuer-abzug
description: Einen neuen FRITZ!Box-Abzug in den Testkorpus aufnehmen — entpacken, Integrität prüfen, Report rendern, ABDECKUNG.md und KORPUS.md fortschreiben, Lücken und Auffälligkeiten berichten. Nutzen, sobald der Nutzer sagt, er habe einen Abzug/Export/ein Bundle hochgeladen oder bereitgestellt.
---

# Neuen Abzug in den Korpus aufnehmen

Der Ablauf ist **sequenziell mit Prüfpunkten**. Nicht abkürzen: Jeder Schritt
kann etwas zutage fördern, das den nächsten ändert.

**Am Ende wird berichtet, nicht committet.** Die Freigabe holt der Nutzer.
Gepusht wird nie ohne ausdrückliches Wort.

## 0. Wo die Dinge liegen

| Ort | Rolle |
|---|---|
| `~/testdata/export/` | **Eingang** — hierhin lädt der Nutzer ZIPs und Verzeichnisse |
| `~/testdata/_work/` | **Korpus** — nur was hier liegt, läuft in `pytest -m golden` |
| `~/testdata/KORPUS.md` | private Inventarliste, **außerhalb des Repos** (Serials, Aktenzeichen) |
| `ABDECKUNG.md` (im Repo) | öffentliche Matrix, **erzeugt**, ohne identifizierende Daten |

Der Eingang ist nicht der Korpus. Ein Abzug, der nur in `export/` liegt, wird
von keinem Test gesehen — das ist der häufigste stille Fehler.

## 1. Finden, was neu ist

```bash
ls -lt ~/testdata/export/ | head -20
ls -d ~/testdata/_work/*/
```

Zeitstempel vergleichen. Bei Unklarheit **fragen**, statt zu raten, welche Datei
gemeint ist.

## 2. Entpacken nach `_work`

```bash
cd ~/testdata/_work && unzip -oq ~/testdata/export/<datei>.zip
```

Liegt der Abzug als Verzeichnis vor: `cp -r` statt `mv` — der Eingang bleibt
unangetastet.

Danach prüfen, dass es als Bundle erkannt wird:

```bash
python3 -c "
import sys; sys.path.insert(0,'.')
from fritzreport.cli import is_bundle
from pathlib import Path
p = Path.home()/'testdata/_work/<name>'
print('is_bundle:', is_bundle(p))
"
```

`False` heißt: unvollständig entpackt oder kein Bundle. Nicht weitermachen.

## 3. Integrität prüfen und **ausdrücklich berichten**

Bei forensischem Material ist das die Angabe, die zählt — sie darf nicht im
grünen Testlauf untergehen.

```bash
python3 -c "
import sys; sys.path.insert(0,'.')
from collections import Counter
from fritzreport.bundle import load_bundle
from pathlib import Path
b = load_bundle(Path.home()/'testdata/_work/<name>')
print(dict(Counter(e.status for e in b.coc)), '| Dateien:', len(b.coc))
print('Abweichungen:', [e.file for e in b.coc if e.status == 'mismatch'])
"
```

Erwartet: alle `ok`. Ein einziges `mismatch` ist ein **Stopp** — melden, nicht
weiterverarbeiten. `no_sidecar` bei einzelnen Dateien kommt vor und ist zu
erwähnen, aber kein Abbruchgrund.

Im Bericht die konkreten Zahlen nennen: „34 Dateien, 34 Sidecars geprüft, 0
Abweichungen."

## 4. Merkmale auslesen

Modell, Firmware und Seriennummer stehen im Kopf der Supportdaten:

```bash
grep -m4 -E "^(HWRevision|HWSubRevision|SerialNumber|firmware_info)\b" \
  ~/testdata/_work/<name>/supportdata_standard_*.txt | tr '\t' '='
```

(`-m4`, nicht `-m1`: `grep` zählt Treffer insgesamt, nicht je Alternative —
mit `-m1` käme nur `HWRevision` und die übrigen drei Felder fehlten stillschweigend.)

HWRevision identifiziert das Modell: **185**=7490, **226**=7590, **256**=7530 AX,
**285**=7690. Bei unbekannter Revision `HWREV_MODELL` in
`scripts/abdeckung.py` ergänzen.

## 5. Auffälligkeiten prüfen — hier liegt der eigentliche Wert

Drei Dinge, die schon aufgetreten sind und leicht übersehen werden:

- **Dieselbe Box wie ein früherer Abzug?** Drei der 7690-Abzüge im Korpus
  stammen von *einem* Gerät, dreimal gezogen — für die Hardware-Abdeckung zählt
  es einfach. `ABDECKUNG.md` weist das in der Spalte „Geräte" aus (ohne
  Kennungen zu zeigen); Klartext-Serials stehen nur in `KORPUS.md`.

  Zum Vergleichen **`tr069_serial` heranziehen, nicht nur `SerialNumber`**: Ein
  7490 im Korpus hat `SerialNumber 0000000000000000` — als einziges genulltes
  Feld im sonst intakten Urlader-Environment, mutmaßlich nach Wiederherstellung
  aus einem generischen AVM-Image. `tr069_serial` überlebt das, weil es aus der
  MAC gebildet wird (`00040E-<maca ohne Doppelpunkte>`). Bei einer solchen Box
  taugt `SerialNumber` nicht zur Identifikation, MAC und `tr069_serial` schon.
- **`calls` exakt 400?** Das ist die box-seitige Obergrenze, nicht die echte
  Listenlänge. Nie als Mengenaussage berichten.
- **Leere Datenarten**: `records: []` heißt entweder „Box hat das nicht"
  (7490 ohne Anrufbeantworter → `tam` leer, korrekt) oder „Extractor lief ins
  Leere". Der Unterschied gehört in den Bericht, notfalls als offene Frage.

Ebenfalls erwähnenswert: Export-Version im Hüllkopf. Abzüge mit **0.3.1** haben
`wan`/`dhcp`/`storage`/`tr069` durchgängig leer — eine Eigenschaft jener Version,
nicht der Box.

## 6. Report rendern und prüfen

Testet den echten Auswertepfad, nicht nur das Format:

```bash
python3 fritzreport.py ~/testdata/_work/<name> \
  -o <scratchpad>/<name>.html --no-prompt --case-id TEST
```

Danach auf Plausibilität sehen: Dateigröße (unter ~100 kB ist verdächtig), ob
Hosts enthalten sind, ob Belegtheits-Badges (D1/D2/D3) auftauchen. Der Report
enthält echte Forensikdaten — **in den Scratchpad, nie ins Repo**.

## 7. Golden-Tests — der Wächter meldet sich hier

```bash
python3 -m pytest -m golden -q
```

`test_abdeckung_ist_aktuell` **muss** jetzt fehlschlagen: Der Korpus hat sich
geändert, die Matrix noch nicht. Das ist der erwartete Zustand, kein Fehler.
Schlägt er *nicht* fehl, wurde der Abzug nicht als Bundle erkannt — zurück zu
Schritt 2.

## 8. ABDECKUNG.md neu erzeugen

```bash
python3 scripts/abdeckung.py ~/testdata/_work > ABDECKUNG.md
```

Liegen **eingegangene Auszüge** von außen vor (Issues mit Label `abdeckung`),
müssen sie mit angegeben werden — sonst verschwinden fremde Geräte aus der
Matrix:

```bash
python3 scripts/abdeckung.py ~/testdata/_work \
  --beitrag=<auszug1.json> --beitrag=<auszug2.json> > ABDECKUNG.md
```

**Immer über den vollständigen Korpus**, nie über ein Teilverzeichnis — sonst
schrumpft die Matrix stillschweigend.

Danach `git diff ABDECKUNG.md` ansehen: Was hat sich geändert? Genau das ist der
Beitrag des neuen Abzugs.

## 9. KORPUS.md fortschreiben

`~/testdata/KORPUS.md` von Hand ergänzen (kein Generator): neue Zeile in der
Bundle-Tabelle, Datensatz-Zahlen, und — wichtiger — die **Lückenliste**
aktualisieren, falls der Abzug eine Lücke geschlossen hat.

Diese Datei darf Serials und Aktenzeichen enthalten. `ABDECKUNG.md` nicht.

## 10. Volle Suite und Bericht

```bash
python3 -m pytest -q && python3 -m pytest -m golden -q
```

Beide grün, dann berichten:

- Modell, Firmware, HW-Revision — und ob es eine neue Kombination ist
- Integritätsergebnis mit Zahlen
- **Welche Lücke der Abzug geschlossen hat**, welche offen bleiben (aus
  `git diff ABDECKUNG.md` und dem Abschnitt „Wo Abzüge dem Projekt am meisten
  helfen")
- Auffälligkeiten aus Schritt 5
- Was noch fehlt oder unklar ist

Dann **stoppen** und die Freigabe zum Commit abwarten.

## Fallen

- `ABDECKUNG.md` **nie von Hand ändern** — sie wird erzeugt, der Golden-Wächter
  überschreibt Handarbeit beim nächsten Lauf.
- Abzüge und Reports **nie ins Repo** (`.gitignore` deckt `export_*/` ab, aber
  nicht jeden Namen — der Blick auf `git status` vor dem Commit ist Pflicht).
- Zu committen sind in aller Regel **nur** `ABDECKUNG.md` — `KORPUS.md` liegt
  außerhalb des Repos und wird nicht mitversioniert.
