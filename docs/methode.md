# fritz-supportdatas-processor — Entwicklungszusammenfassung

Quellen: zwei nicht öffentliche Vorfassungen (v1, Dezember 2025; formale Fassung,
Januar 2026)  
Maßgeblich: ein **nicht öffentliches Methodenpapier zur forensischen Auswertung von
Router-Supportdaten**, v1.0, Januar 2026. Bei Abweichungen gilt das Methodenpapier.
Herausgeber und Verfasser werden hier bewusst nicht genannt; wer wissen muss, worauf
die Methodik beruht, fragt bitte über ein Issue nach.  
Ziel: FRITZ!Box Supportdaten forensisch auswerten → gerätebezogene Verbindungsnachweise mit Zeitstempeln

---

## Kontext

**Zielformat:** AVM FRITZ!Box Supportdatei (Textdatei)  
**Validiert für:** FRITZ!OS 8.20 auf der Plattform, die das Papier **259** nennt
(Dateiname seiner Testdaten: `support_Fritz.Box_7590_259.08.20.zip`)  

> **Anmerkung dieser Zusammenfassung** — nicht Teil des Papiers: Frühere Fassungen gaben
> das als „Hardware-Plattform 259 (FRITZ!Box 7590)" wieder. Beides ist so nicht haltbar.
> `259` steht im Dateinamen in der Position `<Kennung>.<FRITZ!OS>` des Versionsstrings,
> und diese Kennung ist **nicht** das Feld `HWRevision`: Sie fällt nur auf manchen
> Modellen mit ihm zusammen (7530 AX 256, 7690 285), auf anderen nicht (7590: Kennung 154
> bei `HWRevision` 226; 7490: 113 bei 185) — belegt in
> `test_kennung_im_versionsstring_ist_nicht_die_hwrevision`. Die Box selbst trennt beide
> Größen: In ihrem TR-064-Descriptor (`:49000/tr64desc.xml`) führt eine 7590
> `<HW>226</HW>` neben `<Major>154</Major>` und `<Display>154.08.25</Display>`. Die
> Kennung ist also AVMs **Firmware-Major**. Hinter 259 steht die **FRITZ!Box 7590 AX**:
> Die Supportdateien der Testdaten des Papiers selbst führen `HWRevision 259`,
> `ProductID Fritz_Box_HW259` und `firmware_info 259.08.20`, ihre Dateinamen lauten
> `support_FRITZ.Box_7590_AX_259.08.20_…`. Auf der 7590 AX fallen Kennung und
> `HWRevision` also zusammen, wie auf 7530 AX und 7690. Die 7590 (Kennung 154,
> `HWRevision` 226) ist ein anderes Gerät; die frühere Gleichsetzung mit ihr war falsch.
**Portabilität:** Die Übertragbarkeit auf andere FRITZ!OS-Versionen oder Hardware-Plattformen
wird **nicht vorausgesetzt** und ist im Einzelfall gesondert zu prüfen. Insbesondere die
Plattform 285 (FRITZ!Box 7690) ist **nicht** validiert, auch wenn dafür umfangreiche
Testdaten vorliegen.  
**Rechtsrahmen:** Ergebnis sind technische Hinweise — kein Beweis für kontinuierliche Nutzung oder Personenbezug

---

## Dateistruktur der Supportdatei

Sektionen sind abgegrenzt durch:
```
##### BEGIN SECTION <name>
...
##### END SECTION <name>
```

Ausnahme MESH Shringbuf:
```
===== Mesh Shringbuf Begin =====
...
===== Mesh Shringbuf End =====
```

---

## Verarbeitungs-Pipeline (2 Schritte)

### Schritt 1 — Geräteregister aus `dhcpd`

**Sektion:** `##### BEGIN SECTION dhcpd`

Zweiter Teil der Sektion enthält die Lease-Liste (alle jemals verbundenen Geräte).

**Zeilenformat:**
```
lease|wlease  <MAC>  <IP>  <verbleibende_leasezeit>  <gerätename>  01-<MAC>  ""  static|dynamic
```
- `lease` = LAN-Verbindung
- `wlease` = WLAN-Verbindung

