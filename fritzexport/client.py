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

    #: Descriptor-Pfade, unter denen Boxen ihr TR-064-Dienstverzeichnis
    #: anbieten. Modellabhängig — deshalb der Reihe nach probieren.
    #:
    #: Bewusst NICHT enthalten sind ``/fboxdesc.xml`` und ``/igddesc.xml``.
    #: Beide antworten auf manchen Boxen mit HTTP 200, führen aber andere
    #: Protokolle: fboxdesc kennt genau einen Dienst
    #: (``urn:schemas-any-com:service:fritzbox:1``), igddesc listet UPnP-IGD
    #: (``urn:schemas-upnp-org:``) statt TR-064 (``urn:dslforum-org:``).
    #: Sie mitzunehmen ergäbe eine Liste, die aussieht wie ein Befund, aber
    #: keiner ist — beobachtet an zwei Boxen ohne aktiven TR-064-Stack.
    DESCRIPTOR_PATHS = ("/tr64desc.xml",)

    #: Nur diese URN-Familie ist TR-064. Alles andere gehört nicht in den
    #: Abgleich „welche Dienste holt ein Extractor ab".
    TR064_URN_PREFIX = "urn:dslforum-org:service:"

    def tr064_services(self) -> list[dict]:
        """Welche TR-064-Dienste bietet diese Box an?

        Liest das Dienstverzeichnis der Box (``/tr64desc.xml`` o. ä.) und gibt
        je Dienst ``service_type`` und ``control_url`` zurück. Anders als
        :meth:`tr064_available`, die nur den Port anpingt und die Antwort
        verwirft, wird der Inhalt hier ausgewertet.

        Ergebnis ist die einzige Quelle für die Frage, ob die Box Datenquellen
        anbietet, die kein Extractor abholt — sie ist **nur im Moment des
        Abzugs** erfassbar und steht in keinem Bundle-Bestandteil sonst.

        Wie ``tr064_available`` bewusst tolerant: Ist nichts erreichbar oder
        unparsbar, gibt es eben keine Liste. Kein Abbruch — die Abwesenheit
        des Verzeichnisses ist kein Forensikfehler.

        Eine **leere** Liste heißt nicht „Box bietet nichts an", sondern „kein
        TR-064-Verzeichnis erreichbar". Im Feld beobachtet an Boxen, auf denen
        *Zugriff für Anwendungen zulassen* deaktiviert ist: ``/tr64desc.xml``
        liefert dort 404 und ein SOAP-Aufruf HTTP 500, während Boxen mit
        aktivem Stack mit 401 antworten.
        """
        for pfad in self.DESCRIPTOR_PATHS:
            try:
                resp = self.session.get(self.tr064_url(pfad), timeout=10)
            except requests.RequestException:
                continue
            if resp.status_code != 200 or not resp.content:
                continue
            dienste = [d for d in _parse_service_list(resp.content)
                       if d["service_type"].startswith(self.TR064_URN_PREFIX)]
            if dienste:
                return dienste
        return []

    def close(self) -> None:
        auth.logout(self.base_url, self.sid, self.session)
        self.session.close()

    def __enter__(self) -> "FritzClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def _parse_service_list(xml_bytes: bytes) -> list[dict]:
    """Sammelt alle ``<service>``-Einträge einer Descriptor-XML.

    Rekursiv über ``<deviceList>``: Boxen schachteln Geräte (das
    InternetGatewayDevice enthält WANDevice, das wiederum
    WANConnectionDevice …). Nur die oberste Ebene zu lesen unterschlägt
    genau die Dienste, um die es hier geht.

    Namespace-Behandlung wie in ``discover.parse_device_xml`` — der
    Präfix steht am Wurzel-Tag.
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    ns = root.tag.split("}", 1)[0] + "}" if root.tag.startswith("{") else ""

    gefunden: list[dict] = []
    gesehen: set[str] = set()

    def sammle(knoten) -> None:
        for liste in knoten.findall(f"{ns}serviceList"):
            for dienst in liste.findall(f"{ns}service"):
                typ = (dienst.findtext(f"{ns}serviceType") or "").strip()
                if not typ or typ in gesehen:
                    continue
                gesehen.add(typ)
                gefunden.append({
                    "service_type": typ,
                    "control_url": (dienst.findtext(f"{ns}controlURL") or "").strip(),
                    "scpd_url": (dienst.findtext(f"{ns}SCPDURL") or "").strip(),
                })
        for liste in knoten.findall(f"{ns}deviceList"):
            for geraet in liste.findall(f"{ns}device"):
                sammle(geraet)

    for geraet in root.findall(f"{ns}device"):
        sammle(geraet)
    return sorted(gefunden, key=lambda d: d["service_type"])


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
