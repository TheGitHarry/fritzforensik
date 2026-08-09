from .calls import extract as extract_calls
from .phonebook import extract as extract_phonebook
from .wifi import extract as extract_wifi
from .events import extract as extract_events
from .tam import extract as extract_tam
from .mesh import extract as extract_mesh
from .hosts import extract as extract_hosts
from .wan import extract as extract_wan
from .dhcp import extract as extract_dhcp
from .portforward import extract as extract_portforward
from .storage import extract as extract_storage
from .supportdata import extract as extract_supportdata
from .tr069 import extract as extract_tr069
from .services import extract as extract_services
from .boxtime import extract as extract_boxtime
from .deviceinfo import extract as extract_deviceinfo

EXTRACTORS = {
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
