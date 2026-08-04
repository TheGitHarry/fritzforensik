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
    assert cli._normalize_host(raw) == expected


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
    cli._probe_tls(cli._normalize_host("192.168.2.1"), args)
    assert seen == ["https://192.168.2.1/login_sid.lua?version=2"]
    assert args.insecure is True


def test_autodetect_user_bei_genau_einem_benutzer(monkeypatch):
    monkeypatch.setattr(cli, "fetch_users", lambda base_url, session: ["export"])
    assert cli._autodetect_user("https://192.168.2.1", verify_tls=False) == "export"


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
    monkeypatch.setattr(cli, "_list_users", lambda b, verify_tls: ["export"])
    args = argparse.Namespace(user=None, insecure=False)
    assert cli._resolve_user("https://192.168.2.1", args) == "export"


def test_resolve_user_prompt_bei_mehreren(monkeypatch):
    """Regression: mit --host und mehreren Benutzern muss nachgefragt werden,
    statt hart mit '--user ist erforderlich' abzubrechen."""
    monkeypatch.setattr(cli, "_list_users", lambda b, verify_tls: ["fritz1310", "export"])
    seen = {}

    def fake_select(users):
        seen["users"] = users
        return "export"

    monkeypatch.setattr(cli, "_select_user", fake_select)
    args = argparse.Namespace(user=None, insecure=False)
    assert cli._resolve_user("https://192.168.2.1", args) == "export"
    assert seen["users"] == ["fritz1310", "export"]


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
        return ["export"]

    monkeypatch.setattr(cli, "_list_users", fake_list_users)
    args = argparse.Namespace(user=None, insecure=False)
    assert cli._resolve_user("https://192.168.2.1", args) == "export"
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


# ───────────────────────── Mehrfachfund-Schleife (#1) ────────────────────────

def _box(ip, name):
    from fritzexport import discover
    return discover.DiscoveredBox(ip=ip, friendly_name=name, model_name=name,
                                  location=f"https://{ip}:49443/desc.xml")


def _lauf_mehrere(monkeypatch, tmp_path, antworten, stamps=None):
    """main() mit zwei gefundenen Boxen; `antworten` steuert die Auswahl."""
    import logging

    from fritzexport.extractors import EXTRACTORS

    stamps = iter(stamps or ["20260713T101530Z", "20260713T102000Z"])
    monkeypatch.setattr(cli.output, "_utc_now_compact", lambda: next(stamps))
    monkeypatch.setattr(cli.discover, "discover",
                        lambda iface=None: [_box("192.168.2.1", "box-a"),
                                            _box("192.168.2.2", "box-b")])
    monkeypatch.setattr(cli, "_probe_tls", lambda url, args: None)
    monkeypatch.setattr(cli, "_resolve_user", lambda url, args: "admin")
    monkeypatch.setattr(cli, "_resolve_password", lambda env: "geheim")
    monkeypatch.setattr(cli, "_resolve_target",
                        lambda args: (args.host, None, cli.EXIT_OK))

    class _Client:
        def tr064_available(self): return True
        def close(self): pass

    monkeypatch.setattr(cli.FritzClient, "login",
                        classmethod(lambda cls, *a, **kw: _Client()))
    # nur ein Extractor, damit der Lauf kurz bleibt; ohne Extractor-Flag,
    # weil --hosts die Auto-Discovery abschalten würde (_is_implicit_discover)
    monkeypatch.setattr(cli, "_selected_extractors", lambda args: ["hosts"])
    monkeypatch.setitem(EXTRACTORS, "hosts", lambda c: [{"mac": "aa:bb"}])

    it = iter(antworten)
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(it, ""))

    rc = cli.main(["--no-prompt", "--output", str(tmp_path / "export")])
    logging.shutdown()
    return rc


def test_zweite_box_wird_angeboten(monkeypatch, tmp_path):
    """Nach der ersten Box wird die zweite angeboten — kein Neustart je Objekt."""
    rc = _lauf_mehrere(monkeypatch, tmp_path, antworten=["1", "1"])
    assert rc == cli.EXIT_OK
    dirs = sorted(p.name for p in tmp_path.iterdir() if p.is_dir())
    assert len(dirs) == 2, f"zweite Box wurde nicht abgezogen: {dirs}"


def test_jede_box_bekommt_eigenes_verzeichnis(monkeypatch, tmp_path):
    """Eigener Zeitstempel je Box — sonst überschriebe die zweite die erste."""
    _lauf_mehrere(monkeypatch, tmp_path, antworten=["1", "1"])
    dirs = sorted(p.name for p in tmp_path.iterdir() if p.is_dir())
    assert dirs == ["export_20260713T101530Z", "export_20260713T102000Z"]
    for d in dirs:
        assert list((tmp_path / d).glob("*_hosts.json")), f"{d} ohne Abzug"
        assert list((tmp_path / d).glob("fritzexport_*.log")), f"{d} ohne Logdatei"


def test_abbruch_nach_erster_box(monkeypatch, tmp_path):
    """'fertig' beendet die Schleife; die erste Box bleibt abgezogen."""
    rc = _lauf_mehrere(monkeypatch, tmp_path, antworten=["1", "2"])
    assert rc == cli.EXIT_OK
    dirs = [p.name for p in tmp_path.iterdir() if p.is_dir()]
    assert len(dirs) == 1, f"Abbruch hat nicht gegriffen: {dirs}"


def test_keine_box_gewaehlt_bleibt_abbruch(monkeypatch, tmp_path):
    """Wer gleich zu Beginn abbricht, bekommt weiterhin EXIT_AMBIGUOUS."""
    rc = _lauf_mehrere(monkeypatch, tmp_path, antworten=["3"])
    assert rc == cli.EXIT_AMBIGUOUS
