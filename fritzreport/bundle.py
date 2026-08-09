"""Bundle-Erkennung, SHA-256-Verifikation und Herkunfts-Slices.

Ein fritzexport-Bundle ist ein Verzeichnis mit — pro Datenart — einer
``fritzexport_<host>_<UTC>Z_<typ>.json`` und einer ``.sha256``-Sidecar, dazu
den Roh-Supportdateien ``supportdata_<variante>_<UTC>Z.txt`` (+ Sidecar), einem
Sitzungs-Log und optional ``tam_audio/``.

Dieses Modul lädt das Bundle, **verifiziert** jede Datei gegen ihre Sidecar
(der PoC hat den Hash nur angezeigt) und stellt für jeden Datensatz die
Fundstelle in der Quelldatei bereit (Zeilennummer + wörtlicher Auszug).
"""
from __future__ import annotations

import bisect
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Formatvertrag mit fritzexport — Dateinamen, Datenarten, Sidecar-Prüfung.
from fritzformat import (
    JSON_TYPES,
    SIDECAR_SUFFIX,
    SUPPORT_VARIANTS,
    dataset_glob,
    parse_span,
    parse_uhr_spans,
    read_envelope_meta,
    read_sidecar,
    session_log_glob,
    sha256_file,
    support_glob,
    verify,
)

from .supportdata import parse_box_header_time

__all__ = [
    "JSON_TYPES", "SUPPORT_VARIANTS", "sha256_file", "read_sidecar", "verify",
    "record_slices", "Dataset", "SupportFile", "CoCEntry", "Bundle", "ClockOffset",
    "load_bundle",
]


# ----------------------------------------------------- Herkunfts-Slices

_RECORDS_RE = re.compile(r'"records"\s*:\s*\[')


def record_slices(text: str) -> list[dict]:
    """Fundstelle jedes Records im ``records``-Array: Zeilennummern + Original-Auszug.

    Übernommen aus dem PoC (``build_report.py``): der Auszug wird auf volle Zeilen
    aufgezogen und aus der Datei geschnitten, nicht neu serialisiert — wer die
    Zeile in der Quelldatei aufschlägt, sieht Zeichen für Zeichen dasselbe.
    """
    m = _RECORDS_RE.search(text)
    if not m:
        return []
    line_starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            line_starts.append(i + 1)
    line_of = lambda pos: bisect.bisect_right(line_starts, pos)

    dec = json.JSONDecoder()
    out, idx, n = [], m.end(), len(text)
    while idx < n:
        while idx < n and text[idx] in " \t\r\n,":
            idx += 1
        if idx >= n or text[idx] == "]":
            break
        try:
            _, end = dec.raw_decode(text, idx)
        except ValueError:
            break
        start = text.rfind("\n", 0, idx) + 1
        if text[start:idx].strip():
            start = idx
        stop = text.find("\n", end)
        if stop == -1:
            stop = n
        out.append({
            "line": line_of(start),
            "line_end": line_of(stop - 1),
            "text": text[start:stop],
        })
        idx = end
    return out


# ------------------------------------------------------------- Datentypen

@dataclass
class Dataset:
    """Eine geladene JSON-Datenart aus dem Bundle."""
    type: str
    path: Path
    name: str = ""
    data: dict = field(default_factory=dict)
    sha256: str = ""            # tatsächlich berechneter Hash
    status: str = "missing"     # ok | mismatch | no_sidecar | missing
    slices: list = field(default_factory=list)

    @property
    def records(self) -> list:
        return (self.data or {}).get("records", [])

    @property
    def present(self) -> bool:
        return self.path is not None and self.name != ""


@dataclass
class SupportFile:
    """Eine Roh-Supportdatei (Text)."""
    variant: str
    path: Path
    name: str = ""
    text: str = ""
    sha256: str = ""
    status: str = "missing"

    @property
    def lines(self) -> list[str]:
        return self.text.split("\n") if self.text else []

    @property
    def present(self) -> bool:
        return self.path is not None and self.name != ""


