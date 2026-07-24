"""SHA256-Sidecars: schreiben, lesen, verifizieren.

Zu jeder Bundle-Datei ``X`` gehört ``X.sha256`` mit dem Inhalt
``"<hex-digest>  <dateiname>\\n"`` — dasselbe Format wie ``sha256sum``, damit
sich ein Bundle auch ohne unsere Werkzeuge prüfen lässt (``sha256sum -c``).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

SIDECAR_SUFFIX = ".sha256"

#: Ergebnis von :func:`verify`.
STATUS_OK = "ok"
STATUS_MISMATCH = "mismatch"
STATUS_NO_SIDECAR = "no_sidecar"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    """Digest einer Datei, blockweise gelesen (Bundles enthalten große Dateien)."""
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sidecar_path(path: Path) -> Path:
    path = Path(path)
    return path.with_suffix(path.suffix + SIDECAR_SUFFIX)


def write_sidecar(path: Path, digest: str) -> Path:
    """Legt die Sidecar zu ``path`` an und gibt ihren Pfad zurück."""
    path = Path(path)
    sc = sidecar_path(path)
    sc.write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return sc


def read_sidecar(path: Path) -> tuple[str, str]:
    """→ (erwarteter Hex-Digest, im Sidecar genannter Dateiname).

    Beides leer, wenn keine oder eine leere Sidecar vorliegt.
    """
    sc = sidecar_path(path)
    if not sc.exists():
        return "", ""
    raw = sc.read_text(encoding="utf-8", errors="replace").strip()
    if not raw:
        return "", ""
    parts = raw.split()
    digest = parts[0]
    fname = " ".join(parts[1:]) if len(parts) > 1 else ""
    return digest.lower(), fname


def verify(path: Path) -> tuple[str, str]:
    """Verifiziert ``path`` gegen seine Sidecar.

    → (status, digest) mit status ∈ {"ok", "mismatch", "no_sidecar"}.
    ``digest`` ist der tatsächlich berechnete Hash der Datei (immer gesetzt).

    Verglichen wird ausschließlich der Digest, nicht der in der Sidecar
    genannte Dateiname — ein umbenanntes Bundle bleibt damit prüfbar.
    """
    actual = sha256_file(path)
    expected, _ = read_sidecar(path)
    if not expected:
        return STATUS_NO_SIDECAR, actual
    return (STATUS_OK if expected == actual else STATUS_MISMATCH), actual
