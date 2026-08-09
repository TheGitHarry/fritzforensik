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

| Modell | HWRev | FRITZ!OS | Abzüge | calls | phonebook | wifi | events | tam | mesh | hosts | wan | dhcp | portforward | storage | supportdata | tr069 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| FRITZ!Box 7490 | 185 | 07.62 | 1 | ○ | ✓ | ○ | ✓ | ○ | ✓ | ✓ | ○ | ○ | ○ | ○ | ✓ | ○ |
| FRITZ!Box 7530 AX | 256 | 08.25 | 1 | ✓ | ✓ | ○ | ✓ | ○ | ✓ | ✓ | ✓ | ✓ | ○ | ✓ | ✓ | ✓ |
| FRITZ!Box 7590 | 226 | 08.02 | 1 | ✓ | ✓ | ○ | ✓ | ○ | ✓ | ✓ | ○ | ○ | ○ | ○ | ✓ | ○ |
| FRITZ!Box 7590 | 226 | 08.25 | 1 | ○ | ✓ | ○ | ✓ | ○ | ✓ | ✓ | ✓ | ✓ | ○ | ✓ | ✓ | ✓ |
| FRITZ!Box 7690 | 285 | 08.22 | 1 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ○ | ✓ | ✓ | ✓ |
| FRITZ!Box 7690 | 285 | 08.25 | 2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ○ | ✓ | ✓ | ✓ |

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

Ein Abzug enthält personenbezogene Daten und gehört **nicht** in ein öffentliches
Issue. Der Weg für eine Kontaktaufnahme steht in [SECURITY.md](SECURITY.md).