@dataclass
class CoCEntry:
    file: str
    sha256: str          # erwarteter Hash laut Sidecar (bzw. berechneter)
    status: str          # ok | mismatch | no_sidecar
    size: int | None = None


@dataclass
class ClockOffset:
    """Ein Abgleich der Box-Uhr gegen die Referenzuhr der Abzugsmaschine.

    Der Versatz ist ein **Intervall**, kein Einzelwert: Beide Quellen geben ihre Zeit
    nur sekundengenau an, und zwischen den beiden Referenzmarken liegt der Abruf.

    ``beidseitig`` entscheidet, wie viel davon eine Aussage ist:

    - **True** (TR-064) — die Klammer ist die Round-Trip-Zeit, beide Schranken tragen.
    - **False** (Supportdaten) — nur ``versatz_max_s`` ist ein Messwert. Die Box
      schreibt ihren Kopf am Anfang der Erzeugung; ``versatz_min_s`` enthält deshalb
      die gesamte Übertragungsdauer und besagt nur, dass ein Nachgehen der Box
      unentdeckt bliebe. Der Report weist ihn nicht als Messwert aus.
    """
    quelle: str          # "tr064:time" | "supportdata:standard" | "supportdata:enhanced"
    box_lokal: str       # Zeitangabe der Box, wörtlich wie in der Quelle
    ref_von: str         # UTC, unmittelbar vor dem Abruf
    ref_bis: str         # UTC, unmittelbar nach dem Abruf
    versatz_min_s: int
    versatz_max_s: int
    beidseitig: bool
    herkunft: str        # "marker" = eng protokolliert · "berechnet" = Altbestand
    fundstelle: dict = field(default_factory=dict)

    @property
    def klammer_s(self) -> int:
        """Breite der Klammer — die Fehlerschranke der Messung."""
        return self.versatz_max_s - self.versatz_min_s

    @property
    def enthaelt_null(self) -> bool:
        """Kein Versatz nachweisbar (beidseitig) bzw. kein Vorgehen (einseitig)."""
        if self.beidseitig:
            return self.versatz_min_s <= 0 <= self.versatz_max_s
        return self.versatz_max_s >= 0


@dataclass
class Bundle:
    dir: Path
    datasets: dict = field(default_factory=dict)     # type -> Dataset
    support: dict = field(default_factory=dict)      # variant -> SupportFile
    coc: list = field(default_factory=list)          # CoCEntry
    meta: dict = field(default_factory=dict)         # tool/version/host/extracted_at
    session_log: str = ""
    tam_audio_dir: Path | None = None

    #: Sicherungszeitraum (erster bis letzter Datenabruf) als ISO-UTC.
    #: ``secured_source``: "log" = aus den Markern protokolliert · "berechnet" =
    #: aus den ``extracted_at`` der Datensätze abgeleitet · "" = nicht ermittelbar.
    secured_from: str = ""
    secured_to: str = ""
    secured_source: str = ""

    #: Abgleiche der Box-Uhr gegen die Referenzuhr, je Quelle einer.
    clock_offsets: list = field(default_factory=list)   # ClockOffset

    def ds(self, type_: str) -> Dataset:
        return self.datasets.get(type_) or Dataset(type=type_, path=None)  # type: ignore[arg-type]

    @property
    def integrity_ok(self) -> bool:
        return all(e.status != "mismatch" for e in self.coc)


# ------------------------------------------------------------- Laden

def _first(dir_: Path, pattern: str) -> Path | None:
    matches = sorted(dir_.glob(pattern))
    return matches[0] if matches else None


