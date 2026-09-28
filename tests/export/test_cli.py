import argparse

import pytest
import requests

from fritzexport import cli


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("192.168.2.1", "https://192.168.2.1"),
        ("192.168.2.1:8443", "https://192.168.2.1:8443"),
        ("https://192.168.2.1/", "https://192.168.2.1"),
        ("http://fritz.box", "http://fritz.box"),
        ("  fritz.box  ", "https://fritz.box"),
    ],
)
def test_normalize_host(raw, expected):
    assert cli.normalize_host(raw) == expected


FP = "ab" * 32


def _selbstsigniert(monkeypatch, seen=None):
    def boom(url, timeout):
        if seen is not None:
            seen.append(url)
        raise requests.exceptions.SSLError("self-signed certificate")

    monkeypatch.setattr(cli.requests, "get", boom)
    monkeypatch.setattr(cli, "_server_fingerprint", lambda url: FP)


def _tls_args(**kw):
    return argparse.Namespace(**{"insecure": False, "tls_fingerprint": None, **kw})


def test_probe_tls_schaltet_nicht_still_auf_insecure(monkeypatch):
    """Sicherheitsbefund: Ein selbstsigniertes Zertifikat schaltete früher still auf
    --insecure — jedes Gerät, das sich als Box meldete, bekam die Anmeldung. Ohne
    Bestätigung (kein TTY) wird jetzt abgebrochen."""
    _selbstsigniert(monkeypatch)
    monkeypatch.setattr(cli, "_confirm_fingerprint", lambda url, fp: False)
    args = _tls_args()
    assert cli._probe_tls("https://192.168.2.1", args) is False
    assert args.insecure is False
    assert args.tls_fingerprint is None


def test_probe_tls_legt_bestaetigten_fingerabdruck_fest(monkeypatch):
    _selbstsigniert(monkeypatch)
    monkeypatch.setattr(cli, "_confirm_fingerprint", lambda url, fp: True)
    args = _tls_args()
    assert cli._probe_tls("https://192.168.2.1", args) is True
    assert args.tls_fingerprint == FP
    assert args.insecure is False


def test_probe_tls_greift_auch_bei_host_ohne_schema(monkeypatch):
    """Regression: blanke IP wurde vom TLS-Probe übersprungen, dadurch blieb
    der Benutzer-Auto-Detect ohne TLS-Festlegung und lieferte nichts."""
    seen = []
    _selbstsigniert(monkeypatch, seen)
    monkeypatch.setattr(cli, "_confirm_fingerprint", lambda url, fp: True)
    args = _tls_args()
    assert cli._probe_tls(cli.normalize_host("192.168.2.1"), args) is True
    assert seen == ["https://192.168.2.1/login_sid.lua?version=2"]
    assert args.tls_fingerprint == FP


def test_probe_tls_vorgegebener_fingerabdruck_muss_passen(monkeypatch):
    monkeypatch.setattr(cli, "_server_fingerprint", lambda url: FP)
    args = _tls_args(tls_fingerprint=":".join(["CD"] * 32))
    assert cli._probe_tls("https://192.168.2.1", args) is False

    args = _tls_args(tls_fingerprint=":".join(["AB"] * 32))
    assert cli._probe_tls("https://192.168.2.1", args) is True
    assert args.tls_fingerprint == FP


