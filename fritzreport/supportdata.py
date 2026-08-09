"""Supportdaten-Auswertung — Verbindungsnachweise (Sektion 6).

Zwei Wege, beide auf jeder Box, Ergebnisse vereint:

1. **methode.md-Parser** — übernommen aus dem `fritz`-Worker des it-forensic-automat
   (`_material/supportdata-methode/fritz_processor.py`, Methodik `methode.md`).
   Geräteregister aus `dhcpd`, Verbindungsnachweise aus 5 Log-Sektionen mit
   Vertrauensregeln. Empirisch nötig auf Boxen mit WLAN_EVENTS-ID 30005 (7530ax/7590).
   → Grade **D1+D2** (plausibel + durch Tests verifizierte Methode).

2. **802.11-Log-Parser** — übernommen aus dem HTML-Report-PoC. Zeilen
   `… - ath0|ath1: STA <mac> IEEE 802.11: associated/…`. Nötig auf Boxen ohne
   ID 30005 (7690/7490). → Grade **D1+D3** (plausibel + abgeleitet/Skizze).

Der Automat-Klebstoff (job-dict, forensic.results, Geräte-Filter, process/main) ist
bewusst weggelassen — hier zählt nur die reine Methode.
"""
from __future__ import annotations

import re
from datetime import datetime

# ───────────────────────── Konstanten / Regexes (aus fritz_processor.py) ─────

MAC_RE = re.compile(r"[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}")

TS_ISO_RE       = re.compile(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}")
TS_GER_FULL_RE  = re.compile(r"\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}:\d{2}")
TS_GER_SHORT_RE = re.compile(r"\d{2}\.\d{2}\.\d{2}\s+\d{2}:\d{2}:\d{2}")
WLAN_TS_RE      = re.compile(r"(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})")

EV_WLAN_INLINE_RE = re.compile(
    r"^(\d{2}\.\d{2}\.\d{2}\s+\d{2}:\d{2}:\d{2})"
    r"(?:\s+\[([^\]]+)\])?"
    r"\s+(WLAN-Gerät\s+.*?)"
    r",\s+MAC\s+([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})")
EV_FAILED_RE = re.compile(
    r"^(\d{2}\.\d{2}\.\d{2}\s+\d{2}:\d{2}:\d{2})"
    r"(?:\s+\[([^\]]+)\])?"
    r"\s+(.*?(?:gescheitert|fehlgeschlagen|Schlüssel).*?)"
    r"MAC(?:-Adresse)?:?\s*([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})")
EV_OLD_RE = re.compile(
    r"^(\d{2}\.\d{2}\.\d{2}\s+\d{2}:\d{2}:\d{2})"
    r".*?MAC:\s+([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})"
    r".*?verbunden")
FREQ_RE    = re.compile(r"\((\d[,\d]*\s*GHz)\)")
EV_NAME_RE = re.compile(r"\(\d[,\d]* GHz\),\s+(?:\d+ Mbit/s,\s+)?([^,]+),\s+IP")

_TS_RE_ISO   = re.compile(r"^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})")
_TS_RE_DE_4Y = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}):(\d{2}):(\d{2})$")
_TS_RE_DE_2Y = re.compile(r"^(\d{2})\.(\d{2})\.(\d{2})\s+(\d{2}):(\d{2}):(\d{2})$")


# ───────────────────────── Helfer (aus fritz_processor.py) ───────────────────

def extract_timestamp(line):
    for rx in (TS_ISO_RE, TS_GER_FULL_RE, TS_GER_SHORT_RE):
        m = rx.search(line)
        if m:
            return m.group(0)
    return ""


def parse_wlan_timestamp(line):
    m = WLAN_TS_RE.search(line)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)} {m.group(4)}:{m.group(5)}:{m.group(6)}"
    return ""


def extract_section(text, begin_marker, end_marker):
    start = text.find(begin_marker)
    if start == -1:
        return None
    start = text.find("\n", start) + 1
    end = text.find(end_marker, start)
    return text[start:] if end == -1 else text[start:end]


