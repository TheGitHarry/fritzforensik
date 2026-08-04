# fritzforensik

Zwei zusammengehörige Werkzeuge für die forensische Auswertung einer AVM FRITZ!Box:

| Werkzeug | Rolle |
|---|---|
| **fritzexport** | zieht **live** forensisch relevante Daten aus einer laufenden Box in ein **Bundle** |
| **fritzreport** | macht aus diesem Bundle einen **self-contained forensischen HTML-Report** |

```
   ┌────────────────┐        Bundle (Verzeichnis)        ┌────────────────┐
   │  fritzexport   │  ──▶   fritzexport_*_*.json        │  fritzreport   │  ──▶  report.html
   │  (zieht live   │        + .sha256-Sidecars          │  (baut den     │       (self-contained,
   │   aus der Box) │        + supportdata_*.txt         │   Report)      │        offline lesbar)
   └────────────────┘                                    └────────────────┘
```

fritzreport greift **nie** auf die Box zu — es wertet nur ein vorhandenes Bundle aus.
Beide Werkzeuge sind eigenständige Single-File-Binaries für den USB-Stick-Feldeinsatz
ohne installiertes Python.

Das gemeinsame Bundle-Format liegt in **`fritzformat/`** — Dateinamen, Hüllformat und
SHA256-Sidecars stehen dort *einmal* und werden von beiden Seiten benutzt.

