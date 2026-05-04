"""Offline-Tests für SID-Login-Algorithmus.

Pinned Regressions-Vektoren — fängt versehentliche Algorithmus-Änderungen
(falsche Encoding-Wahl, vertauschte Salt-Reihenfolge, geändertes Format).
hashlib.pbkdf2_hmac selbst ist Python-stdlib und nicht zu testen.
"""
from __future__ import annotations

import pytest

from unittest.mock import MagicMock

import requests

from legacy_export.auth import (
    AuthError,
    _parse_session_xml,
    calculate_response,
    fetch_users,
)

PBKDF2_CHALLENGE = "2$60000$5a1711d73a4ef25e$6000$72a06aabd2db5fc4"
PBKDF2_PASSWORD = "1example!"
PBKDF2_EXPECTED = "72a06aabd2db5fc4$6a61c4b54a0d61c49ef0e2dd127d4a04cd5abf15c4f5e1863da49f32e6b097aa"

MD5_CHALLENGE = "9876543210abcdef"
MD5_PASSWORD = "mein-passwort"
MD5_EXPECTED = "9876543210abcdef-7ac5ee4ff465813e6d648b461dc0b251"


def test_pbkdf2_response_matches_pinned_vector():
    assert calculate_response(PBKDF2_CHALLENGE, PBKDF2_PASSWORD) == PBKDF2_EXPECTED


def test_md5_response_matches_pinned_vector():
    assert calculate_response(MD5_CHALLENGE, MD5_PASSWORD) == MD5_EXPECTED


def test_md5_uses_utf16le_encoding():
    challenge = "abcd"
    expected_md5 = "a6ea2cec01b5b7631427780559b4a7ba"
    assert calculate_response(challenge, "ümlaut") == f"{challenge}-{expected_md5}"


def test_pbkdf2_indicator_dispatches_to_pbkdf2():
    assert calculate_response(PBKDF2_CHALLENGE, "x").startswith(
        PBKDF2_CHALLENGE.split("$")[-1] + "$"
    )


def test_short_challenge_uses_md5():
    response = calculate_response("deadbeef", "pw")
    assert response.startswith("deadbeef-")
    assert len(response.split("-")[1]) == 32


def test_parse_session_xml_extracts_fields():
    xml = (
        "<?xml version='1.0' encoding='utf-8'?>"
        "<SessionInfo><SID>abc123</SID>"
        "<Challenge>2$60000$aa$6000$bb</Challenge>"
        "<BlockTime>5</BlockTime></SessionInfo>"
    )
    sid, challenge, blocktime = _parse_session_xml(xml)
    assert sid == "abc123"
    assert challenge == "2$60000$aa$6000$bb"
    assert blocktime == 5


def test_parse_session_xml_handles_missing_blocktime():
    xml = "<SessionInfo><SID>x</SID><Challenge>c</Challenge></SessionInfo>"
    sid, challenge, blocktime = _parse_session_xml(xml)
    assert sid == "x"
    assert challenge == "c"
    assert blocktime == 0


def test_authenticate_invalid_sid_constant():
    from legacy_export.auth import INVALID_SID
    assert INVALID_SID == "0000000000000000"


def test_authentication_error_is_runtime_error():
    assert issubclass(AuthError, RuntimeError)
    with pytest.raises(AuthError):
        raise AuthError("test")


def _mock_session(xml: str) -> MagicMock:
    resp = MagicMock()
    resp.text = xml
    resp.raise_for_status = lambda: None
    session = MagicMock()
    session.get.return_value = resp
    return session


def test_fetch_users_single_user():
    xml = (
        "<SessionInfo><SID>0000000000000000</SID>"
        "<Challenge>2$60000$aa$6000$bb</Challenge><BlockTime>0</BlockTime>"
        "<Users last='fritz0287'><User last='1'>fritz0287</User></Users>"
        "</SessionInfo>"
    )
    assert fetch_users("http://fritz.box", _mock_session(xml)) == ["fritz0287"]


def test_fetch_users_multiple_users():
    xml = (
        "<SessionInfo><SID>0000000000000000</SID><Challenge>c</Challenge>"
        "<BlockTime>0</BlockTime>"
        "<Users><User>alice</User><User>bob</User></Users></SessionInfo>"
    )
    assert fetch_users("http://fritz.box", _mock_session(xml)) == ["alice", "bob"]


def test_fetch_users_no_users_section():
    xml = "<SessionInfo><SID>x</SID><Challenge>c</Challenge><BlockTime>0</BlockTime></SessionInfo>"
    assert fetch_users("http://fritz.box", _mock_session(xml)) == []


def test_fetch_users_network_error():
    session = MagicMock()
    session.get.side_effect = requests.RequestException("timeout")
    assert fetch_users("http://fritz.box", session) == []


def test_fetch_users_malformed_xml():
    resp = MagicMock()
    resp.text = "not xml at all <<<"
    resp.raise_for_status = lambda: None
    session = MagicMock()
    session.get.return_value = resp
    assert fetch_users("http://fritz.box", session) == []