**Extraktion:** MAC + IP + Gerätename → wird Geräteregister (dict: MAC → {name, ip, typ})  
**Rolle:** Grundlage für alle folgenden Schritte — unbekannte MACs werden ignoriert

---

### Schritt 2 — Verbindungsnachweise aus 5 Log-Sektionen

Alle Zeitstempel werden per MAC dem Geräteregister zugeordnet.  
Jeder Nachweis besteht aus: `{mac, timestamp, quelle, vertrauenswuerdig: true}`

---

#### 2a — Sektion `dhcp`

**Sektion:** `##### BEGIN SECTION dhcp`  
**Kapazität:** Max. 37 Einträge (Ringspeicher — älteste werden überschrieben) *(Angabe der Vorfassung, nicht in v1.0)*

**Zeilenformat:**
```
<timestamp>  DHCPD: lan|guest  >>>>|<<<<  <MAC_sender>  <MAC_ziel>  <IP_sender>  <IP_ziel>  <DHCP-Nachricht>
```

**Filterregel:**
- `<<<<` (Gerät → Router) = **vertrauenswürdig** → Verbindungsnachweis
- `>>>>` (Router → Gerät) = **ignorieren** (keine Empfangsbestätigung in Logs)

**Extrahierte Felder:** Timestamp, sendende MAC (erste der zwei MACs)

---

#### 2b — Sektion `STATION_MODULE`

**Sektion:** `##### BEGIN SECTION STATION_MODULE Module for station informations`  
**Inhalt:** Zwei Listen — aktuell verbundene + ehemals verbundene Geräte

Jeder Eintrag beginnt mit **MAC** des Geräts, endet mit **Connect History** (max. 50 Einträge, Ringspeicher — Angabe der Vorfassung, nicht in v1.0).

**Ringspeicher-Reihenfolge:** Neuester Eintrag unten, zweitältester oben, dann absteigend zeitlich nach unten.

**Connect History Zeilenformat:**
```
<ts_verbindung>  [<uptime>]  <status_verbindung>  <ts_trennung>  [<uptime>]  <status_trennung>  <qualität>  <modus>
```

**Filterregel (Status-Code):**
- Status `1` kennzeichnet einen eingehenden Verbindungsnachweis → Timestamp **vertrauenswürdig**. Aussage laut Papier: Das Gerät hat zu diesem Zeitpunkt erfolgreich mit dem Netzwerk kommuniziert — **nicht**, dass eine Person gehandelt hat.
- Jeder andere Status (z.B. `4`) → Timestamp **ignorieren**; laut Papier ein Verbindungsabbruch, der zeitlich nicht bestimmbar ist
- Gilt **für An- und Abmeldung separat** — je Timestamp unabhängig prüfen

**Sonderfall (noch verbunden):** Nur Anmeldungs-Timestamp vorhanden → einmaligen Nachweis extrahieren

---

#### 2c — Sektion `WLAN_EVENTS`

**Sektion:** `##### BEGIN SECTION WLAN_EVENTS Filtered Events`  
**Kapazität:** Max. 100 Einträge *(Angabe der Vorfassung, nicht in v1.0)*

**Spalten:** `time`, `mac`, `id`, `details`

**Filterregel (id):**
| ID | Bedeutung | Wertung |
|----|-----------|---------|
| `30005` | Anmeldung | vertrauenswürdig |
| `752` | Abmeldung | vertrauenswürdig |
| `754` | Verbindungsverlust | **ignorieren** |

Die Bedeutungsspalte stammt aus der Vorfassung. v1.0 sagt nur: `30005` und `752` sind Verbindungsnachweise (das Gerät hat erfolgreich kommuniziert); andere IDs weisen auf fehlende oder fehlerhafte Kommunikation hin, die zeitlich nicht zuverlässig bestimmbar ist.

> Hinweis: `details`-Feld ist versionsübergreifend stabil, `id` kann sich zwischen FRITZ!OS-Versionen ändern

---

#### 2d — Sektion `Events Events`

**Sektion:** `##### BEGIN SECTION Events Events`  
**Kapazität:** Max. **16 Einträge** (sehr begrenzt) *(Angabe der Vorfassung, nicht in v1.0)* — laut v1.0 **meist** nur Erstanmeldungen

