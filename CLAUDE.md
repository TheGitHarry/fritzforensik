# CLAUDE.md

## Was das Projekt macht

`legacy_export` ist eine Python-CLI zum **Live-Abzug forensisch relevanter
Daten aus einer laufenden FRITZ!Box** (im Gegensatz zum Offline-Parser
`fritz_processor.py` aus `it-forensic-automat`, der nur exportierte
Support-ZIPs verarbeitet).

Abgedeckt sind: Anrufliste, Telefonbücher, WLAN-Geräte, Ereignislog,
Anrufbeantworter (inkl. Audio), Mesh-Topologie, Hosts, WAN/DSL, DHCP,
Port-Forwards, USB-Storage, erweiterte Supportdaten, TR-069-Konfig.

## Wie es das macht

- **Auth**: AVM Web-UI-SID-Verfahren (PBKDF2-Challenge-Response,
  MD5-Fallback für ältere Firmware) — siehe [auth.py](legacy_export/auth.py).
- **Discovery**: SSDP-Multicast im LAN; bei genau einer Box automatischer
  Login, sonst muss `--host` gesetzt werden — siehe [discover.py](legacy_export/discover.py).
- **Protokolle**: Primär TR-064 (SOAP über UPnP), mit Web-UI-Fallback wo
  möglich. Reine Web-UI-Pfade für Daten ohne TR-064-Pendant
  (Anrufliste, Telefonbuch, Events, Supportdaten).
- **Extractoren**: Ein Modul pro Datenart in [legacy_export/extractors/](legacy_export/extractors/),
  CLI-Glue in [cli.py](legacy_export/cli.py).
- **Output**: Pro Extractor eine JSON-Datei mit Hüllformat
  (`tool`/`version`/`host`/`extracted_at`/`type`/`records`) plus
  SHA256-Sidecar — siehe [output.py](legacy_export/output.py).
- **Distribution**: Single-file PyInstaller-Binaries für Linux x86_64,
  Linux aarch64, Linux armv7, Windows x86_64 — gedacht für USB-Stick-
  Feldeinsatz ohne installiertes Python.

## GitHub-Workflow

**Eine Workflow-Datei**: [.github/workflows/release.yml](.github/workflows/release.yml).
Trigger:
- Push eines Tags `v*` (= Release-Build)
- `workflow_dispatch` (manueller Trigger)

**Kein** CI-Lauf auf normalen Pushes oder Pull-Requests — Tests laufen nur
als Teil des Release-Builds (`python -m pytest` vor jedem PyInstaller-Run).
Schlägt der Test-Step fehl, gibt es kein Artefakt.

**Build-Matrix**:

| Job | Runner | Artefakt |
|---|---|---|
| `build` (x86_64) | `ubuntu-22.04` | `legacy_export-<v>-linux-x86_64` |
| `build` (aarch64) | `ubuntu-22.04-arm` | `legacy_export-<v>-linux-aarch64` |
| `build` (windows) | `windows-2022` | `legacy_export-<v>-windows-x86_64.exe` |
| `build-arm32` | `ubuntu-22.04` + QEMU (`uraimo/run-on-arch-action`) | `legacy_export-<v>-linux-armv7l` |

`fail-fast: false` — schlägt eine Plattform fehl, laufen die anderen
trotzdem durch. Artefakte landen pro Job als `actions/upload-artifact@v4`,
nicht als GitHub-Release; Release-Anlage erfolgt manuell.

### Release auslösen

1. **Erst Version hochzählen** in [legacy_export/__init__.py](legacy_export/__init__.py)
   *und* [pyproject.toml](pyproject.toml). Beide Stellen müssen synchron
   bleiben — `scripts/build.py` zieht die Version aus `__init__.py`, der
   Paketname kommt aus `pyproject.toml`.
2. Commit der Version-Bumps.
3. Tag setzen und pushen: `git tag v0.2.x && git push --tags`.
4. Matrix-Build läuft automatisch; Artefakte werden im Actions-Run abgelegt.

### Stolperfallen im Build

- **`--runtime-tmpdir .`** wird in [scripts/build.py](scripts/build.py)
  nur auf Nicht-Windows-Plattformen gesetzt: auf Windows knallt der
  Bootstrap-Extract im Drive-Root (`F:\`) wegen fehlender Permissions.
- **certifi** wird via `--collect-data certifi` ins Binary gebündelt
  (TLS gegen FRITZ!Box mit selbstsigniertem Cert sonst kaputt).
- Tests sind **offline** (`@pytest.mark.network` ist per default
  deselectet via `pyproject.toml`), CI braucht keinen Box-Zugriff.

## Lokale Tests

```bash
python -m pytest
```

## Konventionen

- Sprache der Doku, Logmeldungen, Fehlermeldungen: **Deutsch**.
- Code-Identifier, JSON-Feldnamen: Englisch.
- Forensik-Prinzip: **nichts auf der Box verändern**. Wo das Lesen
  Status verändert (z.B. TAM-Read-Flag), wird der Originalstatus per
  Restore-Aufruf wiederhergestellt und im Record dokumentiert.
