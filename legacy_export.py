#!/usr/bin/env python3
"""legacy_export — CLI für Live-Datenabzug aus FRITZ!Box."""
from __future__ import annotations

import argparse
import getpass
import logging
import os
import sys
from pathlib import Path

import requests

from legacy_export import __version__, output
from legacy_export.auth import AuthError
from legacy_export.client import FritzClient
from legacy_export.extractors import EXTRACTORS

EXIT_OK = 0
EXIT_AUTH = 1
EXIT_NETWORK = 2
EXIT_PARTIAL = 3

PASSWORD_ENV = "FRITZ_PW"

log = logging.getLogger("legacy_export")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="legacy_export",
        description="Live-Abzug forensisch relevanter Daten aus einer FRITZ!Box.",
    )
    p.add_argument("--host", required=True, help="Hostname oder IP (z.B. fritz.box)")
    p.add_argument("--user", required=True, help="FRITZ!Box-Benutzername")
    p.add_argument("--output", required=True, type=Path, help="Ausgabeverzeichnis")
    p.add_argument(
        "--password-env",
        default=PASSWORD_ENV,
        help=f"Name der Env-Var, die das Passwort enthält (Default: {PASSWORD_ENV})",
    )
    p.add_argument("--all", action="store_true", help="Alle Extractoren ausführen (Default falls nichts gewählt)")
    for name in EXTRACTORS:
        p.add_argument(f"--{name}", action="store_true", help=f"Extractor '{name}' ausführen")
    p.add_argument("--version", action="version", version=f"legacy_export {__version__}")
    p.add_argument("-v", "--verbose", action="store_true", help="Mehr Logausgabe")
    return p


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


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    password = _resolve_password(args.password_env)
    if not password:
        log.error("Kein Passwort übergeben")
        return EXIT_AUTH

    try:
        client = FritzClient.login(args.host, args.user, password)
    except AuthError as e:
        log.error("Authentifizierung fehlgeschlagen: %s", e)
        return EXIT_AUTH
    except requests.RequestException as e:
        log.error("Box nicht erreichbar: %s", e)
        return EXIT_NETWORK

    failures: list[str] = []
    try:
        for name in _selected_extractors(args):
            log.info("Starte Extractor: %s", name)
            try:
                records = EXTRACTORS[name](client)
            except Exception as e:
                log.error("Extractor '%s' fehlgeschlagen: %s", name, e)
                failures.append(name)
                continue
            path = output.write(args.output, args.host, name, records)
            log.info("Extractor '%s': %d Records → %s", name, len(records), path)
    finally:
        client.close()

    if failures:
        log.warning("Fehlgeschlagene Extractoren: %s", ", ".join(failures))
        return EXIT_PARTIAL
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
