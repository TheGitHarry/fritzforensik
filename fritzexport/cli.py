"""fritzexport — CLI für Live-Datenabzug aus FRITZ!Box."""
from __future__ import annotations

import argparse
import getpass
import json
import logging
import os
import sys
from pathlib import Path

import requests

from fritzformat import (
    begin_line,
    build_case,
    collect_case,
    end_line,
    run_slug,
    sha256_file,
    utc_now_iso,
    write_case,
    write_sidecar,
)

from . import __version__, discover, output
from .auth import AuthError, fetch_users
from .client import FritzClient
from .extractors import EXTRACTORS, EXTRACTORS_WITH_AUDIO, EXTRACTORS_WITH_DIR
from .extractors.services import genutzte_services

EXIT_OK = 0
EXIT_AUTH = 1
EXIT_NETWORK = 2
EXIT_PARTIAL = 3
EXIT_AMBIGUOUS = 4
EXIT_NO_DISCOVERY = 5

PASSWORD_ENV = "FRITZ_PW"

log = logging.getLogger("fritzexport")


def _default_output() -> Path:
    """Default-Output: neben dem PyInstaller-Binary, sonst neben cwd."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "export"
    return Path.cwd() / "export"


def _normalize_host(host: str) -> str:
    """Ergänzt fehlendes Schema (Default https) und entfernt Trailing-Slash.

    Ohne Schema greift weder die TLS-Prüfung noch der Benutzer-Auto-Detect,
    weil requests dann mit MissingSchema abbricht.
    """
    host = host.strip().rstrip("/")
    if "://" not in host:
        host = "https://" + host
    return host


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="fritzexport",
        description="Live-Abzug forensisch relevanter Daten aus einer FRITZ!Box.",
    )
    p.add_argument("--host", help="Hostname oder IP (Default: SSDP-Auto-Discovery)")
    p.add_argument("--user", help="FRITZ!Box-Benutzername (außer bei --discover)")
    p.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Ausgabeverzeichnis (Default: ./export bzw. <binary>/export); "
            "je Lauf wird ein Zeitstempel angehängt, z.B. export_20260713T101530Z"
        ),
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
    p.add_argument("--case-id", default=None, help="Case-ID für den Fallkopf (sonst Abfrage)")
    p.add_argument("--item-id", default=None, help="Asservat / Item-ID (sonst Abfrage)")
    p.add_argument("--sb", default=None, help="Sachbearbeiter (sonst Abfrage)")
    p.add_argument("--date", default=None, help="Datum des Fallkopfs (Default: heute)")
    p.add_argument(
        "--no-prompt",
        action="store_true",
        help="Keine interaktive Fallkopf-Abfrage (für Automation)",
    )
    for name in EXTRACTORS:
        p.add_argument(f"--{name}", action="store_true", help=f"Extractor '{name}' ausführen")
    p.add_argument("--version", action="version", version=f"fritzexport {__version__}")
    p.add_argument("-v", "--verbose", action="store_true", help="Mehr Logausgabe")
    return p


_HELP_HINT = (
    "Wichtige Optionen:\n"
    "  --host IP        Ziel-Box (überspringt Auto-Discovery)\n"
    "  --user NAME      FRITZ!Box-Benutzername\n"
    "  --output DIR     Ausgabeverzeichnis (Default: ./export, mit Zeitstempel-Suffix je Lauf)\n"
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


def _select_box(boxes: list[discover.DiscoveredBox]) -> discover.DiscoveredBox | None:
    """Interaktive Auswahl bei mehreren Boxen.

    Liefert die gewählte Box oder None falls 'keine' / Abbruch / kein TTY.
    """
    if not (sys.stdin and sys.stdin.isatty()):
        return None
    sys.stdout.write("\nMehrere FRITZ!Boxen gefunden — bitte auswählen:\n")
    for i, b in enumerate(boxes, 1):
        label = b.friendly_name or b.model_name or "FRITZ!Box"
        sys.stdout.write(f"  {i}) {b.ip}  —  {label}\n")
    none_idx = len(boxes) + 1
    sys.stdout.write(f"  {none_idx}) keine\n\n")
    while True:
        try:
            raw = input(f"Auswahl [1-{none_idx}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            sys.stdout.write("\nAbgebrochen.\n")
            return None
        if raw.isdigit():
            idx = int(raw)
            if idx == none_idx:
                return None
            if 1 <= idx <= len(boxes):
                return boxes[idx - 1]
        sys.stdout.write("Ungültige Eingabe.\n")


def _probe_tls(target_url: str, args: argparse.Namespace) -> None:
    """Schaltet automatisch auf --insecure um, wenn das Box-Zertifikat
    nicht vertrauenswürdig ist (selbstsigniert). Nur HTTPS-Targets."""
    if args.insecure or not target_url.startswith("https://"):
        return
    try:
        requests.get(
            target_url + "/login_sid.lua?version=2",
            timeout=10,
        )
    except requests.exceptions.SSLError as e:
        log.warning(
            "TLS-Zertifikat der Box ist nicht vertrauenswürdig "
            "(vermutlich selbstsigniert): %s — schalte automatisch "
            "auf --insecure um.",
            e,
        )
        args.insecure = True
    except requests.RequestException:
        # andere Fehler werden später beim Login sichtbar
        pass


def _pause_if_double_clicked() -> None:
    """Hält die Konsole offen wenn das Binary per Windows-Doppelklick
    gestartet wurde (sonst schließt das Fenster sofort beim Exit).

    Erkennung über GetConsoleProcessList: nur unser Prozess hängt am
    Konsolenfenster → Konsole gehört uns → kein Terminal-Aufruf.
    """
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        process_list = (ctypes.c_ulong * 4)()
        count = ctypes.windll.kernel32.GetConsoleProcessList(process_list, 4)
    except Exception:
        return
    if count > 1:
        return
    try:
        sys.stderr.write("\n[Drücken Sie Enter zum Beenden ...]")
        sys.stderr.flush()
        sys.stdin.readline()
    except (EOFError, KeyboardInterrupt):
        pass


def _list_users(base_url: str, verify_tls: bool) -> list[str]:
    """Fragt die Box nach ihrer Benutzerliste (leer bei Fehler/alter Firmware)."""
    session = requests.Session()
    session.verify = verify_tls
    if not verify_tls:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    try:
        return fetch_users(base_url, session)
    finally:
        session.close()


def _autodetect_user(base_url: str, verify_tls: bool) -> str | None:
    """Gibt den Benutzernamen zurück wenn die Box genau einen kennt, sonst None."""
    users = _list_users(base_url, verify_tls)
    return users[0] if len(users) == 1 else None


def _select_user(users: list[str]) -> str | None:
    """Interaktive Auswahl bei mehreren Benutzern.

    Liefert den gewählten Namen oder None bei Abbruch / kein TTY.
    """
    if not (sys.stdin and sys.stdin.isatty()):
        return None
    sys.stdout.write("\nMehrere Benutzer auf der Box — bitte auswählen:\n")
    for i, name in enumerate(users, 1):
        sys.stdout.write(f"  {i}) {name}\n")
    sys.stdout.write("\n")
    while True:
        try:
            raw = input(f"Auswahl [1-{len(users)}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            sys.stdout.write("\nAbgebrochen.\n")
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(users):
            return users[int(raw) - 1]
        sys.stdout.write("Ungültige Eingabe.\n")


def _resolve_user(base_url: str, args: argparse.Namespace) -> str | None:
    """Ermittelt den Benutzernamen: --user > Auto (genau einer) > interaktiv.

    Bei mehreren bekannten Benutzern wird eine Auswahl angeboten; ist die
    Liste nicht abrufbar (alte Firmware), wird nach freiem Text gefragt.
    Gibt None zurück, wenn nichts aufgelöst werden konnte (Meldung erfolgt hier).
    """
    if args.user:
        return args.user

    try:
        users = _list_users(base_url, verify_tls=not args.insecure)
    except requests.exceptions.SSLError as e:
        # Box-Zertifikat nicht vertrauenswürdig (selbstsigniert). Auf insecure
        # umschalten und den Read wiederholen, statt den Anwender zu fragen.
        # args.insecure gilt danach auch für den folgenden Login.
        log.warning(
            "TLS-Zertifikat der Box nicht vertrauenswürdig beim Benutzer-Read "
            "(%s) — schalte auf --insecure um und versuche erneut.", e,
        )
        args.insecure = True
        users = _list_users(base_url, verify_tls=False)
    if len(users) == 1:
        log.info("Einzelner Benutzer erkannt: %s — wird automatisch verwendet", users[0])
        return users[0]
    if len(users) > 1:
        chosen = _select_user(users)
        if chosen is None:
            log.error(
                "Mehrere Benutzer (%s), keine Auswahl möglich — --user explizit angeben.",
                ", ".join(users),
            )
        return chosen

    # Liste leer trotz erfolgreicher Abfrage (kein Zertifikatsproblem mehr —
    # SSL wird oben abgefangen): Box liefert keine Users-Sektion, z.B. alte
    # Firmware. Erst hier — als letzter Ausweg — den Anwender fragen.
    log.info(
        "Box lieferte keine Benutzerliste (auch mit deaktivierter TLS-Prüfung) "
        "— bitte Benutzer angeben."
    )
    if not (sys.stdin and sys.stdin.isatty()):
        log.error("--user ist erforderlich (Benutzerliste nicht abrufbar).")
        return None
    try:
        name = input("Benutzername: ").strip()
    except (EOFError, KeyboardInterrupt):
        sys.stdout.write("\nAbgebrochen.\n")
        return None
    if not name:
        sys.stdout.write("Kein Benutzername eingegeben.\n")
        return None
    return name


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


def _close_log_file() -> None:
    """Logdatei schließen, abhängen und ihre Sidecar schreiben.

    Windows sperrt ein Verzeichnis, solange darin eine Datei offen ist, und der
    FileHandler bleibt sonst bis Prozessende offen (``rename`` scheiterte dort mit
    WinError 32). Der StreamHandler bleibt bestehen, damit die Abschlussmeldung
    weiterhin auf stderr geht.

    Die Sidecar entsteht **hier** und nirgends sonst: Erst wenn der Handler zu ist,
    steht der Inhalt fest. Sie ist nötig, weil das Log Beweislast trägt — der
    Sicherungszeitraum und der Versatz der Box-Uhr stammen allein aus seinen
    Markerzeilen. Ohne Prüfsumme fiele es nicht nur aus der Chain-of-Custody-Tabelle
    des Reports (die entsteht aus den vorhandenen Sidecars), sondern eine Umdatierung
    der Marker bliebe unbemerkt, während der Report weiter alles als verifiziert
    meldet.

    Das spätere Umbenennen des Verzeichnisses ist unschädlich: :func:`verify`
    vergleicht allein den Digest, nicht den in der Sidecar genannten Dateinamen.
    """
    root = logging.getLogger()
    for h in list(root.handlers):
        if isinstance(h, logging.FileHandler):
            path = Path(h.baseFilename)
            h.flush()
            h.close()
            root.removeHandler(h)
            try:
                write_sidecar(path, sha256_file(path))
            except OSError as e:
                sys.stderr.write(f"WARN: Sidecar für {path.name} nicht schreibbar: {e}\n")


def _finalize_output_dir(output_dir: Path, case: dict, run_stamp: str) -> Path:
    """Abzugsverzeichnis auf den sprechenden Namen bringen; gibt den Pfad zurück.

    Läuft als **letzter** Schritt, wenn nichts mehr in die Logdatei geschrieben
    wird. Ohne Fallkopf bleibt der Zeitstempelname bestehen. Scheitert das
    Umbenennen, behält der Abzug seinen bisherigen Namen — er ist vollständig, und
    ein fertiger Abzug darf nicht an der Benennung scheitern.

    Das Log wird **vor** jeder Rückgabe geschlossen, nicht erst kurz vorm
    ``rename``: Es bekommt dabei seine Sidecar, und die braucht auch ein Abzug, der
    gar nicht umbenannt wird.
    """
    _close_log_file()
    slug = run_slug(case.get("case_id", ""), case.get("item_id", ""), run_stamp)
    ziel = output_dir.parent / slug
    if ziel == output_dir:
        return output_dir
    if ziel.exists():
        sys.stderr.write(f"WARN: {ziel.name} existiert bereits — Abzug bleibt unter "
                         f"{output_dir.name}.\n")
        return output_dir

    try:
        output_dir.rename(ziel)
    except OSError as e:
        sys.stderr.write(f"WARN: Umbenennen nach {ziel.name} fehlgeschlagen ({e}) — "
                         f"Abzug liegt unter {output_dir.name}.\n")
        return output_dir
    return ziel


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
        chosen = _select_box(boxes)
        if chosen is None:
            log.error(
                "Keine Box gewählt — Abbruch. "
                "Alternativ --host explizit angeben."
            )
            return None, None, EXIT_AMBIGUOUS
        target = chosen.url_https()
        label = chosen.friendly_name or chosen.model_name or "FRITZ!Box"
        log.info("Ausgewählt: %s at %s", label, chosen.ip)
        meta = {
            "discovery_method": "ssdp",
            "target": target,
            "discovered": chosen.to_dict(),
        }
        return target, meta, EXIT_OK

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

    if args.host:
        args.host = _normalize_host(args.host)

    run_stamp = output._utc_now_compact()
    base_dir = args.output or _default_output()
    output_dir = base_dir.parent / f"{base_dir.name}_{run_stamp}"

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
        log_file = output_dir / f"fritzexport_{run_stamp}.log"

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
            chosen = _select_box(boxes)
            if chosen is None:
                sys.stdout.write(
                    "\nKeine Box gewählt — Abbruch. "
                    "Alternativ --host explizit angeben:\n\n"
                )
                sys.stdout.write(_HELP_HINT)
                return EXIT_AMBIGUOUS
            box = chosen
        else:
            box = boxes[0]
        label = box.friendly_name or box.model_name or "FRITZ!Box"
        sys.stdout.write(f"Gefundene FRITZ!Box: {box.ip}  —  {label}\n\n")
        args.host = box.url_https()
        _probe_tls(args.host, args)
        args.user = _resolve_user(args.host, args)
        if not args.user:
            return EXIT_AUTH

    target_url, discovery_meta, exit_code = _resolve_target(args)
    if exit_code != EXIT_OK:
        return exit_code
    assert target_url is not None

    _probe_tls(target_url, args)

    args.user = _resolve_user(target_url, args)
    if not args.user:
        return EXIT_AUTH

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

    # Fallkopf vor dem Abzug erheben — hier weiß der Anwender noch, welches
    # Asservat vor ihm liegt; nach dem Lauf ist der Moment vorbei.
    case = collect_case(args, intro="\nFallkopf für dieses Asservat (Enter = leer):")

    if not client.tr064_available():
        log.warning(
            "TR-064-Port 49000 nicht erreichbar. "
            "Extractoren ohne TR-064 oder Port-49000-Fallback werden leere Ergebnisse liefern: "
            "wan, dhcp, portforward, storage"
        )
    else:
        # Was die Box anbietet, wissen wir erst jetzt — und nur jetzt. Der
        # Hinweis nennt Dienste, die kein Extractor abholt; das ist keine
        # Fehlfunktion, sondern die Kandidatenliste für künftige Extractoren.
        # Vollständig steht der Abgleich in der Datenart `services`.
        angeboten = client.tr064_services() if hasattr(client, "tr064_services") else []
        if angeboten:
            genutzt = genutzte_services()
            offen = sorted(d["service_type"] for d in angeboten
                           if d["service_type"] not in genutzt)
            if offen:
                log.info(
                    "Box bietet %d TR-064-Dienste an, davon %d ohne Extractor: %s",
                    len(angeboten), len(offen), ", ".join(offen),
                )

    failures: list[str] = []
    # Sicherungsvorgang = erster bis letzter Datenabruf. Der Report weist diesen
    # Zeitraum aus; ohne die Marker müsste er ihn aus den Einzel-Zeitstempeln der
    # Dateien schätzen.
    log.info(begin_line(utc_now_iso()))
    try:
        for name in _selected_extractors(args):
            log.info("Starte Extractor: %s", name)
            try:
                if name in EXTRACTORS_WITH_AUDIO:
                    audio_dir = output_dir / f"{name}_audio"
                    records, extra_meta = EXTRACTORS[name](client, audio_dir)
                elif name in EXTRACTORS_WITH_DIR:
                    records, extra_meta = EXTRACTORS[name](client, output_dir)
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
        # Ende vor dem Fallkopf: Der ist eine Bearbeiterangabe, kein Datenabruf.
        # Im finally, damit auch ein abgebrochener Lauf ein Ende protokolliert.
        log.info(end_line(utc_now_iso()))

    case_file = write_case(output_dir, build_case(**case, written_at=utc_now_iso()))
    log.info("Fallkopf → %s", case_file)

    # Ab hier darf nichts mehr in die Logdatei — sie wird gleich geschlossen,
    # damit das Verzeichnis umbenannt werden kann.
    if failures:
        log.warning("Fehlgeschlagene Extractoren: %s", ", ".join(failures))
    exit_code = EXIT_PARTIAL if failures else EXIT_OK

    final_dir = _finalize_output_dir(output_dir, case, run_stamp)
    sys.stderr.write(f"\nAbzug abgelegt in: {final_dir}\n")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
