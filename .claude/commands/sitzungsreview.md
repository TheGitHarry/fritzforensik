---
description: Nachprüfung der aktuellen Sitzung durch mehrere Review-Agenten — Code, Tests, Doku, Skeptiker. Ergebnis ist ein Bericht, keine Änderung.
---

# Sitzungsreview starten

Stelle den Prüfgegenstand zusammen und starte den Workflow `sitzungsreview`. **Keine
Prüflogik hier** — die steckt im Workflow-Skript, das Projektwissen im gleichnamigen Skill.

## 1. Prüfgegenstand ermitteln

Basis ist der Vergleich gegen `main` — oder gegen den Stand vor der Sitzung, falls schon
auf `main` gearbeitet wurde:

```bash
git branch --show-current
git diff main...HEAD --stat
git diff main...HEAD
git diff main...HEAD --name-only
```

Ist der aktuelle Branch `main` (oder ergibt der Vergleich nichts), stattdessen die
uncommitteten Änderungen samt der Commits nehmen, die seit dem Sitzungsbeginn entstanden
sind — im Zweifel den Nutzer fragen, wogegen verglichen werden soll, statt zu raten.

**Die Dateiinhalte werden nicht mitgegeben** — nur ihre Pfade. Der Prüfgegenstand einer
großen Sitzung erreicht schnell mehrere hundert KB (eine gemessene Sitzung: 319 KB,
~180k Token); durch diesen Kontext geschleust wäre er allein deshalb nicht handhabbar.
Die Agenten holen sich Diff und Dateien selbst, sie haben Bash und Read. Der Workflow
sagt ihnen im Prompt, dass sie die **ganzen** Dateien lesen sollen, nicht nur die Hunks.

## 2. Abbruchbedingungen — Hinweis statt Lauf

Prüfe **vor** dem Start. Bei jedem dieser Fälle nicht starten, sondern kurz begründen:

| Fall | Warum kein Lauf |
|---|---|
| Diff ist leer | Nichts zu prüfen |
| `python3 -m pytest -q` ist rot | Erst grün machen. Sonst prüfen fünf Agenten Code, der sich noch ändert |
| unter ~200 geänderte Zeilen | Die Fixkosten (jeder Agent liest Skill und Diff) fressen den Nutzen — ein normales Review ist hier billiger und genauso gut |

Die Testsuite läuft ohnehin offline und schnell; der Lauf lohnt sich vor dem Start.

## 3. Workflow starten

```
Workflow({
  name: "sitzungsreview",
  args: {
    branch:  "<aktueller Branch>",
    basis:   "main",                        // wogegen verglichen wird
    stat:    "<Ausgabe von git diff --stat>",
    dateien: ["pfad/eins.py", "pfad/zwei.md", ...]   // nur Pfade, keine Inhalte
  }
})
```

Der Workflow läuft im Hintergrund und meldet sich, wenn er fertig ist. **Nicht** darauf
warten, indem du pollst — die Benachrichtigung kommt von selbst.

**Falle — `scriptPath` statt `name` benutzen.** Der Aufruf über `name: "sitzungsreview"`
lädt eine **zwischengespeicherte** Fassung des Skripts, nicht die Datei im Repo. Nach
jeder Änderung an `sitzungsreview.js` liefe damit weiter der alte Stand; kenntlich an
einer Fehlermeldung, die zur aktuellen Datei nicht passt. Deshalb:

```
Workflow({ scriptPath: ".claude/workflows/sitzungsreview.js", args: { ... } })
```

Ob die richtige Fassung läuft, verrät die Zeile `Script file:` in der Antwort: Sie muss
auf den Repo-Pfad zeigen, nicht auf eine Kopie unter `workflows/scripts/`.

## 4. Ergebnis

Der Workflow gibt einen fertigen Bericht zurück (Abschnitte A–D). Gib ihn **wörtlich**
an den Nutzer weiter, statt ihn zusammenzufassen — der Kurator hat bereits priorisiert
und gedeckelt; eine zweite Verdichtung verlöre gerade die Belege.

Ergänze nur, was der Bericht nicht wissen kann: ob du einen der Befunde aus eigener
Kenntnis der Sitzung anders einschätzt.

**Nichts automatisch ändern.** Der Bericht ist die Lieferung; was daraus folgt,
entscheidet der Nutzer.
