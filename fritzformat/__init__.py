"""fritzformat — gemeinsamer Formatvertrag von fritzexport und fritzreport.

Dieses Paket ist die **einzige Wahrheit** darüber, wie ein Bundle aussieht:
Dateinamen, Hüllformat der JSON-Dateien und die SHA256-Sidecars. Vorher lag
dasselbe Wissen dreifach vor (Schreibseite im Export, Leseseite im Report und
ein drittes Mal im Test-Fixture), ohne dass eine Abweichung aufgefallen wäre.

**Bewusst stdlib-only**: fritzreport hat keine Laufzeit-Abhängigkeiten, und da
es dieses Paket importiert, darf auch hier nichts Fremdes hinzukommen.
"""
from __future__ import annotations

from .casefile import (
    CASE_FIELDS,
    CASE_FILENAME,
    CASE_LABELS,
    build_case,
    case_path,
    collect_case,
    read_case,
    write_case,
)
from .digest import (
    SIDECAR_SUFFIX,
    read_sidecar,
    sha256_bytes,
    sha256_file,
    verify,
    write_sidecar,
)
from .envelope import (
    ENVELOPE_KEYS,
    build_envelope,
    compact_from_iso,
    read_envelope_meta,
    utc_now_compact,
    utc_now_iso,
)
from .names import (
    BUNDLE_GLOB,
    JSON_TYPES,
    RUN_FALLBACK,
    SUPPORT_VARIANTS,
    TOOL_NAME,
    dataset_filename,
    dataset_glob,
    run_slug,
    session_log_filename,
    session_log_glob,
    slug_host,
    support_filename,
    support_glob,
)

__all__ = [
    "CASE_FILENAME", "CASE_FIELDS", "CASE_LABELS", "build_case", "case_path",
    "collect_case", "read_case", "write_case",
    "SIDECAR_SUFFIX", "sha256_bytes", "sha256_file", "read_sidecar", "verify",
    "write_sidecar",
    "ENVELOPE_KEYS", "build_envelope", "read_envelope_meta", "utc_now_iso",
    "utc_now_compact", "compact_from_iso",
    "TOOL_NAME", "JSON_TYPES", "SUPPORT_VARIANTS", "BUNDLE_GLOB", "RUN_FALLBACK",
    "dataset_filename", "dataset_glob", "support_filename", "support_glob",
    "session_log_filename", "session_log_glob", "slug_host", "run_slug",
]
