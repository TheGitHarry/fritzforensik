"""HTTP-Session-Wrapper mit SID-Verwaltung und optionalem TR-064-Aufruf."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import requests
from requests.auth import HTTPDigestAuth

from . import auth


class Tr064Error(RuntimeError):
    """Fehlschlag eines TR-064-SOAP-Aufrufs (Auth, Action-Fehler etc.)."""

    def __init__(self, message: str, error_code: int | None = None):
        super().__init__(message)
        self.error_code = error_code


class Tr064Disabled(Tr064Error):
    """TR-064 ist auf der Box nicht zugänglich (Stack aus oder User-Permission fehlt).

    Gibt der Aufrufer das Signal, auf einen Web-UI-Fallback umzuschwenken
    (für Forensik-Nutzungen, wo TR-064 manchmal nicht aktiv sein kann).
    """


@dataclass
class FritzClient:
    base_url: str
    sid: str
    session: requests.Session
    username: str = ""
    password: str = field(default="", repr=False)
    tr064_port: int = 49000

    @classmethod
    def login(
        cls,
        host: str,
        username: str,
        password: str,
        verify_tls: bool = True,
    ) -> "FritzClient":
        base_url = host if host.startswith(("http://", "https://")) else f"http://{host}"
        base_url = base_url.rstrip("/")
        session = requests.Session()
        session.verify = verify_tls
        if not verify_tls:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        result = auth.login(base_url, username, password, session)
        return cls(
            base_url=base_url,
            sid=result.sid,
            session=session,
            username=username,
            password=password,
        )

    def get(self, path: str, **kwargs) -> requests.Response:
        params = dict(kwargs.pop("params", {}) or {})
        params["sid"] = self.sid
        return self.session.get(self.base_url + path, params=params, timeout=30, **kwargs)

    def post(self, path: str, data: dict | None = None, **kwargs) -> requests.Response:
        payload = dict(data or {})
        payload["sid"] = self.sid
        return self.session.post(self.base_url + path, data=payload, timeout=30, **kwargs)

    def tr064_url(self, path: str) -> str:
        """TR-064 läuft auf eigenem Port (49000 HTTP), bauen wir aus base_url-Host."""
        host = urlsplit(self.base_url).hostname or self.base_url
        return f"http://{host}:{self.tr064_port}{path}"

    def tr064_call(
        self,
        service_type: str,
        control_url: str,
        action: str,
        args: dict[str, str] | None = None,
        timeout: float = 10.0,
    ) -> dict[str, str]:
        """Sendet einen TR-064-SOAP-Aufruf und gibt Response-Args als Dict zurück.

        Wirft `Tr064Disabled` bei UPnPError 401 (Stack aus oder Auth abgelehnt
        ohne Challenge) und 606 (User hat keine TR-064-Permission). Wirft
        `Tr064Error` bei allen anderen UPnPError-Codes oder Transport-Fehlern.
        """
        args = args or {}
        body_args = "".join(f"<{k}>{v}</{k}>" for k, v in args.items())
        body = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"'
            ' s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
            f'<s:Body><u:{action} xmlns:u="{service_type}">{body_args}'
            f'</u:{action}></s:Body></s:Envelope>'
        )
        try:
            resp = self.session.post(
                self.tr064_url(control_url),
                data=body,
                headers={
                    "Content-Type": 'text/xml; charset="utf-8"',
                    "SOAPAction": f'"{service_type}#{action}"',
                },
                auth=HTTPDigestAuth(self.username, self.password),
                timeout=timeout,
            )
        except requests.RequestException as e:
            raise Tr064Error(f"TR-064 transport error: {e}") from e

        if resp.status_code == 200:
            return _parse_soap_response(resp.text, action)

        # SOAP-Fault parsen
        if resp.status_code == 500:
            err_code, err_desc = _parse_soap_fault(resp.text)
            if err_code in (401, 606):
                raise Tr064Disabled(
                    f"TR-064 nicht zugänglich: UPnPError {err_code} ({err_desc}). "
                    "Stack auf der Box deaktiviert oder User hat keine TR-064-Berechtigung.",
                    error_code=err_code,
                )
            raise Tr064Error(
                f"TR-064 UPnPError {err_code}: {err_desc}", error_code=err_code
            )
        # HTTP 401 mit echter Auth-Challenge wäre möglich, aber requests handled das
        # via HTTPDigestAuth automatisch — wir landen hier nur bei wirklich gescheiterter Auth.
        raise Tr064Error(f"TR-064 unexpected HTTP {resp.status_code}: {resp.text[:200]}")

    def tr064_available(self) -> bool:
        """Prüft ob Port 49000 erreichbar ist (beliebige HTTP-Antwort genügt).

        Verschiedene Box-Modelle nutzen unterschiedliche Descriptor-Pfade
        (/tr64desc.xml, /l2tpv3.xml, /fboxdesc.xml …). Jede HTTP-Antwort
        zeigt, dass der Port offen ist — ob der User TR-064-Berechtigung
        hat, klärt sich beim ersten SOAP-Aufruf.
        """
        try:
            self.session.get(self.tr064_url("/tr64desc.xml"), timeout=5)
            return True
        except requests.RequestException:
            return False

    def close(self) -> None:
        auth.logout(self.base_url, self.sid, self.session)
        self.session.close()

    def __enter__(self) -> "FritzClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


_SOAP_NS = "{http://schemas.xmlsoap.org/soap/envelope/}"


def _parse_soap_response(xml_text: str, action: str) -> dict[str, str]:
    """Pflückt alle Elemente des `<u:ActionResponse>`-Bodys als flaches Dict."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise Tr064Error(f"Konnte SOAP-Antwort nicht parsen: {e}") from e
    body = root.find(f"{_SOAP_NS}Body")
    if body is None or len(body) == 0:
        raise Tr064Error("SOAP-Antwort ohne Body")
    response = list(body)[0]  # erstes Kind-Element ist <u:ActionResponse>
    return {child.tag.split("}", 1)[-1]: (child.text or "") for child in response}


_FAULT_CODE_RE = re.compile(r"<errorCode>(\d+)</errorCode>")
_FAULT_DESC_RE = re.compile(r"<errorDescription>([^<]+)</errorDescription>")


def _parse_soap_fault(xml_text: str) -> tuple[int, str]:
    """Extrahiert UPnPError-Code und -Description aus einem SOAP-Fault-Body."""
    code_match = _FAULT_CODE_RE.search(xml_text)
    desc_match = _FAULT_DESC_RE.search(xml_text)
    code = int(code_match.group(1)) if code_match else 0
    desc = desc_match.group(1).strip() if desc_match else ""
    return code, desc
