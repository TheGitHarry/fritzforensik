from .calls import extract as extract_calls
from .phonebook import extract as extract_phonebook
from .wifi import extract as extract_wifi
from .events import extract as extract_events
from .tam import extract as extract_tam

EXTRACTORS = {
    "calls": extract_calls,
    "phonebook": extract_phonebook,
    "wifi": extract_wifi,
    "events": extract_events,
    "tam": extract_tam,
}

# Extractoren, die einen audio_dir-Parameter akzeptieren und ein
# (records, extra_meta)-Tupel statt nur records zurückgeben.
EXTRACTORS_WITH_AUDIO = {"tam"}