Was die Werkzeuge fachlich leisten müssen, steht in [ANFORDERUNGEN.md](ANFORDERUNGEN.md);
offene Punkte ausschließlich in den [GitHub-Issues](https://github.com/TheGitHarry/fritzforensik/issues).

---

## Installation

**Feldeinsatz:** die Single-File-Binaries aus dem Release herunterladen
(`fritzexport-<version>-linux-x86_64`, `fritzreport-<version>-windows-x86_64.exe`, …).

**Entwicklung:**

```bash
git clone https://github.com/TheGitHarry/fritzforensik && cd fritzforensik
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
```

`requests` wird ausschließlich von fritzexport gebraucht. **fritzreport und fritzformat
sind stdlib-only** — ein Test (`tests/format/test_stdlib_only.py`) wacht darüber, damit
das Report-Binary schlank und netzwerkfrei bleibt.

---

# fritzexport — Live-Abzug aus der Box

Deckt ab: Anrufliste, Telefonbuch, WLAN-Geräteliste, Ereignislog (alle Kategorien),
Anrufbeantworter, Mesh-Topologie, Hosts, WAN-Status, DHCP-Konfiguration, Port-Forwards,
USB-Storage, erweiterte Supportdaten und TR-069-Konfiguration.

Authentifizierung über das offizielle AVM Web-UI-SID-Verfahren (PBKDF2-Challenge-Response,
MD5-Fallback für ältere Firmware). Die Box wird per SSDP-Auto-Discovery im LAN gefunden
oder explizit per `--host` adressiert.

## Nutzung

Ohne Argumente: Auto-Discovery, bei genau einer Box direkt Abfrage von Benutzer und
Passwort, dann vollständiger Abzug:

```bash
./fritzexport
```

Bei mehreren Boxen erscheint eine nummerierte Auswahl mit Option *"keine"* (= Abbruch).
Alternativ explizit:

```bash
export FRITZ_PW='dein-passwort'
fritzexport --host 192.168.178.1 --user admin
fritzexport --host 192.168.178.1 --user admin --calls --wifi --tr069   # gezielt
fritzexport --discover                                                  # nur Discovery (JSON)
```

Ohne `FRITZ_PW` wird das Passwort interaktiv abgefragt (`getpass`). Das Passwort darf
**nie** als CLI-Argument übergeben werden.

`--host` akzeptiert `fritz.box` wie `https://192.168.178.1`. Selbstsignierte Box-Zertifikate
werden erkannt; das Tool schaltet dann selbstständig auf TLS ohne Verifikation um.
`--insecure` lässt sich weiterhin explizit setzen. `--iface` setzt die Source-IP für
SSDP-Multicast bei Multi-Interface-Hosts.

`--output` ist optional (Default `./export/` neben dem Binary). **Jeder Lauf bekommt ein
eigenes Verzeichnis** mit UTC-Zeitstempel; ein zweiter Lauf überschreibt nie den ersten.
Die Logdatei `fritzexport_<ts>.log` liegt im selben Verzeichnis.

Nach dem Abzug wird das Verzeichnis auf den **Fallkopf** umbenannt, sodass Abzug und
Report am Namen zusammenfinden:

```
C-2026-0815_A-01_20260713T101530Z/            ← Bundle
C-2026-0815_A-01_20260713T101530Z.html        ← Report (fritzreport)
C-2026-0815_A-01_20260713T101530Z.html.sha256
```

Ohne Fallkopf bleibt es beim Zeitstempelnamen (`export_20260713T101530Z/`) — der
gemeinsame Stamm trägt auch dann. Schlägt das Umbenennen fehl (Rechte, Zielname
existiert), behält der Abzug seinen bisherigen Namen; er ist vollständig, es wird nur
gewarnt. Bricht der Lauf vorher ab, bleibt ebenfalls der Zeitstempelname stehen —
mitsamt vollständiger Logdatei, die ab der ersten Zeile geschrieben wird.

## Extractoren

| Flag | Protokoll | Inhalt |
|---|---|---|
| `--calls` | Web-UI | Anrufliste (CSV-Export) |
| `--phonebook` | Web-UI | Alle Telefonbücher (XML-Export) |
| `--wifi` | Web-UI | WLAN-Geräteliste inkl. inaktiver Geräte |
| `--events` | Web-UI | Ereignislog aller Kategorien (sys/net/wlan/fon/usb) |
| `--tam` | TR-064 + Web-UI-Fallback | Anrufbeantworter-Metadaten + Audio-WAVs |
| `--mesh` | TR-064 + Web-UI-Fallback | Mesh-Topologie |
| `--hosts` | TR-064 + Index-Fallback | Alle bekannten Hosts |
| `--wan` | TR-064 | WAN-Status, externe IP, Traffic-Counter, DSL-Daten |
| `--dhcp` | TR-064 | DHCP-Serverkonfiguration |
| `--portforward` | TR-064 | Port-Forwarding-Regeln |
| `--storage` | TR-064 | USB-/NAS-Storage-Konfiguration und User |
| `--supportdata` | Web-UI | Erweiterte Supportdaten (vollständiger Text-Dump) |
| `--tr069` | TR-064 | TR-069-Konfiguration (ACS-URL, Fernwartungsstatus) |

Ohne explizite Auswahl laufen alle Extractoren (`--all`).

### TR-064-Abhängigkeit

Extractoren mit TR-064 (`--wan`, `--dhcp`, `--portforward`, `--storage`, `--tr069`) brauchen:
*Heimnetz → Netzwerk → Netzwerkeinstellungen → "Zugriff für Anwendungen zulassen"* +
*"Statusinformationen über UPnP übertragen"*.

Ist TR-064 nicht erreichbar, warnt das Tool und nennt die betroffenen Extractoren; die
mit Web-UI-Fallback (`--tam`, `--mesh`) laufen trotzdem durch.

**Zusätzlich braucht der Box-Benutzer die TR-064-Berechtigung.** Fehlt sie, antwortet die
Box auf jeden SOAP-Aufruf mit `UPnPError 401` — sichtbar als *"TR-064 nicht zugänglich"*.
Der Lauf bricht nicht ab, `--wan` liefert dann aber nur die Web-UI-Felder. Das Recht sitzt
unter *System → FRITZ!Box-Benutzer → \<Benutzer\> → bearbeiten*.

### Anrufbeantworter (`--tam`)

Audio-Aufnahmen landen als WAV in `tam_audio/`. Primär über TR-064 (`X_AVM-DE_TAM:1`):
der `<New>`-Flag jeder Nachricht wird vor und nach dem Download erfasst; markiert die Box
implizit als "gelesen", wird der Status über `MarkMessage(MarkedAsRead=0)` wiederhergestellt
(`tam_state_preserved: true`). Im Web-UI-Fallback ist das nicht möglich
(`tam_state_preserved: false`).

### Ereignislog (`--events`)

Ruft alle Filterkategorien ab (`all`, `sys`, `net`, `wlan`, `fon`, `usb`) und dedupliziert
nach `(date, time, message)`. Jeder Eintrag trägt ein `found_in_filters`-Array — Einträge,
die eine Firmware nur in einer Kategorie liefert, gehen nicht verloren.

### Erweiterte Supportdaten (`--supportdata`)

POST auf `/cgi-bin/firmwarecfg` (multipart), kein TR-064 nötig. Drei Varianten nacheinander:
`SupportData` (Standard), `MeshSupportData` (Mesh-Diagnose), `SupportDataEnhanced` (erweitert).

Ob für die erweiterte Variante ein physischer Tastendruck nötig ist, hängt von der
Box-Einstellung *erweiterte Sicherheit* ab. Das Tool probiert es deshalb **erst ohne
Bestätigung**: ist die Einstellung aus, kommen die Daten sofort. Verlangt die Box eine
Bestätigung, öffnet schon dieser erste Aufruf das Zeitfenster; dann erscheint der Hinweis
(Knopf an der Box drücken, im Web-UI auf OK) mit 30-s-Countdown. Läuft die Zeit ab, wird
**nur diese Variante** übersprungen.

Pro Variante wird die Rohdatei als `supportdata_<typ>_<ts>.txt` + `.sha256`-Sidecar abgelegt.
`extra_meta` listet `supportdata_fetched` und `supportdata_missing`, sodass im Bericht
sichtbar bleibt, welche Variante fehlt.

## Exit-Codes

| Code | Bedeutung |
|------|-----------|
| 0 | Alle gewählten Extractoren erfolgreich |
| 1 | Auth-Fehler (falsches Passwort, Box gesperrt) |
| 2 | Box nicht erreichbar (Netzwerk/HTTP-Fehler, Output-Dir read-only) |
| 3 | Mindestens ein Extractor fehlgeschlagen |
| 4 | Mehrere Boxen via Discovery gefunden — `--host` explizit setzen |
| 5 | Keine Box via Discovery gefunden — `--host` explizit setzen |

---

# fritzreport — HTML-Report aus dem Bundle

Erzeugt **eine** self-contained HTML-Datei: alle Daten eingebettet, Filter setzt der
Betrachter nachträglich im Browser, jede Zeile mit Herkunftsnachweis und Belegtheits-Grad.

## Features

- **Ein self-contained `.html`** je Box — offline lesbar, keine externen Ressourcen, Dark Mode.
- **Alle Rohdaten eingebettet** (jede JSON-Zeile, Supportdaten-Blöcke) plus Auswertungen.
- **Clientseitige Filter** (MAC, Gerätename, Telefonnummer, Zeitraum, Access Point,
  Belegtheits-Grad) — konsistent über alle Sektionen.
- **Belegtheits-Grade D1–D3** je Datenzeile.
- **Herkunftsnachweis** je Zeile: Quelldatei, SHA-256, Fundstelle als Zeilennummer,
  wörtlicher Original-Auszug (zeichengenau, kopierbar).
- **SHA-256-Verifikation** aller Bundle-Dateien gegen ihre Sidecars (Badge ✔/✘).
- **Verbindungsnachweise** aus den Supportdaten — zwei Parser vereint.
- **Quellenübergreifende Timeline** aller zeitgestempelten Daten.
- **Browser-Druck** der gefilterten Sicht mit Filter-Banner + Roh-Report-Hash.

## Nutzung

```
fritzreport [bundle] [-o report.html] [--open]
            [--case-id …] [--item-id …] [--sb …] [--date …] [--no-prompt]
```

**Geführter Ablauf** — ohne Argumente im Verzeichnis mit den Bundles:

```bash
fritzreport
```

- **Auto-Discovery:** sucht fritzexport-Bundles im aktuellen Verzeichnis. Genau eines →
  direkt genommen. Mehrere → nummerierte Auswahl.
- **Kopf-Felder:** Case-ID · Asservat/Item-ID · Sachbearbeiter · Datum (Enter = leer).
  Liegt eine `case.json` im Bundle (von fritzexport geschrieben), belegt sie die
  Abfrage vor; CLI-Argumente überschreiben sie weiterhin.
- **Ausgabe:** `<Case>_<Item>_<Abzugszeitpunkt>.html` im **aktuellen
  Arbeitsverzeichnis** — bewusst *nicht* im Beweismittel-Ordner. Der Name trägt
  denselben Stamm wie das Bundle-Verzeichnis; der Abzugszeitpunkt stammt aus der
  Hülle des Bundles und macht den Namen eindeutig, sodass zwei Abzüge desselben
  Asservats zwei Reports ergeben statt einen überschriebenen.

**Nicht-interaktiv:**

```bash
fritzreport ~/export_20260722T142333Z_7490 \
  --case-id CASE-2026-042 --item-id Asservat-7490 --sb "Müller" --date 2026-07-22 \
  -o /pfad/report.html
```

Per Flag gesetzte Kopf-Felder überspringen die Abfrage; `--no-prompt` erzwingt
nicht-interaktiv; `--open` öffnet den Report danach im Browser.

## Der Report im Browser

Eine einzige HTML-Datei, per Doppelklick zu öffnen, funktioniert offline ohne Server.

- **Sektionen** (12) starten **zugeklappt**; das Inhaltsverzeichnis öffnet und springt.
  Die Kopfzeile zeigt die Trefferzahl auch zugeklappt.
- **Filterleiste** oben, immer sichtbar; Filter wirken clientseitig über alle Sektionen.
  „X von Y ausgeblendet" zeigt die Wirkung, **Zurücksetzen** stellt alles wieder her.
- **Herkunft** je Zeile über das „▸"-Symbol: Quelldatei, SHA-256, Zeilennummer und
  wörtlicher Original-Auszug, per Knopf kopierbar.
- **Sicherungszeitraum** in den Metadaten (Sektion 1): *Gesichert von / bis / Dauer* —
  der erste bis letzte Datenabruf, nicht ein einzelner Zeitpunkt. Neuere Abzüge
  protokollieren ihn im Sitzungslog (Rohdaten-Wiedergabe, kein Badge); bei älteren
  Bundles leitet fritzreport ihn aus den Zeitstempeln der Datensätze ab — die Werte
  selbst stehen so in den signierten Hüllen, abgeleitet ist nur der Schluss auf den
  Zeitraum, daher **D1**. Die *Dauer* ist errechnet und trägt **D3**.
- **Drucken:** „Gefilterte Sicht drucken" druckt nur die sichtbaren Zeilen, mit Banner
  (aktive Filter + Roh-Report-Hash).

## Belegtheits-Grade

Zeilen ohne Badge sind reine Rohdaten-Wiedergabe (impliziter Normalfall). Badges markieren
die besonderen Fälle, kombinierbar:

Schema **v2** (3 Grade). Ältere Unterlagen können ein 4-Grade-Schema nennen, in dem `D3`
„durch eigene forensische Versuche belegt" bedeutete — das entspricht hier `D2`. Die
Umrechnung steht in [ANFORDERUNGEN.md](ANFORDERUNGEN.md), Abschnitt D.

| Grad | Bedeutung |
|------|-----------|
| **D1** | Plausibel innerhalb Rohdaten |
| **D2** | Durch eigene forensische Tests verifiziert |
| **D3** | Abgeleitet / Interpretation |

Grundlage für **D2** ist die Methodik in [ressourcen/methode.md](ressourcen/methode.md).

**Verbindungsnachweise** (Sektion 6): Treffer des Methoden-Parsers tragen **D1+D2**, die aus
den 802.11-Logs **D1+D3**. Beide Parser laufen auf jeder Box, Ergebnisse werden vereint
(dedupliziert nach Zeitpunkt/MAC/Ereignis). Zeitstempel auf die Sekunde angezeigt;
Millisekunden bleiben Sortierschlüssel und stehen im Original-Auszug.

---

# Bundle-Format

Pro Datenart entstehen zwei Dateien:

```
fritzexport_<host>_<timestamp>_<typ>.json
fritzexport_<host>_<timestamp>_<typ>.json.sha256
```

Die JSON-Datei trägt ein einheitliches Hüllformat (`tool`, `version`, `host`,
`extracted_at`, `type`, `records`, optional `discovery`). Der Sidecar liegt im
Standard-`sha256sum`-Format — ein Bundle lässt sich also auch ohne diese Werkzeuge prüfen:

```bash
cd export_20260713T101530Z && cat *.sha256 | sha256sum -c
```

Verifiziert wird ausschließlich der Digest, nicht der Dateiname im Sidecar — ein umbenanntes
Bundle bleibt prüfbar.

Maßgeblich für all das ist `fritzformat/`: `names.py` (Dateinamen, Datenarten),
`envelope.py` (Hüllformat), `digest.py` (Sidecars).

---

# Distribution

Single-file Binaries ohne installiertes Python. Build via GitHub Actions auf Tag-Push;
die Werkzeuge werden **unabhängig voneinander** versioniert:

| Tag | baut |
|---|---|
| `export-v0.3.2` | nur fritzexport |
| `report-v0.1.1` | nur fritzreport |

Lokal:

```bash
python scripts/build.py --tool export    # → dist/fritzexport-<version>-linux-x86_64
python scripts/build.py --tool report    # → dist/fritzreport-<version>-linux-x86_64
python scripts/build.py --tool all
./scripts/build-linux.sh [export|report|all]
```

Empfohlenes Stick-Layout:

```
USB:/
  fritzexport-<version>-linux-x86_64        (chmod +x)
  fritzexport-<version>-windows-x86_64.exe
  fritzreport-<version>-linux-x86_64
  C-2026-0815_A-01_20260713T101530Z/        (Bundle, pro Lauf erstellt)
  C-2026-0815_A-01_20260713T101530Z.html    (Report, gleicher Namensstamm)
```

Das Export-Verzeichnis landet neben dem Binary, nicht im zufälligen `cwd`. Der
PyInstaller-Bootstrap-Extract wird ebenfalls auf den Stick geschrieben
(`--runtime-tmpdir .`), damit keine Spuren auf dem Host bleiben.

**Dateisystem:** NTFS oder exFAT, nicht FAT32.

**Windows-Doppelklick:** das Konsolenfenster bleibt nach Programmende offen
(*"Drücken Sie Enter zum Beenden …"*). Aus CMD/PowerShell entfällt die Pause.

---

# Tests

```bash
python -m pytest              # vollständige Suite, offline, ohne Box
python -m pytest -m golden    # zusätzlich gegen echte Bundles unter ~/testdata
```

Live-LAN-Tests (`@pytest.mark.network`) und Golden-Tests (`@pytest.mark.golden`) sind im
Default-Lauf deselektiert. Die Golden-Tests brauchen echte Bundles, die bewusst **nicht**
im Repo liegen.

Besonders relevant sind die Vertragstests in `tests/format/`: sie halten die
Extractor-Registry und die Datenart-Liste synchron, prüfen den Rundlauf
*schreiben → lesen* über beide Werkzeuge und sichern die stdlib-Freiheit von fritzreport ab.
