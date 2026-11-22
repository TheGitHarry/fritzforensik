from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from ..client import FritzClient
from .boxtime import extract as extract_boxtime
from .calls import extract as extract_calls
from .deviceinfo import extract as extract_deviceinfo
from .dhcp import extract as extract_dhcp
from .events import extract as extract_events
from .hosts import extract as extract_hosts
from .mesh import extract as extract_mesh
from .phonebook import extract as extract_phonebook
from .portforward import extract as extract_portforward
from .services import extract as extract_services
from .storage import extract as extract_storage
from .supportdata import extract as extract_supportdata
from .tam import extract as extract_tam
from .tr069 import extract as extract_tr069
from .wan import extract as extract_wan
from .wifi import extract as extract_wifi

#: Was ein Extractor zurückgibt: je Datenart eine Liste von Datensätzen. Jedes
#: Modul typisiert seine Datensätze selbst; hier zählt nur, dass sie als JSON-Objekt
#: in die Hülle passen.
Records = Sequence[Mapping[str, object]]

#: Extractor, der nur den Client braucht.
Extract = Callable[[FritzClient], Records]
#: Extractor, der zusätzlich ein Verzeichnis bekommt und Metadaten für den Kopf liefert.
ExtractWithDir = Callable[[FritzClient, Path], tuple[Records, Mapping[str, object]]]

# Alle Extractoren in Abrufreihenfolge. Die Reihenfolge bestimmt auch die der
# CLI-Schalter; cli.py ruft über die beiden typisierten Gruppen darunter auf.
EXTRACTORS: dict[str, Extract | ExtractWithDir] = {
    "calls": extract_calls,
    "phonebook": extract_phonebook,
    "wifi": extract_wifi,
    "events": extract_events,
    "tam": extract_tam,
    "mesh": extract_mesh,
    "hosts": extract_hosts,
    "wan": extract_wan,
    "dhcp": extract_dhcp,
    "portforward": extract_portforward,
    "storage": extract_storage,
    "supportdata": extract_supportdata,
    "tr069": extract_tr069,
    "services": extract_services,
    "boxtime": extract_boxtime,
    "deviceinfo": extract_deviceinfo,
}

# Extractoren, die einen audio_dir-Parameter akzeptieren und ein
# (records, extra_meta)-Tupel statt nur records zurückgeben.
EXTRACTORS_WITH_AUDIO: dict[str, ExtractWithDir] = {"tam": extract_tam}

# Extractoren, die output_dir (das Hauptverzeichnis) akzeptieren und ein
# (records, extra_meta)-Tupel zurückgeben. Werden für Rohdatei-Ablage genutzt.
EXTRACTORS_WITH_DIR: dict[str, ExtractWithDir] = {"supportdata": extract_supportdata}

# Alle übrigen: nur der Client.
EXTRACTORS_PLAIN: dict[str, Extract] = {
    name: fn for name, fn in (
        ("calls", extract_calls), ("phonebook", extract_phonebook), ("wifi", extract_wifi),
        ("events", extract_events), ("mesh", extract_mesh), ("hosts", extract_hosts),
        ("wan", extract_wan), ("dhcp", extract_dhcp), ("portforward", extract_portforward),
        ("storage", extract_storage), ("tr069", extract_tr069), ("services", extract_services),
        ("boxtime", extract_boxtime), ("deviceinfo", extract_deviceinfo),
    )
}
