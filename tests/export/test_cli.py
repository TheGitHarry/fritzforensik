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
