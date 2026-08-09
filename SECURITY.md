# Sicherheitslücken melden

## Wohin

**Bitte nicht als öffentliches Issue.** Meldungen laufen über
[GitHub Security Advisories](https://github.com/TheGitHarry/fritzforensik/security/advisories/new)
— dort ist der Vorgang privat, bis er behoben ist.

Hilfreich sind: betroffenes Werkzeug und Version (`--version`), Firmware- und
Modellstand der Box, und wie sich das Verhalten reproduzieren lässt.

Dies ist ein Freizeit-/Feldprojekt ohne Bereitschaftsdienst — eine Antwort kann
einige Tage dauern.

## Was unterstützt wird

Nur der jeweils neueste Release beider Werkzeuge. Ältere Stände werden nicht
nachgepflegt.

## Was *keine* Meldung wert ist

Ein paar Eigenschaften sehen nach Schwachstelle aus, sind aber Zweck des
Werkzeugs:

- **fritzexport überträgt Box-Zugangsdaten.** Es meldet sich an der Box an —
  ohne Anmeldung kein Abzug. Das Verfahren ist AVMs eigenes
  (PBKDF2-Challenge-Response, MD5-Fallback für ältere Firmware); das Passwort
  geht nicht im Klartext über das Netz.
- **Die Zertifikatsprüfung wird bei selbstsignierten Box-Zertifikaten
  automatisch abgeschaltet.** FRITZ!Boxen verwenden im Auslieferungszustand
  selbstsignierte Zertifikate; erkennt `fritzexport` das, schaltet es von
  selbst auf `--insecure` um und schreibt eine Warnung ins Sitzungslog
  (`_probe_tls` in `fritzexport/cli.py`). Das ist Absicht — sonst wäre kein
  Abzug einer unveränderten Box möglich. Es bedeutet aber, dass die
  TLS-Verbindung zur Box nicht gegen einen Man-in-the-Middle im selben Netz
  schützt; die forensische Sicherung setzt einen kontrollierten Netzzugang
  voraus.
- **Abzüge und Reports enthalten personenbezogene Daten** — Anrufe,
  Telefonbuch, Gerätenamen, MAC-Adressen. Das ist der Zweck einer forensischen
  Sicherung. Ihr Schutz liegt bei dem, der sie erstellt und aufbewahrt; die
  Werkzeuge verschlüsseln nichts.
- **Der HTML-Report führt JavaScript aus** (Filter, Sortierung). Er ist
  self-contained, lädt nichts nach und stellt keine Netzverbindung her.

## Umgang mit Boxdaten in einer Meldung

Ein Abzug enthält echte personenbezogene Daten. Bitte **keine vollständigen
Bundles, Reports oder Supportdaten** anhängen — ein anonymisierter Auszug der
betroffenen Stelle genügt in aller Regel.