def load_bundle(dir_: Path) -> Bundle:
    dir_ = Path(dir_)
    if not dir_.is_dir():
        raise NotADirectoryError(f"Bundle-Verzeichnis nicht gefunden: {dir_}")

    b = Bundle(dir=dir_)

    # --- JSON-Datenarten
    for t in JSON_TYPES:
        p = _first(dir_, dataset_glob(t))
        if not p:
            b.datasets[t] = Dataset(type=t, path=None)  # type: ignore[arg-type]
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = {}
        status, digest = verify(p)
        b.datasets[t] = Dataset(
            type=t, path=p, name=p.name, data=data, sha256=digest,
            status=status, slices=record_slices(text),
        )

    # --- Roh-Supportdaten
    for v in SUPPORT_VARIANTS:
        p = _first(dir_, support_glob(v))
        if not p:
            b.support[v] = SupportFile(variant=v, path=None)  # type: ignore[arg-type]
            continue
        status, digest = verify(p)
        b.support[v] = SupportFile(
            variant=v, path=p, name=p.name,
            text=p.read_text(encoding="utf-8", errors="replace"),
            sha256=digest, status=status,
        )

    # --- Metadaten aus einer beliebigen vorhandenen JSON (bevorzugt hosts)
    for t in ("hosts", *JSON_TYPES):
        d = b.datasets.get(t)
        if d and d.present and d.data:
            b.meta = read_envelope_meta(d.data)
            break

    # --- Chain of Custody: jede Datei mit Sidecar, verifiziert
    for sc in sorted(dir_.glob(f"*{SIDECAR_SUFFIX}")):
        target = sc.with_suffix("")  # entfernt die Sidecar-Endung
        expected, _ = read_sidecar(target)
        if target.exists():
            status, actual = verify(target)
            size = target.stat().st_size
            shown = expected or actual
        else:
            status, shown, size = "mismatch", expected, None
        b.coc.append(CoCEntry(file=target.name, sha256=shown, status=status, size=size))

    # --- Sitzungs-Log + TAM-Audio
    log = _first(dir_, session_log_glob())
    if log:
        b.session_log = log.read_text(encoding="utf-8", errors="replace")
    tam = dir_ / "tam_audio"
    if tam.is_dir():
        b.tam_audio_dir = tam

    _resolve_secured_span(b)
    _resolve_clock_offset(b)
    return b


def _resolve_secured_span(b: Bundle) -> None:
    """Sicherungszeitraum bestimmen — protokolliert, sonst gerechnet.

    Neuere Abzüge protokollieren Beginn und Ende als Marker im Sitzungslog. Fehlen
    sie (Altbestand), wird der Zeitraum aus den ``extracted_at`` **aller** Datensätze
    abgeleitet: Jede Datei trägt den Zeitpunkt, zu dem ihr Extractor fertig war.
    Der gerechnete Wert beginnt damit etwas später als der tatsächliche Abruf — der
    Report muss ihn deshalb als abgeleitet kennzeichnen.
    """
    von, bis = parse_span(b.session_log)
    if von or bis:
        b.secured_from, b.secured_to, b.secured_source = von, bis, "log"
        return

    stamps = sorted(
        s for d in b.datasets.values()
        if d.present and isinstance(d.data, dict)
        and (s := str(d.data.get("extracted_at", "") or ""))
    )
    if stamps:
        b.secured_from, b.secured_to, b.secured_source = stamps[0], stamps[-1], "berechnet"


# ------------------------------------------------- Versatz der Box-Uhr

#: Beide Quellen geben ihre Zeit nur sekundengenau an; die wahre Zeit liegt also im
#: Intervall [angegeben, angegeben + 1 s). Ohne diesen Zuschlag zeigte selbst eine
#: perfekt synchrone Box einen scheinbaren Rückstand von im Mittel einer halben
#: Sekunde — ein Messartefakt, kein Befund.
_QUANTUM_S = 1

_LOG_START_RE = re.compile(r"^(\S+ \S+) INFO Starte Extractor: supportdata", re.M)
_LOG_SAVED_RE = re.compile(r"^(\S+ \S+) INFO Supportdaten '(\w+)' gespeichert", re.M)
_LOG_HEAD_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ ")


def _iso_to_dt(iso: str):
    """ISO-UTC (``…Z``) → naives datetime in UTC; ``None`` wenn unbrauchbar.

    Nimmt beide Schreibweisen: sekundengenau (``…:11Z``, wie ``extracted_at`` und die
    Marker älterer Abzüge) und mit Bruchteil (``…:11.412Z``, wie die Uhr-Marker sie
    schreiben — dort zählt jede Millisekunde für die Breite der Klammer).
    """
    if not iso:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(iso.rstrip("Z"), fmt)
        except ValueError:
            continue
    return None


