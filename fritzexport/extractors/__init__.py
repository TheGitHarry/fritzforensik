from collections.abc import Callable
from typing import Any

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

# Die Extractoren haben verschiedene Signaturen (manche bekommen ein Verzeichnis);
# cli.py wählt den Aufruf über EXTRACTORS_WITH_AUDIO/_WITH_DIR.
EXTRACTORS: dict[str, Callable[..., Any]] = {
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
EXTRACTORS_WITH_AUDIO = {"tam"}

# Extractoren, die output_dir (das Hauptverzeichnis) akzeptieren und ein
# (records, extra_meta)-Tupel zurückgeben. Werden für Rohdatei-Ablage genutzt.
EXTRACTORS_WITH_DIR = {"supportdata"}
