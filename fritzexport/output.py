"""JSON-Output mit SHA256-Sidecar.

Dateinamen, Hüllformat und Sidecar kommen aus :mod:`fritzformat` — dort liegt
der gemeinsame Formatvertrag mit fritzreport.
"""
from __future__ import annotations

import json
from pathlib import Path

from fritzformat import (
    TOOL_NAME,
    build_envelope,
    dataset_filename,
    sha256_bytes,
    utc_now_compact,
    utc_now_iso,
    write_sidecar,
)

from . import __version__

# Aliase für bestehende Aufrufer (cli.py, Tests) — Implementierung in fritzformat.
_utc_now_iso = utc_now_iso
_utc_now_compact = utc_now_compact


def write(
    output_dir: Path,
    host: str,
    type_name: str,
    records: list[dict],
    timestamp: str | None = None,
    discovery_meta: dict | None = None,
    extra_meta: dict | None = None,
) -> Path:
    """Schreibt Records als JSON + .sha256-Sidecar. Gibt JSON-Pfad zurück."""
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = timestamp or utc_now_compact()
    json_path = output_dir / dataset_filename(host, ts, type_name)

    payload = build_envelope(
        tool=TOOL_NAME,
        version=__version__,
        host=host,
        type_name=type_name,
        records=records,
        discovery_meta=discovery_meta,
        extra_meta=extra_meta,
    )
    body = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
    json_path.write_bytes(body)

    write_sidecar(json_path, sha256_bytes(body))
    return json_path
