"""CLI — geführter Feld-Ablauf.

    fritzreport [bundle] [-o report.html] [--open]

Ohne ``bundle``-Argument sucht fritzreport fritzexport-Bundles im aktuellen
Verzeichnis (Auto-Discovery, analog zu fritzexport): genau eines → direkt nehmen,
mehrere → nummerierte Auswahl. Danach werden die Kopf-Felder (Case-ID, Item-ID,
SB, Datum) interaktiv abgefragt (per CLI-Flag gesetzte Werte überspringen die
Abfrage). Der Report bekommt einen sprechenden Namen und wird ins **aktuelle
Arbeitsverzeichnis** geschrieben — nicht in den Beweismittel-Ordner.

Neben dem Report entsteht eine ``<report>.html.sha256``-Sidecar im selben Format
wie im Bundle (``sha256sum -c``-kompatibel), damit auch das Berichtsdokument
selbst einen Integritätsnachweis hat.
"""
from __future__ import annotations

import argparse
import re
import sys
import webbrowser
from pathlib import Path

from fritzformat import BUNDLE_GLOB, CASE_LABELS, collect_case, read_case, utc_now_iso
from fritzformat.digest import sha256_bytes, write_sidecar

from . import __version__
from .bundle import load_bundle
from .model import build_model
from .render import _pick_device, build_html
from .supportdata import analyze


#: Zeitstempel der Report-Erzeugung — Format aus fritzformat, damit Report und
#: Bundle dieselbe Schreibweise verwenden.
_now_iso = utc_now_iso


# ───────────────────────── Bundle-Discovery ─────────────────────────────────

def is_bundle(d: Path) -> bool:
    """Ein Verzeichnis ist ein fritzexport-Bundle, wenn es mindestens eine
    ``fritzexport_<host>_<ts>_<typ>.json`` enthält."""
    return d.is_dir() and any(d.glob(BUNDLE_GLOB))


def discover_bundles(base: Path) -> list[Path]:
    """Bundles im Verzeichnis ``base`` finden: ``base`` selbst (falls Bundle)
    und direkte Unterverzeichnisse. Nach Name sortiert."""
    found = []
    if is_bundle(base):
        found.append(base)
    found += sorted(p for p in base.iterdir() if is_bundle(p))
    return found


def resolve_bundle(arg: Path | None) -> Path:
    """Bundle bestimmen: explizites Argument oder Auto-Discovery im cwd."""
    if arg is not None:
        if not arg.is_dir():
            raise SystemExit(f"Fehler: Bundle-Verzeichnis nicht gefunden: {arg}")
        return arg

    cands = discover_bundles(Path.cwd())
    if not cands:
        raise SystemExit(
            "Fehler: kein fritzexport-Bundle im aktuellen Verzeichnis gefunden.\n"
            "Bundle-Verzeichnis explizit angeben: fritzreport <verzeichnis>")
    if len(cands) == 1:
        print(f"Bundle: {cands[0].name}", file=sys.stderr)
        return cands[0]

    if not sys.stdin.isatty():
        names = ", ".join(c.name for c in cands)
        raise SystemExit(f"Fehler: mehrere Bundles gefunden ({names}). "
                         f"Bitte eines explizit angeben.")
    print("Mehrere Bundles gefunden:", file=sys.stderr)
    for i, c in enumerate(cands, 1):
        print(f"  {i}) {c.name}", file=sys.stderr)
    while True:
        try:
            ans = input(f"Auswahl [1-{len(cands)}, Enter=1]: ").strip()
        except EOFError:
            ans = ""
        if not ans:
            return cands[0]
        if ans.isdigit() and 1 <= int(ans) <= len(cands):
            return cands[int(ans) - 1]
        print("  Ungültige Eingabe.", file=sys.stderr)


# ───────────────────────── Kopf-Felder ──────────────────────────────────────

def collect_header(args, bundle_dir: Path | None = None) -> dict:
    """Kopf-Felder erheben; eine ``case.json`` im Bundle belegt die Abfrage vor.

    Hat fritzexport den Fallkopf bereits erfasst, werden die Werte als Vorgabe
    angeboten (mit Enter zu übernehmen, weiterhin überschreibbar). Fehlt die Datei
    oder ist sie unbrauchbar, wird wie bisher gefragt — ein Bundle ohne Fallkopf
    ist gültig.
    """
    defaults = read_case(bundle_dir) if bundle_dir else {}
    if defaults and any(defaults.values()):
        gefunden = ", ".join(f"{CASE_LABELS[k]}: {v}" for k, v in defaults.items() if v)
        print(f"Fallkopf aus dem Bundle übernommen ({gefunden}).", file=sys.stderr)
    header = collect_case(args, defaults=defaults,
                          intro="Kopf-Felder für den Report (Enter = leer):")
    header["generated_at"] = _now_iso()
    return header


