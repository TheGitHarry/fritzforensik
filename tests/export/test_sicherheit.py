"""Regressionstests zum Sicherheitsaudit (Befunde 1–3).

1. Anmeldung an ein Gerät, das sich als Box ausgibt: kein MD5-Downgrade, TLS auf
   einen Fingerabdruck festgelegt statt still abgeschaltet.
2. TR-064 nicht im Klartext: Umstellung auf den TLS-Port der Box, sonst gesperrt.
3. Pfade aus Box-Antworten dürfen die Anfrage nicht auf einen fremden Host lenken.
"""
from __future__ import annotations

import http.server
import shutil
import ssl
import subprocess
import threading
from unittest.mock import MagicMock

import pytest
import requests

from fritzexport import auth
from fritzexport.auth import AuthError
from fritzexport.client import (
    FritzClient,
    Tr064Disabled,
    UnsafeBoxPath,
    check_box_path,
    make_session,
    normalize_fingerprint,
)
from fritzexport.extractors import tam


# ───────────────────────── Befund 1: MD5-Downgrade ───────────────────────────

def _login_session(challenge: str) -> MagicMock:
    resp = MagicMock()
    resp.text = (f"<SessionInfo><SID>0000000000000000</SID>"
                 f"<Challenge>{challenge}</Challenge><BlockTime>0</BlockTime></SessionInfo>")
    resp.raise_for_status = lambda: None
    session = MagicMock()
    session.get.return_value = resp
    return session


def test_md5_challenge_wird_ohne_erlaubnis_nicht_beantwortet():
    """Die Challenge bestimmt die Gegenstelle. Ohne ``2$`` gäbe es sonst
    ``md5(challenge-passwort)`` — offline in Minuten zu raten."""
    session = _login_session("deadbeef")
    with pytest.raises(AuthError, match="MD5"):
        auth.login("https://box", "admin", "geheim", session)
    session.post.assert_not_called()


def test_md5_mit_ausdruecklicher_erlaubnis():
    session = _login_session("deadbeef")
    ok = MagicMock()
    ok.text = "<SessionInfo><SID>0123456789abcdef</SID></SessionInfo>"
    ok.raise_for_status = lambda: None
    session.post.return_value = ok
    assert auth.login("https://box", "admin", "geheim", session, allow_md5=True).sid \
        == "0123456789abcdef"


@pytest.mark.parametrize("challenge", [
    "2$1$$1$aa",                                      # der Umweg um die MD5-Sperre
    "2$999$5a1711d73a4ef25e$6000$72a06aabd2db5fc4",   # zu wenige Iterationen (statisch)
    "2$60000$5a1711d73a4ef25e$999$72a06aabd2db5fc4",  # zu wenige Iterationen (dynamisch)
    "2$60000$5a1711d73a4e$6000$72a06aabd2db5fc4",     # Salt zu kurz
    "2$60000$5a1711d73a4ef25e$6000$",                 # Salt leer
])
def test_schwache_pbkdf2_challenge_wird_nicht_beantwortet(challenge):
    """Ein nachgebildetes Gerät darf die MD5-Sperre nicht mit ``2$`` und einer
    Iteration umgehen — die Antwort wäre offline so billig zu raten wie MD5.
    Auch ``--allow-md5`` gibt das nicht frei: Es erlaubt alte Firmware, keine
    Challenge, die keine Box stellt."""
    session = _login_session(challenge)
    with pytest.raises(AuthError, match="zu schwaches PBKDF2"):
        auth.login("https://box", "admin", "geheim", session, allow_md5=True)
    session.post.assert_not_called()


# ─────────────────────── Befund 1: TLS-Fingerabdruck ─────────────────────────

def test_fingerabdruck_normalisierung():
    assert normalize_fingerprint(":".join(["AB"] * 32)) == "ab" * 32
    with pytest.raises(ValueError):
        normalize_fingerprint("abcd")


@pytest.fixture
def tls_server(tmp_path):
    """HTTPS-Server mit frisch erzeugtem selbstsigniertem Zertifikat."""
    if not shutil.which("openssl"):
        pytest.skip("openssl nicht verfügbar")
    cert, key = tmp_path / "c.pem", tmp_path / "k.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                    "-keyout", str(key), "-out", str(cert), "-days", "1",
                    "-subj", "/CN=fritz.box"], check=True, capture_output=True)

    class _H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), _H)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    pem = cert.read_text()
    import hashlib
    fp = hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()
    yield f"https://127.0.0.1:{srv.server_port}", fp
    srv.shutdown()


def test_festgelegter_fingerabdruck_verbindet(tls_server):
    url, fp = tls_server
    assert make_session(tls_fingerprint=fp).get(url, timeout=5).text == "ok"


def test_fremder_fingerabdruck_wird_abgewiesen(tls_server):
    url, _ = tls_server
    with pytest.raises(requests.exceptions.SSLError):
        make_session(tls_fingerprint="00" * 32).get(url, timeout=5)


