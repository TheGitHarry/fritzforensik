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


def test_probe_tls_schaltet_bei_selbstsigniertem_cert_auf_insecure(monkeypatch):
    def boom(url, timeout):
        raise requests.exceptions.SSLError("self-signed certificate")

    monkeypatch.setattr(cli.requests, "get", boom)
    args = argparse.Namespace(insecure=False)
    cli._probe_tls("https://192.168.2.1", args)
    assert args.insecure is True


def test_probe_tls_greift_auch_bei_host_ohne_schema(monkeypatch):
    """Regression: blanke IP wurde vom TLS-Probe übersprungen, dadurch blieb
    der Benutzer-Auto-Detect ohne Insecure-Umschaltung und lieferte nichts."""
    seen = []

    def boom(url, timeout):
        seen.append(url)
        raise requests.exceptions.SSLError("self-signed certificate")

    monkeypatch.setattr(cli.requests, "get", boom)
    args = argparse.Namespace(insecure=False)
    cli._probe_tls(cli.normalize_host("192.168.2.1"), args)
    assert seen == ["https://192.168.2.1/login_sid.lua?version=2"]
    assert args.insecure is True


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
    monkeypatch.setattr(cli, "_list_users", lambda b, verify_tls: ["boxuser"])
    args = argparse.Namespace(user=None, insecure=False)
    assert cli._resolve_user("https://192.168.2.1", args) == "boxuser"


def test_resolve_user_prompt_bei_mehreren(monkeypatch):
    """Regression: mit --host und mehreren Benutzern muss nachgefragt werden,
    statt hart mit '--user ist erforderlich' abzubrechen."""
    monkeypatch.setattr(cli, "_list_users", lambda b, verify_tls: ["fritz1310", "boxuser"])
    seen = {}

    def fake_select(users):
        seen["users"] = users
        return "boxuser"

    monkeypatch.setattr(cli, "_select_user", fake_select)
    args = argparse.Namespace(user=None, insecure=False)
    assert cli._resolve_user("https://192.168.2.1", args) == "boxuser"
    assert seen["users"] == ["fritz1310", "boxuser"]


def test_resolve_user_mehrere_ohne_tty_ergibt_none(monkeypatch):
    monkeypatch.setattr(cli, "_list_users", lambda b, verify_tls: ["a", "b"])
    monkeypatch.setattr(cli, "_select_user", lambda users: None)
    args = argparse.Namespace(user=None, insecure=False)
    assert cli._resolve_user("https://192.168.2.1", args) is None


def test_resolve_user_retry_insecure_bei_sslerror(monkeypatch):
    """Regression: bei einem Zertifikatsfehler beim Benutzer-Read wird auf
    insecure umgeschaltet und der Read wiederholt — statt den Anwender zu
    fragen. args.insecure muss danach True sein (gilt für den Login)."""
    calls = []

    def fake_list_users(base_url, verify_tls):
        calls.append(verify_tls)
        if verify_tls:
            raise requests.exceptions.SSLError("self-signed certificate")
        return ["boxuser"]

    monkeypatch.setattr(cli, "_list_users", fake_list_users)
    args = argparse.Namespace(user=None, insecure=False)
    assert cli._resolve_user("https://192.168.2.1", args) == "boxuser"
    assert args.insecure is True
    assert calls == [True, False]  # erst verify, dann insecure-Retry


def test_resolve_user_freitext_wenn_liste_leer(monkeypatch):
    monkeypatch.setattr(cli, "_list_users", lambda b, verify_tls: [])
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
    monkeypatch.setattr(cli, "_probe_tls", lambda url, args: None)
    monkeypatch.setattr(cli, "_resolve_user", lambda url, args: "admin")
    monkeypatch.setattr(cli, "_resolve_password", lambda env: "geheim")

    class _Client:
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