def _resolve_clock_offset(b: Bundle) -> None:
    """Versatz der Box-Uhr gegen die Referenzuhr — je Quelle ein `ClockOffset`.

    Beide Quellen liefern dasselbe Muster: eine Zeitangabe der Box, geklammert von
    zwei Referenzzeiten der Abzugsmaschine. Die Rechnung steht deshalb **einmal**
    hier statt zweimal in den Extractoren.

    Empirische Grundlage der Asymmetrie (7 Abzüge des Testkorpus): Der Kopf der
    Supportdaten entsteht am Anfang der Erzeugung, kurz nach dem Request — gemessen
    −0,1 bis +7,3 s zur Anfrage, bei Übertragungsdauern von 41 bis 196 s (r = +0,94;
    der Vorlauf wächst mit dem Datenvolumen). Die *obere* Schranke ist dort also der
    Messwert, die untere enthält die gesamte Übertragung. Bei TR-064 ist die Klammer
    die Round-Trip-Zeit, dort tragen beide Schranken.

    Rückwirkend (Altbestand ohne Marker) wird **nur** ``standard`` ausgewertet: Bei
    ``enhanced`` liegt zwischen Logzeile und Abruf die Wartezeit auf den Tastendruck
    — bei der 7490 des Korpus 595 s, was einen Uhrenfehler vortäuschte.
    """
    spans = parse_uhr_spans(b.session_log)

    # --- Quelle 1: TR-064 Time:1 — beidseitig scharf
    ds = b.ds("boxtime")
    for i, r in enumerate(ds.records):
        if r.get("record_type") != "box_clock":
            continue
        von, bis = spans.get("tr064:time", ("", ""))
        box = _parse_box_iso(r.get("box_current_local_time", ""))
        if box and von and bis:
            _add_offset(b, "tr064:time", r.get("box_current_local_time", ""),
                        von, bis, box, beidseitig=True, herkunft="marker",
                        fundstelle=_ds_fundstelle(ds, i))
        break

    # --- Quelle 2: Kopf der Supportdaten — nur die obere Schranke trägt
    for variante in ("standard", "enhanced"):
        sf = b.support.get(variante)
        if not (sf and sf.present and sf.text):
            continue
        box, tz, zeile = parse_box_header_time(sf.text)
        if box is None:
            continue   # kein Kopf (Mesh-Dump) oder unbekannte Zeitzone → keine Messung

        quelle = f"supportdata:{variante}"
        von, bis = spans.get(quelle, ("", ""))
        herkunft = "marker"
        if not (von and bis):
            if variante != "standard":
                continue   # enhanced ohne eigene Marker: Tastendruck-Wartezeit
            von, bis = _altbestand_klammer(b)
            herkunft = "berechnet"
        if not (von and bis):
            continue

        # Wörtlich wie in der Datei — `box` ist nach UTC umgerechnet, das Kürzel
        # bezeichnet aber die Ortszeit. Beides zu mischen ergäbe eine falsch
        # etikettierte Uhrzeit („14:18:10 CEST" statt „16:18:10 CEST").
        _add_offset(b, quelle, _kopfzeile_woertlich(sf.text) or tz,
                    von, bis, box, beidseitig=False, herkunft=herkunft,
                    fundstelle={"file": sf.name, "sha": sf.sha256, "line": zeile})


_KOPF_WERT_RE = re.compile(r"#####\s+TITLE\s+Datum\s+(.+)")


def _kopfzeile_woertlich(text: str) -> str:
    """Die Zeitangabe der Box so, wie sie in der Datei steht."""
    m = _KOPF_WERT_RE.search(text or "")
    return m.group(1).strip() if m else ""


