# Abdeckung: getestete Boxen und Datenarten

Welche FRITZ!Box-Modelle mit welchem FRITZ!OS-Stand bereits ausgelesen wurden —
und welche Datenarten dabei tatsächlich Daten geliefert haben.

**Diese Datei wird erzeugt, nicht von Hand gepflegt:**

```bash
python3 scripts/abdeckung.py <verzeichnis-mit-bundles> > ABDECKUNG.md
```

| Zeichen | Bedeutung |
|---|---|
| ✓ | Datenart lieferte Datensätze |
| ○ | abgefragt, kam aber leer zurück |
| — | in diesem Abzug nicht enthalten |

Ein ○ ist nicht zwingend ein Fehler — eine Box ohne Anrufbeantworter liefert bei
`tam` zu Recht nichts. Es heißt nur: an dieser Kombination ist der Codepfad noch
nie mit echten Daten gelaufen.

| Modell | HWRev | FRITZ!OS | Geräte | Abzüge | calls | phonebook | wifi | events | tam | mesh | hosts | wan | dhcp | portforward | storage | supportdata | tr069 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| FRITZ!Box 7490 | 185 | 07.62 | 1 | 1 | ○ | ✓ | ○ | ✓ | ○ | ✓ | ✓ | ○ | ○ | ○ | ○ | ✓ | ○ |
| FRITZ!Box 7530 AX | 256 | 08.25 | 1 | 1 | ✓ | ✓ | ○ | ✓ | ○ | ✓ | ✓ | ✓ | ✓ | ○ | ✓ | ✓ | ✓ |
| FRITZ!Box 7590 | 226 | 08.02 | 1 | 1 | ✓ | ✓ | ○ | ✓ | ○ | ✓ | ✓ | ○ | ○ | ○ | ○ | ✓ | ○ |
| FRITZ!Box 7590 | 226 | 08.25 | 1 | 1 | ○ | ✓ | ○ | ✓ | ○ | ✓ | ✓ | ✓ | ✓ | ○ | ✓ | ✓ | ✓ |
| FRITZ!Box 7690 | 285 | 08.22 | 1 | 1 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ○ | ✓ | ✓ | ✓ |
| FRITZ!Box 7690 | 285 | 08.25 | 1 | 2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ○ | ✓ | ✓ | ✓ |

**Mehrere Abzüge derselben Box.** Die Spalte „Geräte" zählt verschiedene
Exemplare, „Abzüge" die Sicherungen davon. Wo beide auseinandergehen,
stammen mehrere Abzüge vom selben Gerät (erkannt an der Seriennummer, die
hier bewusst nicht steht) — etwa dieselbe Box vor und nach einem
Firmware-Update. Solche Abzüge erweitern die **Hardware**-Abdeckung nicht:

- FRITZ!Box 7690: 3 Abzüge, aber nur 1 Gerät

Ein Abzug eines **zweiten Exemplars** dieser Modelle ist deshalb weiterhin
wertvoll — auch wenn Modell und FRITZ!OS-Stand schon in der Tabelle stehen.

### Genullte Seriennummer

Bei FRITZ!Box 7490 im Korpus steht in `SerialNumber` eine Folge
aus lauter Nullen. Das ist **kein Auslesefehler**: Das Feld ist beschrieben,
nur eben mit einem Vorgabewert statt einer Gerätekennung.

Das übrige Urlader-Environment ist dabei unversehrt — MAC-Adressen,
Hardware-Revision und Bootloader-Version stehen normal darin. Das Muster
passt zu einer **Wiederherstellung aus einem generischen AVM-Image**: Ein
solches Image bringt die gerätespezifische Seriennummer nicht mit (sie steht
auf dem Gehäuseaufkleber), und das Feld wird beim Neuaufbau des Environments
mit Nullen belegt. Andere Ursachen sind nicht auszuschließen — ein Nachweis
des Vorgangs selbst steckt nicht in den Daten.

Praktische Folge: Bei einer solchen Box taugt `SerialNumber` **nicht** zur
Identifikation. Diese Matrix unterscheidet Geräte deshalb vorrangig über
`tr069_serial`, das aus der MAC-Adresse gebildet wird und den Vorgang
übersteht. Wer Abzüge forensisch zuordnet, sollte sich aus demselben Grund
nicht allein auf `SerialNumber` verlassen.

## Supportdaten-Varianten

| Modell | FRITZ!OS | standard | mesh | enhanced |
|---|---|---|---|---|
| FRITZ!Box 7490 | 07.62 | ✓ | ✓ | ✓ |
| FRITZ!Box 7530 AX | 08.25 | ✓ | ✓ | — |
| FRITZ!Box 7590 | 08.02 | ✓ | ✓ | ✓ |
| FRITZ!Box 7590 | 08.25 | ✓ | ✓ | — |
| FRITZ!Box 7690 | 08.22 | ✓ | ✓ | ✓ |
| FRITZ!Box 7690 | 08.25 | ✓ | ✓ | ✓ |