# ───────────────────────── Ausgabename ──────────────────────────────────────

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _slug(value: str) -> str:
    return _SAFE.sub("-", value.strip()).strip("-")


def default_output_name(header: dict, box_label: str) -> Path:
    """Sprechender Report-Name im aktuellen Arbeitsverzeichnis:
    ``<Case>_<Item>_<Box>_<Datum>.html`` (leere Teile entfallen)."""
    parts = [header.get("case_id", ""), header.get("item_id", ""),
             box_label, header.get("date", "")]
    slug = "_".join(_slug(p) for p in parts if p and _slug(p))
    return Path.cwd() / (f"{slug}.html" if slug else "fritzreport.html")


# ───────────────────────── main ─────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="fritzreport",
        description="Forensischer HTML-Report aus einem fritzexport-Bundle. "
                    "Ohne Bundle-Argument wird im aktuellen Verzeichnis gesucht.")
    p.add_argument("bundle", type=Path, nargs="?", default=None,
                   help="Bundle-Verzeichnis (Default: Auto-Discovery im cwd)")
    p.add_argument("-o", "--output", type=Path, default=None,
                   help="Ziel-HTML (Default: sprechender Name im cwd)")
    p.add_argument("--open", action="store_true", help="Report danach im Browser öffnen")
    p.add_argument("--case-id", default=None, help="Case-ID (sonst Abfrage)")
    p.add_argument("--item-id", default=None, help="Asservat / Item-ID (sonst Abfrage)")
    p.add_argument("--sb", default=None, help="Sachbearbeiter (sonst Abfrage)")
    p.add_argument("--date", default=None, help="Datum (Default: heute)")
    p.add_argument("--no-prompt", action="store_true",
                   help="Kopf-Felder nicht abfragen (CLI-Werte bzw. leer)")
    p.add_argument("--version", action="version", version=f"fritzreport {__version__}")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    bundle_dir = resolve_bundle(args.bundle)
    try:
        bundle = load_bundle(bundle_dir)
    except (NotADirectoryError, FileNotFoundError) as e:
        print(f"Fehler: {e}", file=sys.stderr)
        return 2

    header = collect_header(args, bundle_dir)

    model = build_model(bundle)
    master_name = model.master.get("name", "") or (model.real_aps[0] if model.real_aps else "")
    support = analyze(bundle, model.real_aps, master_name)

    html = build_html(bundle, model, support, header)

    device = _pick_device(model.mesh_nodes, model.meta.get("host", ""))
    box_label = device.get("model", "") or bundle_dir.name
    out = args.output or default_output_name(header, box_label)
    # Über die kodierten Bytes gehen, damit die Sidecar exakt das beschreibt,
    # was auf der Platte liegt (write_text würde sonst zweimal kodieren).
    payload = html.encode("utf-8")
    out.write_bytes(payload)
    report_digest = sha256_bytes(payload)
    sidecar = write_sidecar(out, report_digest)

    proofs = support["proofs"]
    mism = sum(1 for e in bundle.coc if e.status == "mismatch")
    kb = out.stat().st_size / 1024
    print(f"Report: {out}  ({kb:.0f} KB)")
    print(f"  SHA256: {report_digest}")
    print(f"  Sidecar: {sidecar.name}")
    print(f"  Gerät: {box_label}")
    print(f"  Integrität: {len(bundle.coc)} Dateien geprüft, "
          + ("alle ✔ verifiziert" if not mism else f"{mism} MISMATCH ✘"))
    print(f"  Hosts {len(model.hosts)} · Clients {len(model.wifi)} · "
          f"Mesh {len(model.mesh_nodes)} ({len(model.real_aps)} echte APs) · "
          f"Events {len(model.events)} · Anrufe {len(model.calls)} · Telefonbuch {len(model.phonebook)}")
    d1d2 = sum(1 for p in proofs if "D2" in p["grades"])
    d1d3 = sum(1 for p in proofs if "D3" in p["grades"])
    print(f"  Verbindungsnachweise: {len(proofs)} "
          f"(methode.md/D1+D2: {d1d2}, 802.11/D1+D3: {d1d3})")

    if args.open:
        webbrowser.open(out.resolve().as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