**Filterregel:** Einträge die Gerätename **und** MAC nennen + Aktionstext "hat sich mit FRITZ!Box verbunden" (o.ä.)  
Alle anderen Einträge der Sektion ignorieren.

**Extrahierte Felder:** Timestamp, MAC aus Eintragstext

---

#### 2e — Untersektion `MESH Shringbuf`

**Marker:** `===== Mesh Shringbuf Begin =====`  
**Kapazität:** Max. 384 Zeilen *(Angabe der Vorfassung, nicht in v1.0)*

Zwei vertrauenswürdige Eintragstypen:

| Muster | Verbundenes Gerät |
|--------|-------------------|
| `WSS_select_target: rate_link():136:` | **zweite** genannte MAC |
| `SC: handle_steering_result():801:` | **erste** genannte MAC |

**Filterregel:**  
Nur Einträge mit RX **und** TX ≠ 0 → Timestamp als Verbindungsnachweis  
Bei RX = 0 und TX = 0 → **ignorieren**

---

## Output-Struktur (je Gerät)

> Feldnamen im tatsächlichen JSON-Output (englisch, konsistent mit ESB-Result-Schema):

```json
{
  "mac": "aa:bb:cc:dd:ee:ff",
  "name": "iPhone-Harry",
  "ip": "192.168.178.42",
  "connection_type": "wlan",
  "source": "dhcpd",
  "event_count": 2,
  "events": [
    {
      "timestamp": "2025-12-01T10:23:00",
      "source": "STATION_MODULE",
      "event_type": "connect"
    },
    {
      "timestamp": "2025-12-01T10:45:00",
      "source": "WLAN_EVENTS",
      "event_type": "disconnect"
    }
  ]
}
```

`connection_type`-Werte: `"lan"`, `"wlan"`, `"wlan_guest"`

---

## Warum zwei Parser laufen (empirischer Befund)

`fritzreport` wertet die Supportdaten auf **zwei** Wegen aus: nach dieser Methodik
(→ D1+D2) und zusätzlich über die 802.11-Logs (→ D1+D3). Der Grund ist eine
Marker-Zählung über vier Testboxen — **kein Weg allein genügt**:

| Box | Treffer nach dieser Methodik (D1+D2) | 802.11-Treffer (D1+D3) | Interface |
|-----|---:|---:|---|
| 7530ax | 1958 | 238 | `wl0/wl1` (Broadcom) |
| 7690 | 1401 | 21 | `ath0/1` (Atheros) |
| 7590 | 1937 | 0 | nur Zähler, keine Einzel-Events |
| 7490 | 1840 | 0 | nur Kernel-Tick-Logs (keine Wall-Clock) |

Beide Parser laufen auf jeder Box, die Ergebnisse werden vereint und dedupliziert
(Schlüssel: Sekunde, MAC, Ereignis); der Belegtheits-Grad richtet sich nach der
Herkunft. Auf 7590 und 7490 liefert der 802.11-Weg **nichts** — dort tragen die
Nachweise ausschließlich diese Methodik.

---

## Forensische Einschränkungen (für Gutachten relevant)

| Einschränkung | Quelle |
|--------------|--------|
| Keine lückenlose Erfassung — Ringpuffer überschreiben alte Daten | dhcp (37), STATION_MODULE (50), WLAN_EVENTS (100), Events (16), MESH (384) — Größen aus der Vorfassung, nicht in v1.0 |
| Geräte mit statischer IP tauchen in DHCP-Logs ggf. nicht auf | dhcp, dhcpd |
| Status ≠ 1 → Zeitpunkt nicht bestimmbar (Verbindungsabbruch) | STATION_MODULE |
| Events Events: meist nur Erstanmeldungen | Events Events |
| Kein Personenbezug aus MAC allein ableitbar | alle |
| Methodik validiert nur für FRITZ!OS 8.20 auf der Plattform 259 des Papiers (FRITZ!Box 7590 AX, siehe Anmerkung unter *Kontext*); Übertragbarkeit auf andere Versionen/Plattformen im Einzelfall zu prüfen | alle |
