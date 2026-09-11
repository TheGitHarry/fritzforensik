#!/usr/bin/env bash
# Erinnert vor nach außen sichtbaren Schritten an die Anonymisierung.
#
# Das Repo ist seit 2026-09-11 öffentlich. Issues, Kommentare und Commits gehen
# damit unmittelbar an die Öffentlichkeit, und nachträgliches Bearbeiten entfernt
# nichts: GitHub führt zu jedem Body einen Bearbeitungsverlauf, der über die
# GraphQL-API im Volltext lesbar bleibt (siehe CLAUDE.md, Abschnitt Doku-Eigentum).
#
# Wird von .claude/settings.json als PreToolUse-Hook auf jeden Bash-Aufruf
# gelegt; welche Kommandos gemeint sind, entscheidet dieses Skript (siehe
# unten). Blockiert nichts, es erinnert nur.
set -uo pipefail

eingabe=$(cat 2>/dev/null || true)

# Die Filterung steht hier und nicht als if-Bedingung in settings.json: Die
# Bedingung dort griff nicht, der Hook lief bei jedem Bash-Aufruf. Wer nicht
# passt, bekommt keine Ausgabe — ein Hook, der immer redet, wird ignoriert.
befehl=$(printf '%s' "$eingabe" | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("tool_input",{}).get("command",""))
except Exception: print("")' 2>/dev/null || true)

case "$befehl" in
  *"gh issue create"*|*"gh issue comment"*|*"gh pr create"*) wohin="Dieses Issue" ;;
  *"git push"*)                                             wohin="Dieser Push" ;;
  *)                                                        exit 0 ;;
esac

regeln="Aktenzeichen als VG-XX-000000, MAC-Adressen als aa:bb:cc:dd:ee:NN, keine Hostnamen, keine LAN-Adressen, keine Seriennummern, keine Verfasser oder Herausgeber nicht oeffentlicher Papiere."

python3 - "$wohin" "$regeln" <<'PY'
import json, sys
wohin, regeln = sys.argv[1], sys.argv[2]
kurz = f"{wohin} geht in ein OEFFENTLICHES Repo. Vorher anonymisieren: {regeln}"
lang = (kurz + " Nachtraeglich reicht Bearbeiten nicht: GitHub haelt den "
        "Bearbeitungsverlauf vor, er ist ueber die GraphQL-API im Volltext lesbar "
        "und nur von Hand in der Weboberflaeche loeschbar.")
print(json.dumps({
    "systemMessage": kurz,
    "hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": lang},
}, ensure_ascii=True))
PY
