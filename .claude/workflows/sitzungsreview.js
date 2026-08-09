export const meta = {
  name: 'sitzungsreview',
  description: 'Nachprüfung einer Arbeitssitzung: 5 Prüfer, Skeptiker, Kurator — Bericht, keine Änderung',
  whenToUse: 'Nach einer umfangreichen Sitzung, vor dem Commit oder PR. Prüfgegenstand ist der Diff samt der vollständigen berührten Dateien.',
  phases: [
    { title: 'Sammeln', detail: '5 Prüfer, blind zueinander' },
    { title: 'Prüfen', detail: 'Skeptiker versucht Befunde zu widerlegen' },
    { title: 'Bericht', detail: 'Kurator priorisiert und deckelt' },
  ],
}

// args: { branch, basis, stat, dateien: ["pfad", ...] }
//
// Bewusst **keine** Dateiinhalte in args: Der Prüfgegenstand einer großen Sitzung
// erreicht schnell mehrere hundert KB (diese Sitzung: 319 KB / ~180k Token). Durch den
// Hauptkontext geschleust wäre er allein deshalb nicht mehr handhabbar. Die Agenten
// holen sich Diff und Dateien selbst — sie haben Bash und Read.
const A = args || {}
const BASIS = A.basis || 'main'
const DATEIEN = A.dateien || []
if (!DATEIEN.length) throw new Error('keine geänderten Dateien übergeben')

const KONTEXT = `
## Prüfgegenstand

Branch: ${A.branch || '(unbekannt)'} · Vergleichsbasis: \`${BASIS}\`

### Überblick
${A.stat || '(kein --stat)'}

### So kommst du an den Stoff

Hol ihn dir selbst — arbeite im Repo-Verzeichnis:

\`\`\`bash
git diff ${BASIS}...HEAD              # die Änderung
git diff ${BASIS}...HEAD -- <datei>   # gezielt eine Datei
\`\`\`

Und lies die **vollständigen** Dateien (Read-Tool), nicht nur die Hunks: Die
Fehlerklasse, um die es hier vor allem geht, sind Widersprüche zwischen dem Neuen und
dem, was schon da war. Die sieht man im Hunk nicht.

### Berührte Dateien (${DATEIEN.length})
${DATEIEN.map(p => `- ${p}`).join('\n')}
`

const GEMEINSAM = `
Du prüfst eine abgeschlossene Arbeitssitzung im Repo fritzforensik (FRITZ!Box-Forensik).

**Lies zuerst den Skill \`sitzungsreview\`** (Skill-Tool, Name: sitzungsreview). Er nennt,
was die Testsuite bereits garantiert — das prüfst du NICHT — und die Regeln des Projekts.

Sprache: Deutsch. Belegpflicht: Jeder Befund nennt Datei und Zeile oder ein wörtliches
Zitat. Ohne Beleg gibst du ihn nicht zurück. Keine Vermutungen ("könnte problematisch
sein") — entweder du zeigst, dass es bricht, oder du lässt es weg.

Du darfst lesen und Tests laufen lassen (\`python3 -m pytest -q\`), aber **nichts ändern**.

Lieber fünf belegte Befunde als dreißig mögliche. Der Nutzer geht jedem einzeln nach.
${KONTEXT}`

const SCHEMA = {
  type: 'object',
  required: ['befunde'],
  properties: {
    befunde: {
      type: 'array',
      items: {
        type: 'object',
        required: ['datei', 'klasse', 'schwere', 'behauptung', 'beleg'],
        properties: {
          datei: { type: 'string' },
          zeile: { type: 'integer' },
          klasse: {
            type: 'string',
            enum: ['korrektheit', 'test-luecke', 'doku-widerspruch', 'prosa-status',
                   'vereinfachung', 'konvention'],
          },
          schwere: { type: 'string', enum: ['hoch', 'mittel', 'niedrig'] },
          behauptung: { type: 'string', description: 'Ein Satz: was ist falsch?' },
          beleg: { type: 'string', description: 'Datei:Zeile oder wörtliches Zitat' },
          vorschlag: { type: 'string' },
        },
      },
    },
  },
}

