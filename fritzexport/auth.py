"""SID-Login gegen die FRITZ!Box Web-UI (AVM Technical Note: Session ID).

PBKDF2-Challenge-Response für moderne Firmware (FRITZ!OS 7.24+),
MD5-Fallback für ältere Stände.
"""
from __future__ import annotations

import hashlib
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import requests

log = logging.getLogger("fritzexport")

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


#: Untergrenzen für die Parameter einer PBKDF2-Challenge. AVMs Technical Note nennt
#: 60000/6000 Iterationen und Salts von 8 Byte; die Grenzen liegen weit darunter und
#: treffen nur Challenges, die niemand außer einem nachgebildeten Gerät stellt.
PBKDF2_MIN_ITER = 1000
PBKDF2_MIN_SALT_BYTES = 8


def _check_pbkdf2_params(iter1: int, salt1: bytes, iter2: int, salt2: bytes) -> None:
    """AuthError, wenn die Challenge das Passwort billig zu raten machte.

    Iterationen und Salts wählt die Gegenstelle. Ein Gerät, das sich als Box ausgibt,
    könnte mit ``2$1$$1$aa`` die MD5-Sperre umgehen: Die Antwort wäre dann zweimal
    HMAC-SHA256 mit je einer Iteration — offline so schnell zu raten wie MD5.
    """
    if (min(iter1, iter2) < PBKDF2_MIN_ITER
            or min(len(salt1), len(salt2)) < PBKDF2_MIN_SALT_BYTES):
        raise AuthError(
            f"Gegenstelle verlangt ein zu schwaches PBKDF2 (Iterationen {iter1}/{iter2}, "
            f"Salt {len(salt1)}/{len(salt2)} Byte) — abgebrochen, das Passwort wurde "
            "nicht verwendet. Keine FRITZ!Box stellt eine solche Challenge."
        )


def _pbkdf2_response(challenge: str, password: str) -> str:
    try:
        _, iter1, salt1, iter2, salt2 = challenge.split("$")
        _check_pbkdf2_params(int(iter1), bytes.fromhex(salt1),
                             int(iter2), bytes.fromhex(salt2))
        static_hash = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt1), int(iter1)
        )
        dynamic_hash = hashlib.pbkdf2_hmac(
            "sha256", static_hash, bytes.fromhex(salt2), int(iter2)
        )
    except ValueError as e:
        raise AuthError(f"Unverständliche PBKDF2-Challenge der Box: {challenge!r} ({e})") from e
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
    base_url: str, username: str, password: str, session: requests.Session,
    allow_md5: bool = False,
) -> LoginResult:
    """Führt das vollständige SID-Login durch.

    `base_url` z.B. 'http://fritz.box' (ohne Trailing-Slash).

    Das MD5-Verfahren wird nur mit ``allow_md5`` bedient. Welches Verfahren gilt,
    bestimmt allein die Challenge — und die kommt von der Gegenstelle. Ein Gerät,
    das sich als Box ausgibt, bekäme sonst auf eine Challenge ohne ``2$`` hin
    ``md5(challenge-passwort)`` und könnte das Passwort offline in Minuten raten.
    Moderne Firmware (7.24+) antwortet auf ``version=2`` immer mit PBKDF2.

    Aus demselben Grund werden die Parameter einer PBKDF2-Challenge geprüft
    (:func:`_check_pbkdf2_params`) — sonst ließe sich die Sperre mit ``2$`` und einer
    Iteration umgehen.
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

    if not challenge.startswith(PBKDF2_INDICATOR) and not allow_md5:
        raise AuthError(
            "Gegenstelle bietet nur das schwache MD5-Anmeldeverfahren an — "
            "abgebrochen, das Passwort wurde nicht verwendet. Nur alte Firmware "
            "(vor FRITZ!OS 7.24) tut das; ist das Gerät sicher die Box, mit "
            "--allow-md5 erlauben."
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

    Ein TLS-Zertifikatsfehler (`SSLError`) wird *nicht* geschluckt, sondern
    weitergereicht: der Aufrufer kann dann auf --insecure umschalten und den
    Read wiederholen, statt fälschlich eine leere Liste zu sehen.
    """
    try:
        resp = session.get(base_url + LOGIN_PATH, timeout=10)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
    except requests.exceptions.SSLError:
        raise
    except (requests.RequestException, ET.ParseError) as e:
        log.warning("Benutzerliste nicht lesbar (%s): %s", type(e).__name__, e)
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
