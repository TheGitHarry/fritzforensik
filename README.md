# legacy_export

Minimales Python-CLI zum Live-Abzug forensisch relevanter Daten aus einer
laufenden FRITZ!Box: Anrufliste, Telefonbuch, WLAN-Geräteliste,
System-Ereignislog.

Authentifizierung erfolgt über das offizielle AVM Web-UI-SID-Verfahren
(PBKDF2-Challenge-Response, mit MD5-Fallback für ältere Firmware-Stände).

Ergänzt — ersetzt nicht — den Offline-Parser
`backend/scripts/fritz/fritz_processor.py` aus dem Projekt
`it-forensic-automat`, der nur exportierte Support-Daten-ZIPs verarbeitet.

## Installation

```bash
git clone <repo> legacy_export
cd legacy_export
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Nutzung

```bash
export FRITZ_PW='dein-passwort'

python legacy_export.py \
    --host fritz.box \
    --user admin \
    --output ./export/ \
    --all
```

Einzelne Datenarten lassen sich gezielt abziehen:

```bash
python legacy_export.py --host 192.168.178.1 --user admin \
    --output ./export/ --calls --wifi
```

Wird `FRITZ_PW` nicht gesetzt, fragt das Tool das Passwort interaktiv ab
(`getpass`). Das Passwort darf **nie** als CLI-Argument übergeben werden.

## Output

Pro Extractor entstehen zwei Dateien im Ausgabeverzeichnis:

```
legacy_export_<host>_<timestamp>_<typ>.json
legacy_export_<host>_<timestamp>_<typ>.json.sha256
```

Die JSON-Datei enthält ein einheitliches Hüllformat (`tool`, `version`,
`host`, `extracted_at`, `type`, `records`). Der zugehörige `.sha256` ist
ein Sidecar im Standard-`sha256sum`-Format zur späteren
Integritätsprüfung.

## Exit-Codes

| Code | Bedeutung                                           |
|------|-----------------------------------------------------|
| 0    | Alle gewählten Extractoren erfolgreich              |
| 1    | Auth-Fehler (falsches Passwort, Box gesperrt)       |
| 2    | Box nicht erreichbar (Netzwerk/HTTP-Fehler)         |
| 3    | Mindestens ein Extractor fehlgeschlagen             |

## Tests

```bash
python -m pytest tests/
```

Die Tests laufen vollständig offline ohne FRITZ!Box.