def extract_section_ln(text, begin_marker, end_marker):
    start = text.find(begin_marker)
    if start == -1:
        return None, None
    start = text.find("\n", start) + 1
    end = text.find(end_marker, start)
    section = text[start:] if end == -1 else text[start:end]
    return section, text[:start].count("\n") + 1


def parse_event_ts(ts):
    """FRITZ-Zeitstempel → naives datetime (oder None)."""
    if not ts or ts in ("—", "-"):
        return None
    s = str(ts).strip()
    m = _TS_RE_ISO.match(s)
    if m:
        y, mo, d, h, mi, se = (int(g) for g in m.groups())
        try:
            return datetime(y, mo, d, h, mi, se)
        except ValueError:
            return None
    m = _TS_RE_DE_4Y.match(s)
    if m:
        d, mo, y, h, mi, se = (int(g) for g in m.groups())
        try:
            return datetime(y, mo, d, h, mi, se)
        except ValueError:
            return None
    m = _TS_RE_DE_2Y.match(s)
    if m:
        d, mo, yy, h, mi, se = (int(g) for g in m.groups())
        try:
            return datetime(2000 + yy, mo, d, h, mi, se)
        except ValueError:
            return None
    return None


def _classify_event(event_text):
    t = event_text.lower()
    is_guest = "gastzugang" in t
    if "gescheitert" in t or "fehlgeschlagen" in t or "schlüssel" in t:
        return "failed_connect", is_guest
    if "abgemeldet" in t:
        return "disconnect", is_guest
    if "angemeldet" in t:
        return "connect", is_guest
    if "umgemeldet" in t:
        return "steering", is_guest
    return "unknown", is_guest


# ───────────────────────── methode.md-Sektions-Parser ────────────────────────
# 1:1 aus fritz_processor.py (parse_dhcpd / dhcp / station_module / wlan_events /
# events_events / mesh_shringbuf / station_list). Sie füllen devices[mac]["events"]
# mit {timestamp, source, event_type, log_line_nr, log_line}.

def parse_dhcpd(text):
    section = extract_section(text, "##### BEGIN SECTION dhcpd", "##### END SECTION dhcpd")
    if not section:
        return {}
    guest_start = section.find("\n       is guest\n")
    if guest_start == -1:
        guest_start = section.find("\nSERVER guest:")
    devices = {}
    lease_re = re.compile(r"^(w?lease)\s+([0-9a-fA-F:]{17})\s+(\S+)\s+\S+\s+(\S+)", re.MULTILINE)
    for m in lease_re.finditer(section):
        mac, ip, name = m.group(2).lower(), m.group(3), m.group(4).strip('"')
        if m.group(1) == "wlease":
            conn = "wlan_guest" if (guest_start != -1 and m.start() > guest_start) else "wlan"
        else:
            conn = "lan"
        devices[mac] = {"name": name, "ip": ip, "connection_type": conn,
                        "source": "dhcpd", "events": []}
    return devices


def parse_dhcp(text, devices):
    section, sec_start = extract_section_ln(text, "##### BEGIN SECTION dhcp\n", "##### END SECTION dhcp")
    if not section:
        return
    for off, line in enumerate(section.splitlines()):
        if not line.strip() or "<<<" not in line:
            continue
        macs = MAC_RE.findall(line)
        if not macs:
            continue
        mac = macs[0].lower()
        if mac not in devices:
            continue
        devices[mac]["events"].append({
            "timestamp": extract_timestamp(line), "source": "dhcp",
            "event_type": "connect", "log_line_nr": sec_start + off, "log_line": line})