def test_probe_tls_insecure_bleibt_ausdruecklicher_verzicht(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("mit --insecure wird nichts geprüft")

    monkeypatch.setattr(cli.requests, "get", boom)
    monkeypatch.setattr(cli, "_server_fingerprint", boom)
    assert cli._probe_tls("https://192.168.2.1", _tls_args(insecure=True)) is True


def test_autodetect_user_bei_genau_einem_benutzer(monkeypatch):
    monkeypatch.setattr(cli, "fetch_users", lambda base_url, session: ["boxuser"])
    assert cli._autodetect_user("https://192.168.2.1", verify_tls=False) == "boxuser"


def test_autodetect_user_none_bei_mehreren(monkeypatch):
    monkeypatch.setattr(cli, "fetch_users", lambda base_url, session: ["a", "b"])
    assert cli._autodetect_user("https://192.168.2.1", verify_tls=False) is None


def test_resolve_user_nimmt_cli_arg_ohne_box_anfrage(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("Box darf bei gesetztem --user nicht befragt werden.")

    monkeypatch.setattr(cli, "_list_users", boom)
    args = argparse.Namespace(user="vorgabe", insecure=False)
    assert cli._resolve_user("https://192.168.2.1", args) == "vorgabe"


def test_resolve_user_auto_bei_genau_einem(monkeypatch):
    monkeypatch.setattr(cli, "_list_users", lambda b, verify_tls, fingerprint=None: ["boxuser"])
    args = argparse.Namespace(user=None, insecure=False)
    assert cli._resolve_user("https://192.168.2.1", args) == "boxuser"


def test_resolve_user_prompt_bei_mehreren(monkeypatch):
    """Regression: mit --host und mehreren Benutzern muss nachgefragt werden,
    statt hart mit '--user ist erforderlich' abzubrechen."""
    monkeypatch.setattr(cli, "_list_users", lambda b, verify_tls, fingerprint=None: ["fritz1310", "boxuser"])
    seen = {}

    def fake_select(users):
        seen["users"] = users
        return "boxuser"

    monkeypatch.setattr(cli, "_select_user", fake_select)
    args = argparse.Namespace(user=None, insecure=False)
    assert cli._resolve_user("https://192.168.2.1", args) == "boxuser"
    assert seen["users"] == ["fritz1310", "boxuser"]


def test_resolve_user_mehrere_ohne_tty_ergibt_none(monkeypatch):
    monkeypatch.setattr(cli, "_list_users", lambda b, verify_tls, fingerprint=None: ["a", "b"])
    monkeypatch.setattr(cli, "_select_user", lambda users: None)
    args = argparse.Namespace(user=None, insecure=False)
    assert cli._resolve_user("https://192.168.2.1", args) is None


def test_resolve_user_sslerror_schaltet_nicht_auf_insecure(monkeypatch):
    """Sicherheitsbefund: Früher wurde bei einem Zertifikatsfehler still auf
    insecure umgeschaltet und der Read wiederholt. Die TLS-Prüfung legt jetzt
    `_probe_tls` fest; ein Fehler hier heißt: anderes Zertifikat als bestätigt."""
    calls = []

    def fake_list_users(base_url, verify_tls, fingerprint=None):
        calls.append((verify_tls, fingerprint))
        raise requests.exceptions.SSLError("fingerprint mismatch")

    monkeypatch.setattr(cli, "_list_users", fake_list_users)
    args = argparse.Namespace(user=None, insecure=False, tls_fingerprint=FP)
    assert cli._resolve_user("https://192.168.2.1", args) is None
    assert args.insecure is False
    assert calls == [(True, FP)]


def test_resolve_user_freitext_wenn_liste_leer(monkeypatch):
    monkeypatch.setattr(cli, "_list_users", lambda b, verify_tls, fingerprint=None: [])
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "manuell")
    args = argparse.Namespace(user=None, insecure=False)
    assert cli._resolve_user("https://192.168.2.1", args) == "manuell"


def test_output_dir_bekommt_zeitstempel_suffix(monkeypatch, tmp_path):
    monkeypatch.setattr(cli.output, "_utc_now_compact", lambda: "20260713T101530Z")
    monkeypatch.setattr(cli, "_resolve_target", lambda args: (None, None, cli.EXIT_NO_DISCOVERY))

    rc = cli.main(["--host", "192.168.2.1", "--user", "x", "--output", str(tmp_path / "case42")])

    assert rc == cli.EXIT_NO_DISCOVERY
    run_dir = tmp_path / "case42_20260713T101530Z"
    assert run_dir.is_dir()
    assert (run_dir / "fritzexport_20260713T101530Z.log").exists()


# ───────────────────────── Verzeichnis-Benennung ─────────────────────────────

def _lauf(monkeypatch, tmp_path, case_args, records=None):
    """Vollständigen main()-Lauf mit gemocktem Client/Extractor fahren."""
    import logging

    from fritzexport.extractors import EXTRACTORS

    monkeypatch.setattr(cli.output, "_utc_now_compact", lambda: "20260713T101530Z")
    monkeypatch.setattr(cli, "_resolve_target",
                        lambda args: ("https://192.168.2.1", None, cli.EXIT_OK))
    monkeypatch.setattr(cli, "_probe_tls", lambda url, args: True)
    monkeypatch.setattr(cli, "_resolve_user", lambda url, args: "admin")
    monkeypatch.setattr(cli, "_resolve_password", lambda env: "geheim")

    class _Client:
        tr064_scheme = "https"
        def tr064_available(self): return True
        def close(self): pass

    monkeypatch.setattr(cli.FritzClient, "login",
                        classmethod(lambda cls, *a, **kw: _Client()))
    monkeypatch.setitem(EXTRACTORS, "hosts", lambda c: records or [{"mac": "aa:bb"}])

    rc = cli.main(["--host", "192.168.2.1", "--user", "admin", "--hosts",
                   "--no-prompt", "--output", str(tmp_path / "export"), *case_args])
    logging.shutdown()
    return rc


def test_verzeichnis_bekommt_fallkopf_namen(monkeypatch, tmp_path):
    """Der Abzug landet unter <Case>_<Item>_<ts> — demselben Stamm wie der Report."""
    rc = _lauf(monkeypatch, tmp_path,
               ["--case-id", "C-2026-0815", "--item-id", "A-01", "--sb", "X"])
    assert rc == cli.EXIT_OK
    assert (tmp_path / "C-2026-0815_A-01_20260713T101530Z").is_dir()
    assert not (tmp_path / "export_20260713T101530Z").exists()


def test_ohne_fallkopf_bleibt_zeitstempelname(monkeypatch, tmp_path):
    """Ein Abzug ohne Fallkopf ist der Normalfall — kein Umbenennen, kein Fehler."""
    rc = _lauf(monkeypatch, tmp_path, [])
    assert rc == cli.EXIT_OK
    assert (tmp_path / "export_20260713T101530Z").is_dir()


def test_logdatei_wandert_mit_und_ist_gefuellt(monkeypatch, tmp_path):
    """Das Log muss im umbenannten Verzeichnis liegen UND Inhalt haben — es wird
    ab der ersten Zeile geschrieben, damit es bei einem Absturz nicht fehlt."""
    _lauf(monkeypatch, tmp_path, ["--case-id", "C-1"])
    log = tmp_path / "C-1_20260713T101530Z" / "fritzexport_20260713T101530Z.log"
    assert log.exists(), "Logdatei ist beim Umbenennen verlorengegangen"
    assert log.stat().st_size > 0, "Logdatei ist leer — wurde sie gepuffert?"


def test_kein_offener_log_handler_nach_dem_lauf(monkeypatch, tmp_path):
    """Wirksamkeitsprobe für Windows: ein offener FileHandler sperrt das
    Verzeichnis und ließe rename() mit WinError 32 scheitern. Auf Linux fällt das
    nie auf — deshalb dieser Test."""
    import logging

    _lauf(monkeypatch, tmp_path, ["--case-id", "C-1"])
    offen = [h for h in logging.getLogger().handlers
             if isinstance(h, logging.FileHandler)]
    assert not offen, f"FileHandler nach dem Umbenennen noch offen: {offen}"


def test_bundle_bleibt_nach_umbenennen_ladbar(monkeypatch, tmp_path):
    """Gegenprobe: Nach dem Umbenennen muss der Report das Bundle noch lesen und
    alle Sidecars verifizieren können — hier fielen absolute Pfade auf."""
    from fritzreport.bundle import load_bundle
    from fritzreport.cli import is_bundle

    _lauf(monkeypatch, tmp_path, ["--case-id", "C-1", "--item-id", "A-01"])
    neu = tmp_path / "C-1_A-01_20260713T101530Z"

    assert is_bundle(neu), "umbenanntes Verzeichnis wird nicht mehr als Bundle erkannt"
    b = load_bundle(neu)
    assert b.ds("hosts").present
    assert b.integrity_ok, "Sidecars verifizieren nach dem Umbenennen nicht mehr"


def test_umbenennen_scheitert_lautlos_nicht(monkeypatch, tmp_path):
    """Existiert der Zielname schon, bleibt der Abzug unter seinem alten Namen —
    ein fertiger Abzug darf nicht an der Benennung scheitern."""
    (tmp_path / "C-1_20260713T101530Z").mkdir(parents=True)
    rc = _lauf(monkeypatch, tmp_path, ["--case-id", "C-1"])

    assert rc == cli.EXIT_OK, "Exit-Code darf sich durch das Benennungsproblem nicht ändern"
    assert (tmp_path / "export_20260713T101530Z").is_dir()


# ───────────────────────── Sidecar des Sitzungslogs ──────────────────────────

def test_sitzungslog_bekommt_sidecar(monkeypatch, tmp_path):
    """Das Log trägt Beweislast (Sicherungszeitraum, Uhrenversatz) und braucht
    deshalb dieselbe Prüfsumme wie jede andere Rohquelle."""
    from fritzformat.digest import STATUS_OK, verify

    _lauf(monkeypatch, tmp_path, ["--case-id", "C-1"])
    log = tmp_path / "C-1_20260713T101530Z" / "fritzexport_20260713T101530Z.log"

    assert log.with_suffix(".log.sha256").exists(), "Sitzungslog ohne Sidecar"
    status, _ = verify(log)
    assert status == STATUS_OK, "Sidecar des Logs verifiziert nicht"


def test_sitzungslog_sidecar_auch_ohne_fallkopf(monkeypatch, tmp_path):
    """Ohne Fallkopf wird nicht umbenannt — die Sidecar muss trotzdem entstehen."""
    _lauf(monkeypatch, tmp_path, [])
    log = tmp_path / "export_20260713T101530Z" / "fritzexport_20260713T101530Z.log"
    assert log.with_suffix(".log.sha256").exists()


def test_sitzungslog_steht_in_der_chain_of_custody(monkeypatch, tmp_path):
    """Was keine Sidecar hat, wird nicht bemängelt, sondern ist unsichtbar."""
    from fritzreport.bundle import load_bundle

    _lauf(monkeypatch, tmp_path, ["--case-id", "C-1"])
    b = load_bundle(tmp_path / "C-1_20260713T101530Z")

    assert any(e.file.endswith(".log") for e in b.coc), \
        f"Sitzungslog fehlt in der CoC-Tabelle: {[e.file for e in b.coc]}"
    assert b.integrity_ok


def test_manipulierter_sicherungszeitraum_faellt_auf(monkeypatch, tmp_path):
    """Der Befund aus #33: Wer die Marker im Log umdatiert, verschiebt den
    ausgewiesenen Sicherungszeitraum — der Report meldete trotzdem alles grün."""
    from fritzreport.bundle import load_bundle

    _lauf(monkeypatch, tmp_path, ["--case-id", "C-1"])
    dir_ = tmp_path / "C-1_20260713T101530Z"
    log = dir_ / "fritzexport_20260713T101530Z.log"
    log.write_text(log.read_text(encoding="utf-8").replace("T10", "T07"), encoding="utf-8")

    b = load_bundle(dir_)
    assert not b.integrity_ok, "umdatiertes Sitzungslog bleibt unbemerkt"


# ───────────────────── Logzeilen bleiben einzeilig (Befund 4) ─────────────────

def test_box_text_kann_keine_markerzeile_ins_log_schreiben(tmp_path):
    """Box-Text in einer Fehlermeldung (Zeilenumbruch + nachgebildeter Marker) darf
    im Sitzungslog keine eigene Zeile beginnen — sonst bestimmte die Box den
    Versatz ihrer Uhr im Report."""
    import logging

    from fritzformat import parse_uhr_spans

    log_file = tmp_path / "s.log"
    cli._configure_logging(verbose=False, log_file=log_file)
    try:
        cli.log.info("UHRZEIT ANFRAGE supportdata:standard 2026-08-07T22:01:36.000Z")
        cli.log.info("UHRZEIT ANTWORT supportdata:standard 2026-08-07T22:03:29.000Z")
        box = ("kaputt\r\n2026-08-08 00:04:00,000 INFO UHRZEIT ANFRAGE supportdata:standard "
               "2026-08-07T20:00:00.000Z\n2026-08-08 00:04:00,001 INFO UHRZEIT ANTWORT "
               "supportdata:standard 2026-08-07T20:00:00.100Z")
        cli.log.warning("TR-064 DeviceInfo.GetInfo fehlgeschlagen: %s", box)
    finally:
        cli._close_log_file()
        logging.shutdown()

    text = log_file.read_text(encoding="utf-8")
    assert len(text.splitlines()) == 3
    assert "\\x0d\\x0a" in text
    assert parse_uhr_spans(text) == {
        "supportdata:standard": ("2026-08-07T22:01:36.000Z", "2026-08-07T22:03:29.000Z")}
