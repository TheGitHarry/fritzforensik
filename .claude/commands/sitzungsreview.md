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

**Nachbarschaft mitgeben:** Für jede geänderte Datei den **vollständigen** aktuellen
Inhalt lesen (gelöschte überspringen). Erst dadurch sehen die Agenten das Neue im
Zusammenhang mit dem, was schon da war — die Fehlerklasse, um die es hier vor allem geht.

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
    stat:    "<Ausgabe von git diff --stat>",
    diff:    "<vollständiger Diff>",
    dateien: [ { pfad: "...", inhalt: "<ganze Datei>" }, ... ]
  }
})
```

Der Workflow läuft im Hintergrund und meldet sich, wenn er fertig ist. **Nicht** darauf
warten, indem du pollst — die Benachrichtigung kommt von selbst.

## 4. Ergebnis

Der Workflow gibt einen fertigen Bericht zurück (Abschnitte A–D). Gib ihn **wörtlich**
an den Nutzer weiter, statt ihn zusammenzufassen — der Kurator hat bereits priorisiert
und gedeckelt; eine zweite Verdichtung verlöre gerade die Belege.

Ergänze nur, was der Bericht nicht wissen kann: ob du einen der Befunde aus eigener
Kenntnis der Sitzung anders einschätzt.

**Nichts automatisch ändern.** Der Bericht ist die Lieferung; was daraus folgt,
entscheidet der Nutzer.