def parse_station_module(text, devices):
    section, sec_start = extract_section_ln(
        text, "##### BEGIN SECTION STATION_MODULE", "##### END SECTION STATION_MODULE")
    if not section:
        return
    mac_line_re = re.compile(r"^\s*mac\s*=\s*([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})\s*$",
                             re.MULTILINE | re.IGNORECASE)
    TS_GER = r"\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}:\d{2}"
    history_re = re.compile(rf"({TS_GER})/\[[\d.]+\]\s*/\s*(\d+)"
                            rf"(?:\s*-\s*({TS_GER})/\[[\d.]+\]\s*/\s*(\d+))?")
    current_mac, in_history = None, False
    for off, line in enumerate(section.splitlines()):
        mm = mac_line_re.match(line)
        if mm:
            current_mac, in_history = mm.group(1).lower(), False
            continue
        if "Connect history:" in line:
            in_history = True
            continue
        if not in_history or not current_mac or current_mac not in devices:
            continue
        hm = history_re.search(line)
        if not hm:
            continue
        ts_c, st_c, ts_d, st_d = hm.group(1), hm.group(2), hm.group(3), hm.group(4)
        ln = sec_start + off
        if st_c == "1":
            devices[current_mac]["events"].append({
                "timestamp": ts_c, "source": "STATION_MODULE", "event_type": "connect",
                "log_line_nr": ln, "log_line": line})
        if ts_d and st_d == "1":
            devices[current_mac]["events"].append({
                "timestamp": ts_d, "source": "STATION_MODULE", "event_type": "disconnect",
                "log_line_nr": ln, "log_line": line})


def parse_wlan_events(text, devices):
    section, sec_start = extract_section_ln(
        text, "##### BEGIN SECTION WLAN_EVENTS", "##### END SECTION WLAN_EVENTS")
    if not section:
        return
    TRUSTED = {"30005": "connect", "752": "disconnect"}
    for off, line in enumerate(section.splitlines()):
        if not line.strip():
            continue
        mm = MAC_RE.search(line)
        if not mm:
            continue
        mac = mm.group(0).lower()
        if mac not in devices:
            continue
        id_m = re.search(r"\b(\d+)\b", line[mm.end():])
        if not id_m or id_m.group(1) not in TRUSTED:
            continue
        devices[mac]["events"].append({
            "timestamp": parse_wlan_timestamp(line), "source": "WLAN_EVENTS",
            "event_type": TRUSTED[id_m.group(1)], "log_line_nr": sec_start + off, "log_line": line})


def parse_events_events(text, devices):
    section, sec_start = extract_section_ln(
        text, "##### BEGIN SECTION Events Events", "##### END SECTION Events")
    if not section:
        return
    for off, line in enumerate(section.splitlines()):
        if not line.strip():
            continue
        ts = mesh_node = event_type = mac = freq = device_name = ip = None
        is_guest = False
        m = EV_WLAN_INLINE_RE.match(line)
        if m:
            ts, mesh_node, event_text, mac = m.group(1), m.group(2), m.group(3), m.group(4)
            event_type, is_guest = _classify_event(event_text)
            fm = FREQ_RE.search(event_text)
            freq = fm.group(1) if fm else None
            nm = EV_NAME_RE.search(event_text)
            device_name = nm.group(1).strip() if nm else None
            im = re.search(r",\s+IP\s+(\S+?)\s*,\s+MAC", line)
            if im and im.group(1) not in ("---", ""):
                ip = im.group(1).rstrip(".,")
        elif re.search(r"(?:gescheitert|fehlgeschlagen|Schlüssel)", line):
            m = EV_FAILED_RE.match(line)
            if m:
                ts, mesh_node, event_text, mac = m.group(1), m.group(2), m.group(3), m.group(4)
                event_type = "failed_connect"
                is_guest = "gastzugang" in event_text.lower()
                fm = FREQ_RE.search(event_text)
                freq = fm.group(1) if fm else None
        elif "verbunden" in line.lower() and "MAC:" in line:
            m = EV_OLD_RE.match(line)
            if m:
                ts, mac, event_type = m.group(1), m.group(2), "connect"
                nm = re.search(r"Name:\s+([^,]+)", line)
                device_name = nm.group(1).strip() if nm else None
        if not (ts and mac and event_type) or event_type == "unknown":
            continue
        mac = mac.lower()
        if mac not in devices:
            devices[mac] = {"name": device_name or "", "ip": ip or "",
                            "connection_type": "wlan_guest" if is_guest else "wlan",
                            "source": "events_events", "events": []}
        devices[mac]["events"].append({
            "timestamp": ts, "source": "Events_Events", "event_type": event_type,
            "mesh_node": mesh_node or "", "frequency": freq or "",
            "log_line_nr": sec_start + off, "log_line": line})