def test_ohne_fingerabdruck_wird_geprueft(tls_server):
    url, _ = tls_server
    with pytest.raises(requests.exceptions.SSLError):
        make_session().get(url, timeout=5)


def test_cli_fingerabdruck_gegen_echten_server(tls_server):
    from fritzexport import cli
    url, fp = tls_server
    assert cli._server_fingerprint(url) == fp


# ─────────────────────── Befund 2: TR-064 nicht im Klartext ─────────────────

_SECURITY_PORT_OK = (
    '<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
    '<s:Body><u:GetSecurityPortResponse xmlns:u="urn:dslforum-org:service:DeviceInfo:1">'
    '<NewSecurityPort>49443</NewSecurityPort></u:GetSecurityPortResponse></s:Body></s:Envelope>'
)


def _client(post_resp=None, post_exc=None) -> FritzClient:
    session = MagicMock()
    if post_exc:
        session.post.side_effect = post_exc
    else:
        session.post.return_value = post_resp
    return FritzClient(base_url="https://192.168.2.1", sid="0" * 16, session=session,
                       username="admin", password="geheim")


def test_tr064_wechselt_auf_tls_port():
    resp = MagicMock(status_code=200, text=_SECURITY_PORT_OK)
    c = _client(resp)
    c.secure_tr064()
    assert c.tr064_url("/upnp/control/x") == "https://192.168.2.1:49443/upnp/control/x"
    # Die Port-Abfrage läuft ohne Digest: Auf 401 hin ginge sonst die
    # Digest-Antwort im Klartext hinaus.
    assert "auth" not in c.session.post.call_args.kwargs


def test_tr064_ohne_tls_port_gesperrt():
    c = _client(post_exc=requests.ConnectionError("zu"))
    c.secure_tr064()
    with pytest.raises(Tr064Disabled):
        c.tr064_url("/tr64desc.xml")
    assert c.tr064_available() is False
    assert c.tr064_services() == []


def test_tr064_klartext_nur_ausdruecklich():
    c = _client(post_exc=requests.ConnectionError("zu"))
    c.secure_tr064(allow_plain=True)
    assert c.tr064_url("/x") == "http://192.168.2.1:49000/x"


def test_tr064_call_bei_sperre_ist_tr064disabled():
    """Die Extractoren fallen auf Tr064Disabled bereits auf Web-UI-Pfade zurück."""
    c = _client(post_exc=requests.ConnectionError("zu"))
    c.secure_tr064()
    with pytest.raises(Tr064Disabled):
        c.tr064_call("urn:x", "/upnp/control/x", "GetInfo")


# ─────────────────────── Befund 3: Pfade aus Box-Antworten ──────────────────

@pytest.mark.parametrize("pfad", [
    "@evil.example/download.lua",
    "/download.lua@evil",
    "//evil.example/x",
    "http://evil.example/x",
    "download.lua",
    "/a\\b",
    "/a\nb",
    "",
])
def test_unsichere_box_pfade(pfad):
    with pytest.raises(UnsafeBoxPath):
        check_box_path(pfad)


@pytest.mark.parametrize("pfad", [
    "/download.lua?path=/data/tam/rec/rec.0.001",
    "/meshlist.lua?sid=abc&hkid=x@y",   # @ in der Query ändert den Host nicht
    "/devicehostlist.lua",
])
def test_sichere_box_pfade(pfad):
    assert check_box_path(pfad) == pfad


def test_webui_get_lehnt_fremden_host_ab():
    c = _client()
    with pytest.raises(UnsafeBoxPath):
        c.get("@evil.example/download.lua")
    c.session.get.assert_not_called()


def test_tam_liste_geht_an_die_eigene_box():
    """``NewURL`` ist Fremdeingabe — übernommen werden nur Pfad und Query."""
    c = MagicMock()
    c.tr064_call.side_effect = [
        {"NewName": "AB", "NewEnable": "1"},
        {"NewURL": "http://evil.example:80/tamcalllist.lua?sid=abc&tamindex=0"},
        Tr064Disabled("ende"),
    ]
    c.tr064_url.side_effect = lambda p: f"https://192.168.2.1:49443{p}"
    c.session.get.return_value = MagicMock(text="<Root/>")
    try:
        tam._try_tr064(c, MagicMock())
    except Tr064Disabled:
        pass
    url = c.session.get.call_args_list[0].args[0]
    assert url == "https://192.168.2.1:49443/tamcalllist.lua?sid=abc&tamindex=0"


def test_weiterleitung_auf_fremden_host_wird_verweigert():
    s = make_session()
    resp = requests.Response()
    resp.status_code = 302
    resp.url = "https://192.168.2.1/x"
    resp.headers["location"] = "https://evil.example/y"
    with pytest.raises(requests.exceptions.InvalidURL):
        s.get_redirect_target(resp)

    resp.headers["location"] = "/y"
    assert s.get_redirect_target(resp) == "/y"
