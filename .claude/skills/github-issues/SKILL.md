---
name: github-issues
description: GitHub-Zugriff auf dieses Repo (Issues lesen, anlegen, kommentieren) über gh mit dem Token aus ~/.env. Nutzen, sobald Issues, Pull Requests oder der offene Backlog aus GitHub gebraucht werden.
---

# GitHub-Zugriff für fritzforensik

Das Repo hängt an `https://github.com/TheGitHarry/fritzforensik.git` (`origin`).
`gh` ist **nicht** interaktiv angemeldet — die Authentifizierung läuft über den
Token aus `~/.env`.

## Token laden

Der Token steht als `GH_TOKEN` in `/home/claude/.env` (gitignored). Immer nur diese
eine Variable ziehen, nie die ganze Datei sourcen — dort liegen auch Mail- und
Nextcloud-Zugangsdaten, die hier nichts zu suchen haben:

```bash
export GH_TOKEN=$(grep '^GH_TOKEN=' /home/claude/.env | cut -d= -f2- | tr -d '"'"'"'')
```

Den Token **nie ausgeben** — nicht in Logs, nicht in Kommandoausgaben, nicht in
Dateien. Zum Prüfen der Anmeldung reicht `gh api user --jq .login`.

## Übliche Aufrufe

```bash
gh issue list --state open --limit 50                    # offene Issues
gh issue list --state all --limit 50                     # inkl. geschlossener
gh issue view <nr> --comments                            # ein Issue samt Verlauf
gh issue create --title "..." --body "..."               # neues Issue
gh issue comment <nr> --body "..."                       # kommentieren
gh issue close <nr>                                      # schließen
```

Für strukturierte Weiterverarbeitung `--json` nutzen, z. B.:

```bash
gh issue list --state open --json number,title,labels,updatedAt \
  --jq '.[] | "\(.number)\t\(.title)"'
```

## Wenn der Aufruf blockiert wird

Kombiniert man `export GH_TOKEN=$(grep ...)` mit dem `gh`-Aufruf in *einem*
Kommando, greift unter Umständen der Auto-Mode-Klassifizierer. Dann beide Schritte
trennen oder den Nutzer um Freigabe bitten — **keine Umgehungsversuche**.

Damit das seltener passiert, liegt in `.claude/settings.json` eine passende
Permission-Regel.

## Schreibende Aktionen

Issues anlegen, kommentieren oder schließen sind nach außen sichtbare Handlungen.
Vorher beim Nutzer rückversichern, sofern er sie nicht ausdrücklich beauftragt hat.

## Backlog

Der offene Stand steht **ausschließlich** in den GitHub-Issues — es gibt bewusst keine
zweite Quelle. Wer nach „was steht noch an" gefragt wird, liest die Issues, sonst nichts.

Früher führte `CONCEPT.md` einen zweiten Backlog („Offen / später"); die beiden liefen
auseinander, die Datei ist deshalb aufgelöst. Taucht in einem alten Stand oder einer
alten Unterhaltung noch ein Verweis darauf auf: nicht wiederbeleben, sondern als Issue
anlegen.

Der fachliche Vertrag — was die Werkzeuge leisten müssen — steht in
**[ANFORDERUNGEN.md](../../../docs/ANFORDERUNGEN.md)**. Dort nennt jede Zeile mit Status
`offen` ihre Issue-Nummer; die Verknüpfung läuft nur in diese Richtung (Issues
verweisen nicht zurück, sonst wären bei jedem Statuswechsel zwei Orte zu pflegen).