def parse_mesh_shringbuf(text, devices):
    start = text.find("===== Mesh Shringbuf Begin =====")
    if start == -1:
        return
    end = text.find("===== Mesh Shringbuf End =====", start)
    section = text[start:] if end == -1 else text[start:end]
    sec_start = text[:start].count("\n") + 1
    wss_rx_tx_re = re.compile(r"scored\s+RX\s+(\d+)\s+and\s+TX\s+(\d+)")
    sta_re = re.compile(r"\bSTA\s+([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})\b", re.IGNORECASE)
    for off, line in enumerate(section.splitlines()):
        if not line.strip():
            continue
        is_wss = "WSS_select_target: rate_link():136:" in line
        is_sc = "SC: handle_steering_result():801:" in line
        if not (is_wss or is_sc):
            continue
        if is_wss:
            rxtx = wss_rx_tx_re.search(line)
            if not rxtx or (int(rxtx.group(1)) == 0 and int(rxtx.group(2)) == 0):
                continue
            macs = MAC_RE.findall(line)
            if len(macs) < 2:
                continue
            device_mac = macs[1].lower()
        else:
            sm = sta_re.search(line)
            if not sm:
                continue
            device_mac = sm.group(1).lower()
        if device_mac not in devices:
            continue
        devices[device_mac]["events"].append({
            "timestamp": extract_timestamp(line), "source": "MESH_Shringbuf",
            "event_type": "mesh_activity", "log_line_nr": sec_start + off, "log_line": line})


# ───────────────────────── 802.11-Log-Parser (aus dem PoC) ───────────────────

# Interface-Namen variieren je Chipsatz: Atheros ath0/ath1, Broadcom wl0/wl1.
_WLAN80211_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})\.(\d+) - ((?:ath|wl)\d): STA "
    r"([0-9a-fA-F:]{17}) IEEE 802\.11: (\w+)")
_BAND = {"ath0": "2,4 GHz", "ath1": "5 GHz", "ath2": "6 GHz",
         "wl0": "2,4 GHz", "wl1": "5 GHz", "wl2": "6 GHz"}

EVENT_DE = {
    "associated": "angemeldet", "disassociated": "abgemeldet",
    "authenticated": "authentifiziert", "deauthenticated": "deauthentifiziert",
    "connect": "angemeldet", "disconnect": "abgemeldet",
    "failed_connect": "Anmeldung gescheitert", "steering": "umgemeldet",
    "mesh_activity": "Mesh-Aktivität",
}


def _sec_display(dt: datetime | None, fallback: str) -> tuple[str, str]:
    """→ (iso_sekundengenau, display 'YYYY-MM-DD HH:MM:SS'). Fallback = Rohstring."""
    if dt:
        return dt.strftime("%Y-%m-%dT%H:%M:%S"), dt.strftime("%Y-%m-%d %H:%M:%S")
    return fallback, fallback


# ───────────────────────── Vereinigung ───────────────────────────────────────

