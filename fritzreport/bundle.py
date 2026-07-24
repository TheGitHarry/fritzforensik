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
from pathlib import Path

# Formatvertrag mit fritzexport — Dateinamen, Datenarten, Sidecar-Prüfung.
from fritzformat import (
    JSON_TYPES,
    SIDECAR_SUFFIX,
    SUPPORT_VARIANTS,
    dataset_glob,
    read_envelope_meta,
    read_sidecar,
    session_log_glob,
    sha256_file,
    support_glob,
    verify,
)

__all__ = [
    "JSON_TYPES", "SUPPORT_VARIANTS", "sha256_file", "read_sidecar", "verify",
    "record_slices", "Dataset", "SupportFile", "CoCEntry", "Bundle", "load_bundle",
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
class Bundle:
    dir: Path
    datasets: dict = field(default_factory=dict)     # type -> Dataset
    support: dict = field(default_factory=dict)      # variant -> SupportFile
    coc: list = field(default_factory=list)          # CoCEntry
    meta: dict = field(default_factory=dict)         # tool/version/host/extracted_at
    session_log: str = ""
    tam_audio_dir: Path | None = None

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

    return b
