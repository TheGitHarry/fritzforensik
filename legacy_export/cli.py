"""legacy_export — CLI für Live-Datenabzug aus FRITZ!Box."""
from __future__ import annotations

import argparse
import getpass
import json
import logging
import os
import sys
from pathlib import Path

import requests

from . import __version__, discover, output
from .auth import AuthError
from .client import FritzClient
from .extractors import EXTRACTORS, EXTRACTORS_WITH_AUDIO

EXIT_OK = 0
EXIT_AUTH = 1
EXIT_NETWORK = 2
EXIT_PARTIAL = 3
EXIT_AMBIGUOUS = 4
EXIT_NO_DISCOVERY = 5

PASSWORD_ENV = "FRITZ_PW"

log = logging.getLogger("legacy_export")


def _default_output() -> Path:
    """Default-Output: neben dem PyInstaller-Binary, sonst neben cwd."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "export"
    return Path.cwd() / "export"


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="legacy_export",
        description="Live-Abzug forensisch relevanter Daten aus einer FRITZ!Box.",
    )
    p.add_argument("--host", help="Hostname oder IP (Default: SSDP-Auto-Discovery)")
    p.add_argument("--user", help="FRITZ!Box-Benutzername (außer bei --discover)")
    p.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Ausgabeverzeichnis (Default: ./export bzw. <binary>/export)",
    )
    p.add_argument(
        "--password-env",
        default=PASSWORD_ENV,
        help=f"Name der Env-Var, die das Passwort enthält (Default: {PASSWORD_ENV})",
    )
    p.add_argument(
        "--discover",
        action="store_true",
        help="Nur Discovery-Lauf, JSON-Liste auf stdout, exit 0",
    )
    p.add_argument(
        "--iface",
        default=None,
        help="Source-IP der Netzwerk-Schnittstelle für Multicast (z.B. 192.168.2.228)",
    )
    p.add_argument("--all", action="store_true", help="Alle Extractoren ausführen (Default falls nichts gewählt)")
    p.add_argument(
        "--insecure",
        action="store_true",
        help="TLS-Zertifikat der Box NICHT prüfen (für selbstsignierte Box-Zertifikate)",
    )
    for name in EXTRACTORS:
        p.add_argument(f"--{name}", action="store_true", help=f"Extractor '{name}' ausführen")
    p.add_argument("--version", action="version", version=f"legacy_export {__version__}")
    p.add_argument("-v", "--verbose", action="store_true", help="Mehr Logausgabe")
    return p


_HELP_HINT = (
    "Wichtige Optionen:\n"
    "  --host IP        Ziel-Box (überspringt Auto-Discovery)\n"
    "  --user NAME      FRITZ!Box-Benutzername\n"
    "  --output DIR     Ausgabeverzeichnis (Default: ./export)\n"
    "  --discover       Nur Discovery-Lauf (JSON auf stdout, für Scripting)\n"
    "  --iface IP       Multicast-Schnittstelle\n"
    "  --insecure       TLS-Zertifikat nicht prüfen\n"
    "  -v, --verbose    Mehr Logausgabe\n"
    "  --help           Alle Optionen anzeigen\n"
)


def _is_implicit_discover(args: argparse.Namespace) -> bool:
    """True wenn kein Action-Argument gesetzt — kein --host, --user, --discover, kein Extractor."""
    if args.discover or args.host or args.user or args.all:
        return False
    return not any(getattr(args, name, False) for name in EXTRACTORS)


def _selected_extractors(args: argparse.Namespace) -> list[str]:
    selected = [name for name in EXTRACTORS if getattr(args, name)]
    if args.all or not selected:
        return list(EXTRACTORS)
    return selected


def _resolve_password(env_name: str) -> str:
    pw = os.environ.get(env_name)
    if pw:
        return pw
    return getpass.getpass(f"FRITZ!Box-Passwort (oder ${env_name} setzen): ")


def _configure_logging(verbose: bool, log_file: Path | None) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s %(levelname)s %(message)s"
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if log_file is not None:
        try:
            handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
        except OSError as e:
            sys.stderr.write(f"WARN: Log-Datei {log_file} nicht schreibbar: {e}\n")
    logging.basicConfig(level=level, format=fmt, handlers=handlers, force=True)


def _resolve_target(args: argparse.Namespace) -> tuple[str | None, dict | None, int]:
    """Liefert (target_url, discovery_meta, exit_code).

    exit_code != 0 bedeutet: nicht weitermachen, exit_code zurückgeben.
    """
    if args.host:
        return args.host, {"discovery_method": "manual", "target": args.host}, EXIT_OK

    log.info("Suche FRITZ!Box im LAN per SSDP …")
    try:
        boxes = discover.discover(iface=args.iface)
    except OSError as e:
        log.error("Discovery-Fehler: %s", e)
        return None, None, EXIT_NO_DISCOVERY

    if not boxes:
        log.error(
            "Keine FRITZ!Box im LAN gefunden. --host explizit setzen, "
            "oder Multicast-Schnittstelle per --iface IP wählen."
        )
        return None, None, EXIT_NO_DISCOVERY

    if len(boxes) > 1:
        log.error("Mehrere FRITZ!Boxen gefunden — bitte --host explizit angeben:")
        for b in boxes:
            label = b.friendly_name or b.model_name or "FRITZ!Box"
            log.error("  %s — %s (%s)", b.ip, label, b.location)
        return None, None, EXIT_AMBIGUOUS

    box = boxes[0]
    target = box.url_https()
    label = box.friendly_name or box.model_name or "FRITZ!Box"
    log.info("Discovered %s at %s", label, box.ip)
    meta = {
        "discovery_method": "ssdp",
        "target": target,
        "discovered": box.to_dict(),
    }
    return target, meta, EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    output_dir = args.output or _default_output()

    log_file: Path | None = None
    if not args.discover:
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            sys.stderr.write(f"ERROR: Output-Verzeichnis {output_dir} nicht erstellbar: {e}\n")
            return EXIT_NETWORK
        if not os.access(output_dir, os.W_OK):
            sys.stderr.write(f"ERROR: Output-Verzeichnis {output_dir} nicht beschreibbar (read-only?).\n")
            return EXIT_NETWORK
        log_file = output_dir / f"legacy_export_{output._utc_now_compact()}.log"

    _configure_logging(verbose=args.verbose, log_file=log_file)

    if args.discover:
        boxes = discover.discover(iface=args.iface)
        sys.stdout.write(
            json.dumps([b.to_dict() for b in boxes], indent=2, ensure_ascii=False) + "\n"
        )
        log.info("Discovery: %d FRITZ!Box(en) gefunden", len(boxes))
        return EXIT_OK

    if _is_implicit_discover(args):
        try:
            boxes = discover.discover(iface=args.iface)
        except OSError as e:
            sys.stdout.write(f"Discovery-Fehler: {e}\n")
            return EXIT_NO_DISCOVERY

        if not boxes:
            sys.stdout.write(
                "Keine FRITZ!Box im LAN gefunden.\n"
                "Tipp: Multicast-Schnittstelle per --iface IP wählen oder --host direkt setzen.\n\n"
            )
            sys.stdout.write(_HELP_HINT)
            return EXIT_NO_DISCOVERY

        if len(boxes) > 1:
            sys.stdout.write("Mehrere FRITZ!Boxen gefunden — bitte --host wählen:\n")
            for b in boxes:
                label = b.friendly_name or b.model_name or "FRITZ!Box"
                sys.stdout.write(f"  {b.ip}  —  {label}\n")
            sys.stdout.write("\n")
            sys.stdout.write(_HELP_HINT)
            return EXIT_AMBIGUOUS

        # Genau eine Box: direkt starten
        box = boxes[0]
        label = box.friendly_name or box.model_name or "FRITZ!Box"
        sys.stdout.write(f"Gefundene FRITZ!Box: {box.ip}  —  {label}\n\n")
        try:
            args.user = input("Benutzername: ").strip()
        except (EOFError, KeyboardInterrupt):
            sys.stdout.write("\nAbgebrochen.\n")
            return EXIT_AUTH
        if not args.user:
            sys.stdout.write("Kein Benutzername eingegeben.\n")
            return EXIT_AUTH
        args.host = box.url_https()

    if not args.user:
        log.error("--user ist erforderlich (außer bei --discover)")
        return EXIT_AUTH

    target_url, discovery_meta, exit_code = _resolve_target(args)
    if exit_code != EXIT_OK:
        return exit_code
    assert target_url is not None

    password = _resolve_password(args.password_env)
    if not password:
        log.error("Kein Passwort übergeben")
        return EXIT_AUTH

    try:
        client = FritzClient.login(
            target_url, args.user, password, verify_tls=not args.insecure
        )
        if args.insecure:
            log.warning("TLS-Verifikation deaktiviert (--insecure)")
    except AuthError as e:
        log.error("Authentifizierung fehlgeschlagen: %s", e)
        return EXIT_AUTH
    except requests.RequestException as e:
        log.error("Box nicht erreichbar: %s", e)
        return EXIT_NETWORK

    if not client.tr064_available():
        log.warning(
            "TR-064 nicht verfügbar (Port 49000 nicht erreichbar oder deaktiviert). "
            "Extractoren ohne Web-UI-Fallback werden fehlschlagen: "
            "hosts, wan, dhcp, portforward, storage"
        )

    failures: list[str] = []
    try:
        for name in _selected_extractors(args):
            log.info("Starte Extractor: %s", name)
            try:
                if name in EXTRACTORS_WITH_AUDIO:
                    audio_dir = output_dir / f"{name}_audio"
                    records, extra_meta = EXTRACTORS[name](client, audio_dir)
                else:
                    records = EXTRACTORS[name](client)
                    extra_meta = None
            except Exception as e:
                log.error("Extractor '%s' fehlgeschlagen: %s", name, e)
                failures.append(name)
                continue
            path = output.write(
                output_dir,
                target_url,
                name,
                records,
                discovery_meta=discovery_meta,
                extra_meta=extra_meta,
            )
            log.info("Extractor '%s': %d Records → %s", name, len(records), path)
    finally:
        client.close()

    if failures:
        log.warning("Fehlgeschlagene Extractoren: %s", ", ".join(failures))
        return EXIT_PARTIAL
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