def _parse_box_iso(wert: str):
    """``2026-08-09T17:55:36+02:00`` → naives datetime in UTC."""
    if not wert:
        return None
    try:
        dt = datetime.fromisoformat(wert)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt
    return (dt - dt.utcoffset()).replace(tzinfo=None)


def _add_offset(b, quelle, box_lokal, von, bis, box, *, beidseitig, herkunft,
                fundstelle) -> None:
    dt_von, dt_bis = _iso_to_dt(von), _iso_to_dt(bis)
    if not (dt_von and dt_bis):
        return
    if dt_von > dt_bis:
        # Rückwärts laufende Klammer — im Log steht die Antwort vor ihrer Anfrage.
        # Das ist keine Messung, sondern ein gekürztes oder manipuliertes Log; die
        # Breite wäre negativ und die Aussage schärfer als jede echte Messung.
        return
    b.clock_offsets.append(ClockOffset(
        quelle=quelle,
        box_lokal=box_lokal,
        ref_von=von,
        ref_bis=bis,
        versatz_min_s=int(round((box - dt_bis).total_seconds())),
        versatz_max_s=int(round((box - dt_von).total_seconds())) + _QUANTUM_S,
        beidseitig=beidseitig,
        herkunft=herkunft,
        fundstelle=fundstelle,
    ))


def _altbestand_klammer(b: Bundle) -> tuple[str, str]:
    """Grobe Klammer für Abzüge ohne Marker, aus den Logzeilen des Extractors.

    Die Zeilenköpfe stehen in **Lokalzeit** — ein direkter Vergleich mit der
    UTC-Zeit der Box mischte zwei Zeitzonen. Der Versatz der Abzugsmaschine wird
    deshalb aus einer Zeile bestimmt, die beides trägt: der ``SICHERUNG BEGINN``-
    Marker (UTC im Text, Lokalzeit im Kopf). Fehlt auch der, dient ``extracted_at``
    der Supportdaten-Datenart als Anker. Ohne Anker gibt es **keine** Messung.
    """
    if not b.session_log:
        return "", ""
    start = _LOG_START_RE.search(b.session_log)
    saved = [m for m in _LOG_SAVED_RE.finditer(b.session_log)
             if m.group(2) == "standard"]
    if not (start and saved):
        return "", ""

    versatz = _maschinen_versatz(b)
    if versatz is None:
        return "", ""
    try:
        t_req = datetime.strptime(start.group(1), "%Y-%m-%d %H:%M:%S,%f")
        t_res = datetime.strptime(saved[0].group(1), "%Y-%m-%d %H:%M:%S,%f")
    except ValueError:
        return "", ""
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return ((t_req - versatz).strftime(fmt), (t_res - versatz).strftime(fmt))


def _maschinen_versatz(b: Bundle):
    """Offset Lokalzeit → UTC der Abzugsmaschine, als `timedelta`."""
    m = re.search(r"^(\S+ \S+) INFO SICHERUNG BEGINN\s+(\S+)", b.session_log, re.M)
    if m:
        lokal = _log_kopf_dt(m.group(1))
        utc = _iso_to_dt(m.group(2))
        if lokal and utc:
            return lokal - utc

    # Kein Marker: extracted_at der Supportdaten gegen ihre Abschlusszeile
    ds = b.ds("supportdata")
    iso = str(ds.data.get("extracted_at", "") or "") if isinstance(ds.data, dict) else ""
    fertig = re.search(r"^(\S+ \S+) INFO Extractor 'supportdata':", b.session_log, re.M)
    if iso and fertig:
        lokal = _log_kopf_dt(fertig.group(1))
        utc = _iso_to_dt(iso)
        if lokal and utc:
            return lokal - utc
    return None


def _log_kopf_dt(wert: str):
    try:
        return datetime.strptime(wert, "%Y-%m-%d %H:%M:%S,%f")
    except ValueError:
        return None


def _ds_fundstelle(ds, i: int) -> dict:
    s = ds.slices[i] if i < len(ds.slices) else None
    return {"file": ds.name, "sha": ds.sha256, "line": s["line"] if s else None}
