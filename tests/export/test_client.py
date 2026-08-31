"""FritzClient — Schema-Default beim Login (#39).

Welches Schema gilt, wenn der Host ohne eines angegeben wird, ist **eine** Frage.
Sie wurde an zwei Stellen verschieden beantwortet: ``cli._normalize_host`` ergänzte
``https://``, ``FritzClient.login`` ``http://``. Über die CLI gewann HTTPS, weil die
Normalisierung vorher läuft — wer den Client direkt benutzt, bekam still Klartext.
"""
from __future__ import annotations

import pytest

from fritzexport import client as client_mod
from fritzexport.client import FritzClient


@pytest.fixture
def gesehen(monkeypatch):
    """Fängt die base_url ab, mit der der Login tatsächlich losläuft."""
    gesehen: list[str] = []

    class _Result:
        sid = "0123456789abcdef"

    def _login(base_url, username, password, session):
        gesehen.append(base_url)
        return _Result()

    monkeypatch.setattr(client_mod.auth, "login", _login)
    return gesehen


@pytest.mark.parametrize("host,erwartet", [
    ("fritz.box", "https://fritz.box"),
    ("192.168.2.1", "https://192.168.2.1"),
    ("fritz.box/", "https://fritz.box"),
    ("https://fritz.box", "https://fritz.box"),
    # Ein ausdrückliches http:// bleibt stehen — der Aufrufer hat sich entschieden.
    ("http://fritz.box", "http://fritz.box"),
])
def test_schema_default_ist_https(gesehen, host, erwartet):
    c = FritzClient.login(host, "admin", "geheim", verify_tls=False)
    assert gesehen == [erwartet]
    assert c.base_url == erwartet


def test_client_und_cli_geben_dieselbe_antwort(gesehen):
    """Die eigentliche Zusage aus #39: beide Wege enden bei derselben base_url."""
    from fritzexport.cli import _normalize_host

    FritzClient.login("fritz.box", "admin", "geheim", verify_tls=False)
    assert gesehen[0] == _normalize_host("fritz.box")