const PRUEFER = [
  {
    key: 'code-review',
    prompt: `Prüfe die **Korrektheit** der geänderten Logik und ob sie **einfacher** ginge.

Korrektheit: Fehlerpfade, Grenzfälle, Off-by-one, falsche Annahmen über Eingaben,
Verhalten bei fehlenden/leeren/kaputten Daten. Die berührten Dateien liegen vollständig
vor — prüfe das Neue **im Zusammenhang** mit dem, was schon da war.

Vereinfachung: doppelte Logik, unnötige Zwischenschritte, Sonderfälle die keine sind.
Vorsicht: Manches sieht nur nach Doppelung aus. Der Skill nennt Trennungen, die Absicht
sind — prüfe dagegen, bevor du Zusammenlegen vorschlägst.

Klasse: \`korrektheit\` oder \`vereinfachung\`.`,
  },
  {
    key: 'test-kritik',
    prompt: `Prüfe die **Güte der Tests**, nicht den Code.

Für jeden neuen oder geänderten Test:
1. Prüft er, was sein **Name** und sein **Docstring** behaupten?
2. Könnte er **grün sein, obwohl das Feature kaputt ist**? Geh das gedanklich durch:
   Was müsste im Code brechen, damit dieser Test fällt — und deckt das die Behauptung ab?
3. Sammelt er die zu vergleichenden Dinge in getrennten Kanälen und vergleicht sie nie?
   (Genau dieser Fehler ist in diesem Repo schon vorgekommen, siehe Skill.)
4. Prüft er nur, dass etwas *existiert*, wo er prüfen müsste, dass es *stimmt*?

Zusätzlich: Nennt ANFORDERUNGEN.md einen Test als Nachweis, der die Anforderung
inhaltlich gar nicht belegt? (Dass der Name existiert, prüft bereits ein Test — dass er
passt, niemand.)

Klasse: \`test-luecke\`. Das ist der wertvollste Agent des Laufs; ein grüner Test, der
nichts prüft, ist schlimmer als kein Test.`,
  },
  {
    key: 'inline-doku',
    prompt: `Prüfe **Docstrings und Kommentare gegen das tatsächliche Verhalten** des Codes.

- Behauptet ein Docstring etwas, das der Code nicht (mehr) tut?
- Nennt er Zahlen, Grenzen oder Bedingungen, die nicht stimmen?
- Erklärt er das **Warum** oder wiederholt er nur das Was?
- Fehlt an einer nicht-offensichtlichen Stelle die Begründung — besonders dort, wo
  jemand später "vereinfachen" und damit einen Fehler einbauen könnte?
- Sprachtrennung: Doku/Meldungen Deutsch, Identifier/JSON-Feldnamen Englisch.

Klasse: \`konvention\` für Sprache/Stil, \`doku-widerspruch\` wenn der Docstring dem Code
widerspricht.`,
  },
  {
    key: 'doku-eigentum',
    prompt: `Prüfe die **Projektdoku auf Widersprüche und Dubletten**.

Der Skill nennt die Eigentumstabelle: jede Aussage hat genau einen Ort. Prüfe:
- Steht dieselbe Aussage an zwei Orten — und weichen die Fassungen ab?
- Widerspricht eine Datei einer anderen?
- Steht etwas an einem Ort, dem es nicht gehört? **Besonders methode.md**: Sie fasst ein
  externes nicht öffentliches Methodenpapier zusammen und trägt D2 — eigene Messreihen gehören dort
  nicht hinein.
- Passt der **Titel** einer Datei noch zu ihrer Rolle?
- Stimmt die **Grade-Definition in CLAUDE.md** (steht dort in Prosa, nicht in einer
  Tabelle) mit \`fritzreport/model.py\` \`GRADE_LABEL\` überein? Kein Test erfasst das.
- Ist irgendwo ein Backlog entstanden ("offen", "später", "TODO") statt eines Issues?

Klasse: \`doku-widerspruch\`. Widersprüche mit Außenwirkung (Grade-Bedeutung,
Netzfreiheit, Datenschutz) sind \`hoch\`.`,
  },
  {
    key: 'prosa-status',
    prompt: `Ein einziger, enger Auftrag: Finde **neu eingefügten Status in Prosa**.

Das Repo verbietet ihn, weil er mit dem nächsten Commit veraltet: Testanzahlen,
Versionsnummern, "alles grün", "funktioniert jetzt", "vollständig umgesetzt", "aktuell
X Dateien". Auch in **Docstrings** und Kommentaren, nicht nur in .md-Dateien.

Nur was **diese Sitzung hinzugefügt** hat (der Diff zeigt es mit +). Altbestand ist nicht
dein Auftrag.

Ausnahme: ABDECKUNG.md ist erzeugt und darf Status tragen.

Klasse: \`prosa-status\`. Belege **wörtlich** — der Satz selbst ist der Beweis.`,
  },
]