## Wo Abzüge dem Projekt am meisten helfen

**Bisher in keinem einzigen Abzug mit Daten gesehen** — hier ist der Codepfad
faktisch ungetestet:

- `portforward`

**Nur auf einem Teil der Modelle mit Daten gesehen** — Abzüge der übrigen
Modelle schließen die Lücke:

- `calls` — bisher nur: FRITZ!Box 7530 AX, FRITZ!Box 7590, FRITZ!Box 7690
- `wifi` — bisher nur: FRITZ!Box 7690
- `tam` — bisher nur: FRITZ!Box 7690
- `wan` — bisher nur: FRITZ!Box 7530 AX, FRITZ!Box 7590, FRITZ!Box 7690
- `dhcp` — bisher nur: FRITZ!Box 7530 AX, FRITZ!Box 7590, FRITZ!Box 7690
- `storage` — bisher nur: FRITZ!Box 7530 AX, FRITZ!Box 7590, FRITZ!Box 7690
- `tr069` — bisher nur: FRITZ!Box 7530 AX, FRITZ!Box 7590, FRITZ!Box 7690

Ebenso wertvoll: **jedes Modell, das oben noch gar nicht steht**, und jeder
deutlich abweichende FRITZ!OS-Stand eines schon gelisteten Modells.


## Bevor Sie einen Abzug bereitstellen

Ein Abzug enthält **personenbezogene Daten** — Anrufe, Telefonbuch, Gerätenamen,
MAC-Adressen. Nicht nur Ihre eigenen: auch die aller Personen, die mit dieser Box
telefoniert haben oder in ihrem WLAN waren. Diese Menschen können nicht selbst
einwilligen. Bitte prüfen Sie vor dem Bereitstellen, wessen Daten Sie weitergeben.

### Auswertung erfolgt KI-gestützt

Zwei Dinge, die auseinanderzuhalten sind:

- **Die Werkzeuge selbst enthalten keine KI.** `fritzexport` und `fritzreport`
  sind gewöhnliche Programme ohne Modell, ohne Dienstaufruf. `fritzexport`
  spricht ausschließlich mit der Box im eigenen Netz, `fritzreport` liest nur
  das Bündel auf der Platte — dass es **kein netzfähiges Modul** verwendet,
  auch keines aus der Standardbibliothek, ist durch einen Test festgehalten
  (`tests/format/test_stdlib_only.py`). Wer die Werkzeuge herunterlädt und auf
  eigenen Geräten einsetzt, gibt keine Daten heraus.
- **Die Weiterentwicklung dieses Projekts läuft KI-gestützt.** Wird ein Abzug
  bereitgestellt, um eine Lücke zu schließen, werden seine Inhalte dabei von
  einem KI-Assistenten verarbeitet — und damit an dessen Anbieter übermittelt.

**Wer einen Abzug bereitstellt, muss damit einverstanden sein.** Sind Sie es
nicht, stellen Sie bitte keinen bereit — es gibt zwei Wege ohne fremde Daten,
siehe unten.

### Am wertvollsten: Abzüge aus einem Testlabor

Wer in einer Dienststelle oder einem Labor mit **Testboxen** arbeitet, kann das
Problem an der Wurzel umgehen: Dort gibt es keine unbeteiligten Dritten, deren
Daten mitwandern. Ein solcher Abzug ist deshalb die mit Abstand unbedenklichste
Art beizutragen — und für dieses Projekt zugleich die nützlichste.

**Auch ein dünn befüllter Testaufbau hilft.** Es kommt nicht auf die Menge an,
sondern darauf, dass eine Datenart **überhaupt** Datensätze liefert. Ein paar
Testanrufe, ein Telefonbucheintrag, ein verbundenes Endgerät genügen bereits, um
ein ○ in dieser Matrix zu einem ✓ zu machen — und damit zu belegen, dass der
Codepfad auf dieser Modell-/Firmware-Kombination funktioniert. Gerade bei
`portforward`, das bisher in keinem einzigen Abzug gefüllt war, reicht eine
einzige eingerichtete Portfreigabe.

### Ganz ohne Daten: nur die Abdeckungsinformation

Kommt auch das nicht in Frage, genügt für diese Matrix oft schon, **was ohne
personenbezogene Daten** auskommt:

- Modell, HWRevision und FRITZ!OS-Stand (aus der Box-Oberfläche ablesbar)
- welche Datenarten Daten enthielten — also die Zeile, die in dieser Tabelle
  entstünde

Damit lässt sich eine Lücke oft schon schließen, ohne dass ein einziger Datensatz
das Haus verlässt. Ein vollständiger Abzug ist nur nötig, wenn ein Fehler
nachvollzogen werden muss.

Ein Abzug gehört in **keinem** Fall in ein öffentliches Issue. Der Weg für eine
Kontaktaufnahme steht in [SECURITY.md](SECURITY.md).
