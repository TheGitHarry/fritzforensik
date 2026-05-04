"""SID-Login gegen die FRITZ!Box Web-UI (AVM Technical Note: Session ID).

PBKDF2-Challenge-Response für moderne Firmware (FRITZ!OS 7.24+),
MD5-Fallback für ältere Stände.
"""
from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import requests

LOGIN_PATH = "/login_sid.lua?version=2"
LOGIN_POST_PATH = "/login_sid.lua"
INVALID_SID = "0000000000000000"
PBKDF2_INDICATOR = "2$"


class AuthError(RuntimeError):
    """Anmeldung fehlgeschlagen (falsches Passwort, Box gesperrt, …)."""


@dataclass
class LoginResult:
    sid: str
    blocktime: int


def _pbkdf2_response(challenge: str, password: str) -> str:
    _, iter1, salt1, iter2, salt2 = challenge.split("$")
    static_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt1), int(iter1)
    )
    dynamic_hash = hashlib.pbkdf2_hmac(
        "sha256", static_hash, bytes.fromhex(salt2), int(iter2)
    )
    return f"{salt2}${dynamic_hash.hex()}"


def _md5_response(challenge: str, password: str) -> str:
    digest = hashlib.md5(
        f"{challenge}-{password}".encode("utf-16-le")
    ).hexdigest()
    return f"{challenge}-{digest}"


def calculate_response(challenge: str, password: str) -> str:
    """Wählt PBKDF2 oder MD5 anhand des Challenge-Formats."""
    if challenge.startswith(PBKDF2_INDICATOR):
        return _pbkdf2_response(challenge, password)
    return _md5_response(challenge, password)


def _parse_session_xml(xml_text: str) -> tuple[str, str, int]:
    root = ET.fromstring(xml_text)
    sid = (root.findtext("SID") or "").strip()
    challenge = (root.findtext("Challenge") or "").strip()
    blocktime_text = (root.findtext("BlockTime") or "0").strip()
    try:
        blocktime = int(blocktime_text)
    except ValueError:
        blocktime = 0
    return sid, challenge, blocktime


def login(
    base_url: str, username: str, password: str, session: requests.Session
) -> LoginResult:
    """Führt das vollständige SID-Login durch.

    `base_url` z.B. 'http://fritz.box' (ohne Trailing-Slash).
    """
    challenge_resp = session.get(base_url + LOGIN_PATH, timeout=10)
    challenge_resp.raise_for_status()
    _, challenge, blocktime = _parse_session_xml(challenge_resp.text)
    if not challenge:
        raise AuthError("Keine Challenge von der Box erhalten")
    if blocktime > 0:
        raise AuthError(
            f"Box ist gesperrt (BlockTime={blocktime}s) — "
            "vorherige Login-Versuche zu schnell oder mit falschem Passwort"
        )

    response_value = calculate_response(challenge, password)
    login_resp = session.post(
        base_url + LOGIN_POST_PATH,
        data={"username": username, "response": response_value},
        timeout=10,
    )
    login_resp.raise_for_status()
    sid, _, blocktime = _parse_session_xml(login_resp.text)
    if not sid or sid == INVALID_SID:
        raise AuthError(
            f"Login abgelehnt — falscher Benutzer oder Passwort "
            f"(BlockTime={blocktime}s)"
        )
    return LoginResult(sid=sid, blocktime=blocktime)


def fetch_users(base_url: str, session: requests.Session) -> list[str]:
    """Gibt die Benutzerliste aus login_sid.lua zurück.

    Leere Liste bei Netzwerkfehler, Parse-Fehler oder fehlender Users-Sektion
    (ältere Firmware ohne Users-Element).
    """
    try:
        resp = session.get(base_url + LOGIN_PATH, timeout=10)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
    except (requests.RequestException, ET.ParseError):
        return []
    users_node = root.find("Users")
    if users_node is None:
        return []
    return [
        u.text.strip()
        for u in users_node.findall("User")
        if u.text and u.text.strip()
    ]


def logout(base_url: str, sid: str, session: requests.Session) -> None:
    """Höflich abmelden — Box gibt Session-Slot zurück."""
    try:
        session.get(
            base_url + LOGIN_POST_PATH,
            params={"logout": "1", "sid": sid},
            timeout=5,
        )
    except requests.RequestException:
        pass