// ── Phase 1: fünf Prüfer, blind zueinander ───────────────────────────────────
phase('Sammeln')
log(`Prüfgegenstand: ${(A.dateien || []).length} Dateien`)

const roh = await parallel(PRUEFER.map(p => () =>
  agent(`${GEMEINSAM}\n\n## Dein Auftrag: ${p.key}\n\n${p.prompt}`,
        { label: p.key, phase: 'Sammeln', schema: SCHEMA })
    .then(r => (r?.befunde || []).map((b, i) => ({ ...b, id: `${p.key}-${i + 1}`, agent: p.key })))
))

const alle = roh.filter(Boolean).flat()
log(`${alle.length} Befunde aus ${roh.filter(Boolean).length} Prüfern`)

// ── Phase 2: Skeptiker — nur wo Falsch-Positive teuer sind ───────────────────
const ZU_PRUEFEN = new Set(['korrektheit', 'test-luecke', 'vereinfachung'])
const strittig = alle.filter(b => ZU_PRUEFEN.has(b.klasse))
const direkt = alle.filter(b => !ZU_PRUEFEN.has(b.klasse))

let urteile = []
if (strittig.length) {
  phase('Prüfen')
  const bündel = Math.min(3, Math.ceil(strittig.length / 6))
  const grösse = Math.ceil(strittig.length / bündel)
  const gruppen = Array.from({ length: bündel }, (_, i) =>
    strittig.slice(i * grösse, (i + 1) * grösse)).filter(g => g.length)

  log(`${strittig.length} Befunde zur Gegenprüfung in ${gruppen.length} Bündeln`)

  const URTEIL_SCHEMA = {
    type: 'object',
    required: ['urteile'],
    properties: {
      urteile: {
        type: 'array',
        items: {
          type: 'object',
          required: ['id', 'urteil', 'begruendung'],
          properties: {
            id: { type: 'string' },
            urteil: { type: 'string', enum: ['bestaetigt', 'widerlegt', 'strittig'] },
            begruendung: { type: 'string', description: 'Was hast du versucht, was kam heraus?' },
          },
        },
      },
    },
  }

  urteile = (await parallel(gruppen.map((g, i) => () =>
    agent(`${GEMEINSAM}

## Dein Auftrag: Skeptiker

Du bekommst Befunde anderer Prüfer und versuchst, sie zu **widerlegen**. Nicht zu
bestätigen — zu widerlegen. Was du nicht widerlegen kannst, ist belastbar.

Vorgehen je Befund:
- \`korrektheit\` → **Lass den Test laufen** (\`python3 -m pytest -q\`, oder ein
  read-only Python-Einzeiler). Der tatsächliche Lauf ist die stärkste Widerlegung.
- \`test-luecke\` → Prüfe: Fiele der Test doch, wenn das Feature kaputt wäre? Geh den
  konkreten Bruch durch.
- \`vereinfachung\` → Hier ist die Widerlegungsquote erfahrungsgemäß am höchsten. Die
  einfachere Variante scheitert meist an einem Grenzfall, den der Vorschlagende nicht
  kannte. Prüfe **gegen die Fallen im Skill** — manche Trennung ist Absicht.

Urteile:
- \`bestaetigt\` — Widerlegung versucht, gescheitert. Der Befund steht.
- \`widerlegt\` — der Befund ist falsch. Sag konkret warum.
- \`strittig\` — es kommt auf eine Abwägung an, die der Nutzer treffen muss.

Sei **fair**, nicht destruktiv: Ein echter Befund, den du wegredest, ist teurer als ein
Fehlalarm. Im Zweifel \`strittig\`.

## Zu prüfende Befunde

${JSON.stringify(g, null, 1)}`,
      { label: `skeptiker-${i + 1}`, phase: 'Prüfen', schema: URTEIL_SCHEMA })
  ))).filter(Boolean).flatMap(r => r.urteile || [])
}

