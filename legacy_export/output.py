"""JSON-Output mit SHA256-Sidecar."""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from pathlib import Path

from . import __version__

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _slug(value: str) -> str:
    return _SAFE.sub("_", value).strip("_") or "host"


def _utc_now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_now_compact() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write(
    output_dir: Path,
    host: str,
    type_name: str,
    records: list[dict],
    timestamp: str | None = None,
) -> Path:
    """Schreibt Records als JSON + .sha256-Sidecar. Gibt JSON-Pfad zurück."""
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = timestamp or _utc_now_compact()
    filename = f"legacy_export_{_slug(host)}_{ts}_{type_name}.json"
    json_path = output_dir / filename

    payload = {
        "tool": "legacy_export",
        "version": __version__,
        "host": host,
        "extracted_at": _utc_now_iso(),
        "type": type_name,
        "records": records,
    }
    body = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
    json_path.write_bytes(body)

    digest = hashlib.sha256(body).hexdigest()
    sidecar = json_path.with_suffix(json_path.suffix + ".sha256")
    sidecar.write_text(f"{digest}  {filename}\n", encoding="utf-8")
    return json_path
