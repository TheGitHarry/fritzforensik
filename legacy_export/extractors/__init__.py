from .calls import extract as extract_calls
from .phonebook import extract as extract_phonebook
from .wifi import extract as extract_wifi
from .events import extract as extract_events

EXTRACTORS = {
    "calls": extract_calls,
    "phonebook": extract_phonebook,
    "wifi": extract_wifi,
    "events": extract_events,
}
