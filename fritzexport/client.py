"""HTTP-Session-Wrapper mit SID-Verwaltung und optionalem TR-064-Aufruf."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit
from xml.sax.saxutils import escape

import requests
from requests.adapters import HTTPAdapter
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


class UnsafeBoxPath(Tr064Error, ValueError):
    """Pfad aus einer Box-Antwort, der die Box verlassen würde.

    Pfade wie ``<Path>`` einer Sprachnachricht oder ``GetHostListPath`` sind
    Fremdeingabe des Asservats. Angehängt an die Basis-URL machte
    ``@andere.example/x`` aus ``https://<box>`` die URL
    ``https://<box>@andere.example/x`` — die Anfrage ginge samt SID an einen
    fremden Host.
    """


#: Zeichen, die in einem Box-Pfad (vor dem ``?``) nichts zu suchen haben: ``@`` und
#: ``\`` verschieben die Autorität der URL, Steuerzeichen brechen Header und Log.
_UNSICHERE_PFADZEICHEN = re.compile(r"[@\\\x00-\x20\x7f]")


def check_box_path(path: str) -> str:
    """``path`` unverändert zurückgeben, wenn er auf der Box bleibt; sonst UnsafeBoxPath.

    Zulässig ist nur ein absoluter Pfad (``/…``) ohne Autoritätsanteil. Geprüft wird
    der Teil vor dem ``?`` — die Query darf beliebige Werte tragen, sie kann den
    Host nicht mehr ändern.
    """
    kopf = path.split("?", 1)[0]
    if (not kopf.startswith("/") or kopf.startswith("//")
            or _UNSICHERE_PFADZEICHEN.search(kopf)):
        raise UnsafeBoxPath(f"Box lieferte einen Pfad, der die Box verlässt: {path!r}")
    return path


class _BoxSession(requests.Session):
    """Session, die Weiterleitungen nur auf denselben Host folgt.

    Was die Box antwortet, bestimmt das Asservat. Eine Weiterleitung auf einen
    anderen Host brächte die Abzugsmaschine dazu, beliebige Ziele anzusprechen.
    """

    def get_redirect_target(self, resp):
        ziel = super().get_redirect_target(resp)
        if ziel:
            neu = urlsplit(urljoin(resp.url, ziel))
            alt = urlsplit(resp.url)
            if (neu.hostname, neu.port) != (alt.hostname, alt.port) and not (
                    neu.hostname == alt.hostname and neu.scheme == "https"
                    and alt.scheme == "http"):
                raise requests.exceptions.InvalidURL(
                    f"Weiterleitung auf fremden Host verweigert: {ziel!r}")
        return ziel


class _PinnedAdapter(HTTPAdapter):
    """HTTPS nur gegen genau das Zertifikat mit diesem SHA256-Fingerabdruck.

    FRITZ!Boxen tragen ab Werk ein selbstsigniertes Zertifikat, das keine CA
    bestätigt. Der Fingerabdruck ersetzt diese Prüfung: Er wurde vom Anwender
    gegen die Box-Oberfläche abgeglichen (oder per ``--tls-fingerprint`` gesetzt).
    """

    def __init__(self, fingerprint: str):
        self._fingerprint = fingerprint
        super().__init__()

    def init_poolmanager(self, *args, **kwargs):
        kwargs["assert_fingerprint"] = self._fingerprint
        super().init_poolmanager(*args, **kwargs)


def normalize_fingerprint(fp: str) -> str:
    """``AB:CD …`` / ``abcd…`` → ``abcd…`` (64 Hex-Zeichen); ValueError sonst."""
    rein = re.sub(r"[\s:]", "", fp or "").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", rein):
        raise ValueError(f"Kein SHA256-Fingerabdruck: {fp!r}")
    return rein


def make_session(verify_tls: bool = True, tls_fingerprint: str | None = None) -> requests.Session:
    """Session für alle Anfragen an die Box.

    Mit Fingerabdruck wird jede HTTPS-Verbindung auf genau dieses Zertifikat
    festgelegt; ``verify_tls`` ist dann ohne Belang. Ohne Fingerabdruck und mit
    ``verify_tls=False`` findet **keine** Prüfung statt — das ist ausschließlich
    der ausdrückliche ``--insecure``-Fall.
    """
    session = _BoxSession()
    if tls_fingerprint:
        session.verify = False
        session.mount("https://", _PinnedAdapter(normalize_fingerprint(tls_fingerprint)))
    else:
        session.verify = verify_tls
        if not verify_tls:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    return session


def normalize_host(host: str) -> str:
    """Ergänzt fehlendes Schema (Default https) und entfernt Trailing-Slash.

    **Die** Antwort auf die Frage, welches Schema gilt, wenn der Host ohne eines
    angegeben wird — für die CLI wie für den direkten Gebrauch des Clients. Sie stand
    lange zweimal da, mit verschiedenen Defaults (#39) und danach immer noch mit
    verschiedener Erkennung (#43): Ohne Schema greift weder die TLS-Prüfung noch der
    Benutzer-Auto-Detect, weil requests mit MissingSchema abbricht.

    Ein ausdrücklich angegebenes Schema bleibt unangetastet, auch ein ungewöhnliches —
    wer ``http://`` schreibt, hat sich entschieden.
    """
    host = host.strip().rstrip("/")
    if "://" not in host:
        host = "https://" + host
    return host


@dataclass
class FritzClient:
    base_url: str
    sid: str
    session: requests.Session
    username: str = ""
    password: str = field(default="", repr=False)
    tr064_port: int = 49000
    #: ``http`` (Port 49000), ``https`` (Sicherheitsport der Box) oder ``""`` —
    #: TR-064 gesperrt, weil kein verschlüsselter Zugang bestand und Klartext nicht
    #: ausdrücklich erlaubt wurde. Siehe :meth:`secure_tr064`.
    tr064_scheme: str = "http"

    #: Klartext-Port und Dienst, über den die Box ihren TLS-Port für TR-064 nennt.
    TR064_PLAIN_PORT = 49000
    DEVICEINFO_SERVICE = "urn:dslforum-org:service:DeviceInfo:1"
    DEVICEINFO_CONTROL = "/upnp/control/deviceinfo"

    @classmethod
    def login(
        cls,
        host: str,
        username: str,
        password: str,
        verify_tls: bool = True,
        tls_fingerprint: str | None = None,
        allow_md5: bool = False,
        allow_plain_tr064: bool = False,
    ) -> "FritzClient":
        base_url = normalize_host(host)
        session = make_session(verify_tls, tls_fingerprint)
        result = auth.login(base_url, username, password, session, allow_md5=allow_md5)
        client = cls(
            base_url=base_url,
            sid=result.sid,
            session=session,
            username=username,
            password=password,
        )
        client.secure_tr064(allow_plain=allow_plain_tr064)
        return client

    def secure_tr064(self, allow_plain: bool = False) -> None:
        """TR-064 auf den TLS-Port der Box umstellen.

        Auf Port 49000 gingen Digest-Antwort (offline knackbar) und — in den
        Web-UI-Rückfällen von hosts/mesh — die Web-UI-SID im Klartext durchs LAN.
        Den TLS-Port nennt die Box über ``DeviceInfo:GetSecurityPort``; die Aktion
        ist ohne Anmeldung zugänglich und wird deshalb **ohne** Digest gerufen.

        Nennt die Box keinen Port, bleibt TR-064 gesperrt, es sei denn, Klartext
        wurde ausdrücklich erlaubt (``--tr064-http``).
        """
        port = self._query_security_port()
        if port:
            self.tr064_scheme, self.tr064_port = "https", port
        elif allow_plain:
            self.tr064_scheme, self.tr064_port = "http", self.TR064_PLAIN_PORT
        else:
            self.tr064_scheme = ""

    def _query_security_port(self) -> int | None:
        action = "GetSecurityPort"
        body = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"'
            ' s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
            f'<s:Body><u:{action} xmlns:u="{self.DEVICEINFO_SERVICE}"/></s:Body></s:Envelope>'
        )
        host = self._tr064_host()
        try:
            resp = self.session.post(
                f"http://{host}:{self.TR064_PLAIN_PORT}{self.DEVICEINFO_CONTROL}",
                data=body,
                headers={
                    "Content-Type": 'text/xml; charset="utf-8"',
                    "SOAPAction": f'"{self.DEVICEINFO_SERVICE}#{action}"',
                },
                timeout=10,
            )
            if resp.status_code != 200:
                return None
            port = int(_parse_soap_response(resp.text, action).get("NewSecurityPort", ""))
        except (requests.RequestException, Tr064Error, ValueError):
            return None
        return port if 0 < port < 65536 else None

    def get(self, path: str, **kwargs) -> requests.Response:
        params = dict(kwargs.pop("params", {}) or {})
        params["sid"] = self.sid
        return self.session.get(self.base_url + check_box_path(path),
                                params=params, timeout=30, **kwargs)

    def post(self, path: str, data: dict | None = None, **kwargs) -> requests.Response:
        payload = dict(data or {})
        payload["sid"] = self.sid
        return self.session.post(self.base_url + check_box_path(path),
                                 data=payload, timeout=30, **kwargs)

    def _tr064_host(self) -> str:
        host = urlsplit(self.base_url).hostname or self.base_url
        return f"[{host}]" if ":" in host else host

    def tr064_url(self, path: str) -> str:
        """URL eines TR-064-Pfads — auf dem TLS-Port, sofern :meth:`secure_tr064` lief.

        ``path`` stammt oft aus einer Box-Antwort und wird deshalb geprüft
        (:func:`check_box_path`). Ist TR-064 gesperrt, gibt es keine URL, sondern
        ``Tr064Disabled`` — die Extractoren fallen darauf bereits zurück.
        """
        check_box_path(path)
        if not self.tr064_scheme:
            raise Tr064Disabled(
                "TR-064 nur im Klartext erreichbar (Box nennt keinen TLS-Port) — "
                "gesperrt; mit --tr064-http ausdrücklich erlauben.")
        return f"{self.tr064_scheme}://{self._tr064_host()}:{self.tr064_port}{path}"

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
        # Werte escapen: Ein Argument mit & < > erzeugte sonst kaputtes oder
        # fremdbestimmtes XML. Heute reichen alle Extractoren nur Ziffern durch —
        # scharf wird die Stelle beim ersten Aufruf, der einen Wert aus einer
        # Box-Antwort zurückgibt (MAC, Gerätename, Telefonbucheintrag), und dort
        # fiele nichts auf (#40). Die Elementnamen stammen aus unseren eigenen
        # Modulkonstanten und sind keine Fremdeingabe.
        body_args = "".join(f"<{k}>{escape(str(v))}</{k}>" for k, v in args.items())
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
        except (requests.RequestException, Tr064Error):
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
            except (requests.RequestException, Tr064Error):
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
