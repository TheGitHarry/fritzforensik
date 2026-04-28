# legacy_export

Minimales Python-CLI zum Live-Abzug forensisch relevanter Daten aus einer
laufenden FRITZ!Box: Anrufliste, Telefonbuch, WLAN-Geräteliste,
System-Ereignislog, Anrufbeantworter-Aufnahmen.

Authentifizierung erfolgt über das offizielle AVM Web-UI-SID-Verfahren
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

Auto-Discovery (kein `--host` nötig, wenn nur eine Box im LAN ist):

```bash
export FRITZ_PW='dein-passwort'
python legacy_export.py --user admin --all
```

Mit explizitem Host (z.B. wenn mehrere Boxen im Netz sind oder UPnP
deaktiviert ist):

```bash
python legacy_export.py --host https://192.168.178.1 --user admin --all
```

Einzelne Datenarten gezielt abziehen:

```bash
python legacy_export.py --host 192.168.178.1 --user admin --calls --wifi
```

Nur Discovery laufen lassen (für Setup-Sanity-Check, JSON-Liste auf stdout):

```bash
python legacy_export.py --discover
```

Wird `FRITZ_PW` nicht gesetzt, fragt das Tool das Passwort interaktiv ab
(`getpass`). Das Passwort darf **nie** als CLI-Argument übergeben werden.

`--host` akzeptiert sowohl `fritz.box` (Default-Schema `http://`, kann zur
HTTPS-Umleitung führen) als auch explizit `https://192.168.178.1`. Bei
Boxen mit selbstsigniertem oder eigener-CA-signiertem Zertifikat (das im
System-Trust-Store nicht hinterlegt ist) bricht die TLS-Prüfung sonst ab —
in dem Fall `--insecure` setzen.

`--iface` setzt die Source-IP für SSDP-Multicast bei Multi-Interface-Hosts
(z.B. `--iface 192.168.2.228`). IPv6-Discovery wird derzeit nicht
unterstützt.

`--output` ist optional: Default ist `./export/` neben dem Skript bzw.
neben dem PyInstaller-Binary. Pro Lauf wird zusätzlich eine Logdatei
`legacy_export_<timestamp>.log` im selben Verzeichnis abgelegt.

## Output

Pro Extractor entstehen zwei Dateien im Ausgabeverzeichnis:

```
legacy_export_<host>_<timestamp>_<typ>.json
legacy_export_<host>_<timestamp>_<typ>.json.sha256
```

Die JSON-Datei enthält ein einheitliches Hüllformat (`tool`, `version`,
`host`, `extracted_at`, `type`, `records`, optional `discovery`). Bei
Auto-Discovery ist im `discovery`-Feld die Roh-Antwort der Box als
Audit-Trail abgelegt (`discovery_method: "ssdp"` oder `"manual"`). Der
zugehörige `.sha256` ist ein Sidecar im Standard-`sha256sum`-Format zur
späteren Integritätsprüfung.

### Anrufbeantworter (`--tam`)

Audio-Aufnahmen werden als WAV in das Subverzeichnis `tam_audio/`
geschrieben (Dateiname `tam<slot>_msg<index>.wav`); pro Nachricht steht
im JSON-Record der relative Pfad und die SHA256-Prüfsumme der
Audio-Bytes. Es werden zwei Wege unterstützt:

- **Primär TR-064** (`X_AVM-DE_TAM:1` auf Port 49000, HTTP Digest mit
  Box-User/Passwort). Vor und nach dem Audio-Download wird der
  `<New>`-Flag jeder Nachricht erfasst; falls die Box implizit auf
  "gelesen" markiert, wird über `MarkMessage(MarkedAsRead=0)` der
  ursprüngliche Status wiederhergestellt. Im Hüllformat:
  `tam_method: "tr064"`, `tam_state_preserved: true/false`,
  `tam_state_mutations: [...]`.
- **Fallback Web-UI** (über die SID-Auth des bestehenden Stacks). Wird
  nur aktiv, wenn TR-064 auf der Box deaktiviert ist (UPnPError 401/606
  ohne `WWW-Authenticate`-Challenge). In dem Fall ist
  `tam_state_preserved: false` und `tam_state_warning` dokumentiert,
  dass der read-Status nicht zurückgesetzt werden kann.

**TR-064 aktivieren** (für die forensisch saubere Variante):
*Heimnetz → Netzwerk → Netzwerkeinstellungen → "Zugriff für Anwendungen
zulassen"* + *"Statusinformationen über UPnP übertragen"*.

## USB-Stick-Distribution

Für den Forensik-Feldeinsatz gibt es single-file Binaries (Linux und
Windows x86_64), die ohne installiertes Python auskommen. Build per
GitHub Actions auf Tag-Push (`v*`); Artefakte sind am Release angeheftet.

Lokaler Build (Linux):

```bash
bash scripts/build-linux.sh
# Ergebnis: dist/legacy_export-<version>-linux-x86_64
```

Lokaler Build (Windows):

```cmd
scripts\build-windows.bat
REM Ergebnis: dist\legacy_export-<version>-windows-x86_64.exe
```

Empfohlenes Stick-Layout:

```
USB:/
  legacy_export-<version>-linux-x86_64       (chmod +x)
  legacy_export-<version>-windows-x86_64.exe
  export/                                     (wird automatisch erstellt)
```

Beim Doppelklick-Start landet `export/` neben dem Binary, nicht im
zufälligen `cwd`. Der PyInstaller-Bootstrap-Extract wird ebenfalls auf
den Stick geschrieben (`--runtime-tmpdir .`), damit zero Spuren auf dem
Host-System bleiben — Trade-off: erstmaliger Cold-Start dauert wenige
Sekunden länger als bei Extract nach `/tmp`.

**Empfehlung Dateisystem**: NTFS oder exFAT, nicht FAT32 (4-GB-Limit
und keine Sonderzeichen-Toleranz, falls Captures größer werden).

## Exit-Codes

| Code | Bedeutung                                                       |
|------|-----------------------------------------------------------------|
| 0    | Alle gewählten Extractoren erfolgreich                          |
| 1    | Auth-Fehler (falsches Passwort, Box gesperrt)                   |
| 2    | Box nicht erreichbar (Netzwerk/HTTP-Fehler, Output-Dir read-only) |
| 3    | Mindestens ein Extractor fehlgeschlagen                         |
| 4    | Mehrere Boxen via Discovery gefunden — `--host` explizit setzen |
| 5    | Keine Box via Discovery gefunden — `--host` explizit setzen     |

## Tests

```bash
python -m pytest
```

Die Tests laufen vollständig offline ohne FRITZ!Box (auth-Vektoren und
SSDP-Parser/-Discovery mit gemocktem Socket). Live-LAN-Tests sind als
`@pytest.mark.network` markiert und im Default-Lauf deselektiert.