def analyze(bundle, real_aps, master_name) -> dict:
    """→ {'proofs': [...], 'uptime': {...}}.

    ``proofs`` = vereinte, deduplizierte Verbindungsnachweise (Sektion 6/Timeline).
    Jeder Nachweis: iso · sortkey · display · mac · event · event_de · band · ap ·
    grades · f_* · origin{file,sha,line,text}. Dedup-Key = (iso-Sekunde, mac, event).
    """
    support_files = [sf for sf in bundle.support.values() if getattr(sf, "present", False)]

    # 1) Geräteregister aus dhcpd (über alle Supportdateien gemergt)
    devices: dict = {}
    for sf in support_files:
        devices.update(parse_dhcpd(sf.text))

    # 2) methode.md-Event-Parser je Datei; neue Events der Datei zuordnen
    methode_hits = []  # (event_dict, source_file)
    for sf in support_files:
        before = {mac: len(d["events"]) for mac, d in devices.items()}
        for fn in (parse_dhcp, parse_station_module, parse_wlan_events,
                   parse_events_events, parse_mesh_shringbuf):
            fn(sf.text, devices)
        for mac, d in devices.items():
            for ev in d["events"][before.get(mac, 0):]:
                methode_hits.append((mac, ev, sf))

    # dedup + grade
    unified: dict = {}   # key -> proof

    def _add(mac, iso, sortkey, display, event, band, ap, grades, sf, line, line_text):
        key = (iso, mac.upper(), event)
        if key in unified:
            p = unified[key]
            for g in grades:
                if g not in p["grades"]:
                    p["grades"].append(g)
            p["sources"].add(sf.name)
            return
        unified[key] = {
            "iso": iso, "sortkey": sortkey, "display": display,
            "mac": mac.upper(), "event": event, "event_de": EVENT_DE.get(event, event),
            "band": band, "ap": ap, "sources": {sf.name},
            "grades": list(grades),
            "f_name": "", "f_phone": "", "f_ap": ap, "f_iso": iso,
            "origin": {"file": sf.name, "sha": sf.sha256, "idx": None, "total": None,
                       "line": line, "line_end": line, "text": line_text},
        }

    # 2a) methode.md-Treffer → D1+D2
    for mac, ev, sf in methode_hits:
        dt = parse_event_ts(ev.get("timestamp"))
        iso, display = _sec_display(dt, ev.get("timestamp") or "")
        band = ev.get("frequency") or ""
        ap = ev.get("mesh_node") or ""
        _add(mac, iso, iso, display, ev["event_type"], band, ap,
             ("D1", "D2"), sf, ev.get("log_line_nr"), ev.get("log_line") or "")

    # 2b) 802.11-Log-Treffer → D1+D3 (Datei: standard, sonst erste vorhandene)
    sf80 = bundle.support.get("standard")
    if not (sf80 and getattr(sf80, "present", False)):
        sf80 = next((s for s in support_files), None)
    if sf80:
        for off, line in enumerate(sf80.lines, 1):
            m = _WLAN80211_RE.match(line)
            if not m:
                continue
            date, tm, ms, iface, mac, event = m.groups()
            iso = f"{date}T{tm}"
            sortkey = f"{iso}.{int(ms):06d}"
            _add(mac, iso, sortkey, f"{date} {tm}", event,
                 _BAND.get(iface, iface), master_name, ("D1", "D3"), sf80, off, line)

    proofs = sorted(unified.values(), key=lambda p: p["sortkey"])
    for i, p in enumerate(proofs, 1):
        p["origin"]["idx"] = i
        p["origin"]["total"] = len(proofs)
        p["sources"] = sorted(p["sources"])

    # 3) Betriebszeit (aus standard) — roh (kein Badge) + abgeleitet (D3)
    uptime = _parse_uptime(sf80, bundle.meta.get("extracted_at", "")) if sf80 else {}

    return {"proofs": proofs, "uptime": uptime}


def _parse_uptime(sf, extracted_at: str) -> dict:
    from datetime import timedelta
    days = wan_s = ""
    up_ln = wan_ln = None
    for lineno, line in enumerate(sf.lines, 1):
        if not days and line.startswith("uptime:"):
            um = re.search(r"up (\d+ days?(?:,\s*\d+:\d+)?)", line)
            days, up_ln = (um.group(1) if um else line.strip()), lineno
        if not wan_s and (wm := re.match(r"\s*ip4_uptime=(\d+)\s*$", line)):
            wan_s, wan_ln = wm.group(1), lineno
        if days and wan_s:
            break
    boot = ""
    dm = re.match(r"(\d+) days?", days)
    if dm:
        try:
            base = datetime.fromisoformat(extracted_at.replace("Z", "+00:00"))
            boot = (base - timedelta(days=int(dm.group(1)))).strftime("%Y-%m-%d")
        except Exception:
            boot = ""
    return {
        "file": sf.name, "days": days, "up_line": up_ln,
        "wan_s": wan_s, "wan_line": wan_ln,
        "wan_h": f"{int(wan_s) / 3600:.1f}" if wan_s else "",
        "boot_derived": boot,
    }
