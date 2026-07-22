"""CLI — legacy_report <bundle> [--output report.html].

Liest ein legacy_export-Bundle (Verzeichnis), verifiziert die Hashes, wertet die
Supportdaten aus und schreibt einen self-contained forensischen HTML-Report.

Die Kopf-Felder (Case-ID, Item-ID, SB, Datum) werden hier als CLI-Args
entgegengenommen — **wie sie im Feldeinsatz erhoben werden (Prompt/Config), ist
noch offen** und wird später geklärt.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import sys
import webbrowser
from pathlib import Path

from . import __version__
from .bundle import load_bundle
from .model import build_model
from .render import build_html
from .supportdata import analyze


def _today() -> str:
    return _dt.date.today().isoformat()


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="legacy_report",
        description="Forensischer HTML-Report aus einem legacy_export-Bundle.")
    p.add_argument("bundle", type=Path, help="Bundle-Verzeichnis (legacy_export-Export)")
    p.add_argument("-o", "--output", type=Path, default=None,
                   help="Ziel-HTML (Default: <bundle>/report.html)")
    p.add_argument("--open", action="store_true", help="Report danach im Browser öffnen")
    # Kopf-Felder: standardmäßig interaktiv abgefragt (Prompt). Wer sie hier
    # angibt, überspringt die Abfrage (Automation/Tests). --no-prompt erzwingt
    # nicht-interaktiv (leere/CLI-Werte, kein Fragen).
    p.add_argument("--case-id", default=None, help="Case-ID (sonst Abfrage)")
    p.add_argument("--item-id", default=None, help="Asservat / Item-ID (sonst Abfrage)")
    p.add_argument("--sb", default=None, help="Sachbearbeiter (sonst Abfrage)")
    p.add_argument("--date", default=None, help="Datum (Default: heute)")
    p.add_argument("--no-prompt", action="store_true",
                   help="Kopf-Felder nicht abfragen (nimmt CLI-Werte bzw. leer)")
    p.add_argument("--version", action="version", version=f"legacy_report {__version__}")
    return p


def collect_header(args) -> dict:
    """Kopf-Felder erheben: was per CLI kam, wird übernommen; der Rest wird
    interaktiv abgefragt (Prompt), sofern ein TTY vorhanden ist und nicht
    ``--no-prompt`` gesetzt wurde."""
    interactive = (not args.no_prompt) and sys.stdin.isatty() and sys.stdout.isatty()

    def field(cli_val, label, default=""):
        if cli_val is not None:          # explizit per CLI gesetzt
            return cli_val
        if not interactive:
            return default
        suffix = f" [{default}]" if default else ""
        try:
            ans = input(f"  {label}{suffix}: ").strip()
        except EOFError:
            ans = ""
        return ans or default

    if interactive and all(getattr(args, a) is None for a in ("case_id", "item_id", "sb")):
        print("Kopf-Felder für den Report (Enter = leer):", file=sys.stderr)
    return {
        "case_id": field(args.case_id, "Case-ID"),
        "item_id": field(args.item_id, "Asservat / Item-ID"),
        "sb": field(args.sb, "Sachbearbeiter (SB)"),
        "date": args.date or field(None, "Datum", _today()),
        "generated_at": _now_iso(),
    }


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    try:
        bundle = load_bundle(args.bundle)
    except (NotADirectoryError, FileNotFoundError) as e:
        print(f"Fehler: {e}", file=sys.stderr)
        return 2

    header = collect_header(args)

    model = build_model(bundle)
    master_name = model.master.get("name", "") or (model.real_aps[0] if model.real_aps else "")
    support = analyze(bundle, model.real_aps, master_name)

    html = build_html(bundle, model, support, header)
    out = args.output or (args.bundle / "report.html")
    out.write_text(html, encoding="utf-8")

    # --- Zusammenfassung (wie legacy_export)
    proofs = support["proofs"]
    mism = sum(1 for e in bundle.coc if e.status == "mismatch")
    kb = out.stat().st_size / 1024
    print(f"Report: {out}  ({kb:.0f} KB)")
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
