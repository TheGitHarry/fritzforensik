# legacy_export

Python-CLI zum Live-Abzug forensisch relevanter Daten aus einer laufenden
FRITZ!Box. Deckt Anrufliste, Telefonbuch, WLAN-Geräteliste, Ereignislog
(alle Kategorien), Anrufbeantworter, Mesh-Topologie, Hosts, WAN-Status,
DHCP-Konfiguration, Port-Forwards, USB-Storage, erweiterte Supportdaten
und TR-069-Konfiguration ab.

Authentifizierung über das offizielle AVM Web-UI-SID-Verfahren
(PBKDF2-Challenge-Response, mit MD5-Fallback für ältere Firmware-Stände).
Die Box wird per SSDP-Auto-Discovery im LAN gefunden, kann aber auch
explizit per `--host` adressiert werden.

Ergänzt — ersetzt nicht — den Offline-Parser
`backend/scripts/fritz/fritz_processor.py` aus dem Projekt
`it-forensic-automat`, der nur exportierte Support-Daten-ZIPs verarbeitet.

## Installation (Entwicklung)

```bash
git clone <repo> legacy_export
cd legacy_export
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Für den Feldeinsatz von einem USB-Stick gibt es vorgefertigte
single-file Binaries für Linux und Windows — siehe Abschnitt
"USB-Stick-Distribution" weiter unten.

## Nutzung

Ohne Argumente: Auto-Discovery läuft, bei genau einer Box wird direkt
nach Benutzername und Passwort gefragt und der vollständige Abzug startet:

```bash
./legacy_export
```

Bei mehreren Boxen im Netz erscheint eine nummerierte Auswahlliste mit
zusätzlicher Option *"keine"* (= Abbruch). Auswahl per Nummer + Enter,
dann läuft der Abzug für die gewählte Box weiter. Alternativ Box
explizit per `--host` adressieren:

```bash
export FRITZ_PW='dein-passwort'
python legacy_export.py --host 192.168.178.1 --user admin
```

Einzelne Datenarten gezielt abziehen:

```bash
python legacy_export.py --host 192.168.178.1 --user admin --calls --wifi --tr069
```

Nur Discovery (JSON-Liste auf stdout, z.B. für Scripting):

```bash
python legacy_export.py --discover
```

Wird `FRITZ_PW` nicht gesetzt, fragt das Tool das Passwort interaktiv ab
(`getpass`). Das Passwort darf **nie** als CLI-Argument übergeben werden.

`--host` akzeptiert sowohl `fritz.box` als auch explizit
`https://192.168.178.1`. Selbstsignierte Box-Zertifikate werden beim
Verbindungsaufbau automatisch erkannt — das Tool schaltet dann
selbstständig auf TLS ohne Verifikation um (Logmeldung: *"TLS-Zertifikat
der Box ist nicht vertrauenswürdig … schalte automatisch auf --insecure
um."*). `--insecure` lässt sich bei Bedarf weiterhin explizit setzen.

`--iface` setzt die Source-IP für SSDP-Multicast bei Multi-Interface-Hosts
(z.B. `--iface 192.168.2.228`).

`--output` ist optional: Default ist `./export/` neben dem Skript bzw.
neben dem PyInstaller-Binary. Pro Lauf wird eine Logdatei
`legacy_export_<timestamp>.log` im selben Verzeichnis abgelegt.

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

Ohne explizite Auswahl werden alle Extractoren ausgeführt (`--all`).

### TR-064-Abhängigkeit

Extractoren die TR-064 nutzen (`--wan`, `--dhcp`, `--portforward`,
`--storage`, `--tr069`) benötigen:
*Heimnetz → Netzwerk → Netzwerkeinstellungen → "Zugriff für Anwendungen
zulassen"* + *"Statusinformationen über UPnP übertragen"*.

Ist TR-064 beim Start nicht erreichbar, erscheint eine Warnung mit der
Liste der betroffenen Extractoren. Extractoren mit Web-UI-Fallback (`--tam`,
`--mesh`) laufen in jedem Fall durch.

### Anrufbeantworter (`--tam`)

Audio-Aufnahmen werden als WAV in das Subverzeichnis `tam_audio/`
geschrieben. Zwei Wege werden unterstützt:

- **Primär TR-064** (`X_AVM-DE_TAM:1`): Der `<New>`-Flag jeder Nachricht
  wird vor und nach dem Download erfasst; falls die Box implizit auf
  "gelesen" markiert, wird der Status über `MarkMessage(MarkedAsRead=0)`
  wiederhergestellt (`tam_state_preserved: true`).
- **Fallback Web-UI**: Wird aktiv wenn TR-064 deaktiviert ist. Read-Status
  kann nicht zurückgesetzt werden (`tam_state_preserved: false`).

### Ereignislog (`--events`)

Der Extractor ruft alle Filterkategorien ab (`all`, `sys`, `net`, `wlan`,
`fon`, `usb`) und dedupliziert nach `(date, time, message)`. Jeder Eintrag
enthält ein `found_in_filters`-Array — Einträge die eine Firmware nur in
einer Kategorie liefert, gehen nicht verloren.

### Erweiterte Supportdaten (`--supportdata`)

POST auf `/cgi-bin/firmwarecfg` (multipart). Kein TR-064 erforderlich.
Drei Varianten werden nacheinander gezogen:

1. `SupportData` — Standard-Diagnosebericht.
2. `MeshSupportData` — Mesh-Topologie-Diagnose.
3. `SupportDataEnhanced` — erweiterter Bericht. **Erfordert physische
   Bestätigung an der Box**: ein beliebiger Knopf an der FRITZ!Box
   drücken und im Web-UI-Dialog auf OK klicken. Das Tool zeigt einen
   30-s-Countdown auf der Konsole; läuft die Zeit ab, wird nur diese
   Variante übersprungen, die anderen beiden bleiben erhalten.

Pro Variante wird die Rohdatei als `supportdata_<typ>_<ts>.txt` plus
`.sha256`-Sidecar im Output-Verzeichnis abgelegt; das JSON-Record
enthält Typ, Dateiname, Größe und Hash. `extra_meta` listet
`supportdata_fetched` und `supportdata_missing`, sodass im Bericht
sichtbar bleibt, welche Variante (z.B. der Enhanced-Dump bei Timeout)
fehlt.

### TR-069-Konfiguration (`--tr069`)

Liest via TR-064 `ManagementServer:1#GetInfo` die TR-069-Konfiguration:
ACS-URL (ISP-Fernwartungsserver), ob Fernwartung aktiv ist, Verbindungs-
intervall und ConnectionRequestURL. Ist TR-064 nicht verfügbar, gibt der
Extractor eine leere Liste zurück.

## Output

Pro Extractor entstehen zwei Dateien:

```
legacy_export_<host>_<timestamp>_<typ>.json
legacy_export_<host>_<timestamp>_<typ>.json.sha256
```

Die JSON-Datei enthält ein einheitliches Hüllformat (`tool`, `version`,
`host`, `extracted_at`, `type`, `records`, optional `discovery`). Der
`.sha256`-Sidecar liegt im Standard-`sha256sum`-Format zur
Integritätsprüfung.

## USB-Stick-Distribution

Single-file Binaries für Linux und Windows x86_64 ohne installiertes
Python. Build via GitHub Actions auf Tag-Push (`v*`); Artefakte sind am
jeweiligen Tag hinterlegt.

Lokaler Build:

```bash
python scripts/build.py
# Ergebnis: dist/legacy_export-<version>-linux-x86_64
#           dist/legacy_export-<version>-windows-x86_64.exe  (nur auf Windows)
```

Empfohlenes Stick-Layout:

```
USB:/
  legacy_export-<version>-linux-x86_64       (chmod +x)
  legacy_export-<version>-windows-x86_64.exe
  export/                                     (wird automatisch erstellt)
```

`export/` landet neben dem Binary, nicht im zufälligen `cwd`. Der
PyInstaller-Bootstrap-Extract wird ebenfalls auf den Stick geschrieben
(`--runtime-tmpdir .`), damit keine Spuren auf dem Host-System bleiben.

**Empfehlung Dateisystem**: NTFS oder exFAT, nicht FAT32.

**Start per Doppelklick (Windows)**: das Binary öffnet beim Doppelklick
ein Konsolenfenster, das nach Programmende **offen bleibt** (Hinweis
*"Drücken Sie Enter zum Beenden …"*). Aus CMD/PowerShell heraus
gestartet entfällt diese Pause. Auf Linux ist Doppelklick-Verhalten
Sache des Dateimanagers — das Tool wird dort üblicherweise direkt aus
dem Terminal gestartet.

## Exit-Codes

| Code | Bedeutung |
|------|-----------|
| 0 | Alle gewählten Extractoren erfolgreich |
| 1 | Auth-Fehler (falsches Passwort, Box gesperrt) |
| 2 | Box nicht erreichbar (Netzwerk/HTTP-Fehler, Output-Dir read-only) |
| 3 | Mindestens ein Extractor fehlgeschlagen |
| 4 | Mehrere Boxen via Discovery gefunden — `--host` explizit setzen |
| 5 | Keine Box via Discovery gefunden — `--host` explizit setzen |

## Tests

```bash
python -m pytest
```

Die Tests laufen vollständig offline ohne FRITZ!Box. Live-LAN-Tests sind
als `@pytest.mark.network` markiert und im Default-Lauf deselektiert.