const urteilVon = Object.fromEntries(urteile.map(u => [u.id, u]))
const bewertet = alle.map(b => ({
  ...b,
  urteil: urteilVon[b.id]?.urteil || (ZU_PRUEFEN.has(b.klasse) ? 'strittig' : 'ungeprueft'),
  gegenprobe: urteilVon[b.id]?.begruendung || '',
}))

const widerlegt = bewertet.filter(b => b.urteil === 'widerlegt')
const bleibt = bewertet.filter(b => b.urteil !== 'widerlegt')
log(`${widerlegt.length} widerlegt, ${bleibt.length} bleiben`)

// ── Phase 3: Kurator ─────────────────────────────────────────────────────────
phase('Bericht')

const bericht = await agent(`${GEMEINSAM}

## Dein Auftrag: Kurator

Du schreibst den **Bericht an den Nutzer**. Auf Deutsch, als Fließtext mit Markdown.

Regeln, die den Bericht brauchbar machen:

1. **Harte Deckelung: Abschnitt A und B zusammen höchstens 12 Befunde.** Alles Weitere
   nach D. Du priorisierst, du lädst nicht ab.
2. **Streiche jeden Befund, den ein bestehender Test bereits abdeckt** (siehe Skill,
   Ausschlussliste).
3. **Dubletten zusammenlegen** — mehrere Prüfer finden oft dasselbe. Ein Eintrag, beide
   Quellen genannt.
4. **Widersprechen sich zwei Befunde, wird nicht gemittelt.** Beide Positionen wörtlich
   nach Abschnitt C, der Nutzer entscheidet.
5. Widerlegte Befunde nur als **Zahl** nennen, nicht einzeln ausführen.

Aufbau:

**Kopf, drei Zeilen:** Umfang · Befundzahl nach Gegenprüfung · und die eine Frage:
**Ist der Stand commit-fähig?** (ja / ja, mit Vorbehalt / nein — und in einem Satz warum)

**A — Muss vor dem Commit** (erwartet 0–3): bestätigte \`korrektheit\` und
\`test-luecke\`, dazu Doku-Widersprüche mit Außenwirkung (Grade-Bedeutung, Netzfreiheit,
Datenschutz). Je Befund: Behauptung · Beleg (Datei:Zeile) · was die Gegenprüfung ergab ·
Vorschlag.

**B — Sollte, blockiert aber nicht** (erwartet 3–8): knapper, je zwei bis drei Zeilen.

**C — Strittig, du entscheidest** (erwartet 0–2): beide Positionen wörtlich.

**D — Anhang, ungeprüft**: Stil und Konvention, **eine Zeile pro Punkt**, keine
Ausführung.

Schließe mit einem Satz dazu, was der Lauf **nicht** geprüft hat.

## Befunde nach Gegenprüfung

${JSON.stringify(bleibt, null, 1)}

## Widerlegt (nur zählen)

${widerlegt.length} Befunde: ${widerlegt.map(b => b.id).join(', ') || '—'}
`, { label: 'kurator', phase: 'Bericht' })

return {
  bericht,
  zahlen: {
    befunde_roh: alle.length,
    gegengeprueft: strittig.length,
    widerlegt: widerlegt.length,
    im_bericht: bleibt.length,
  },
}
