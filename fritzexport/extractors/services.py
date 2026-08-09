"""TR-064-Dienstverzeichnis der Box — was bietet sie an, was holen wir ab?

Beantwortet die Frage, die sich sonst niemand stellt: Ob die Box Datenquellen
anbietet, für die es keinen Extractor gibt. Die Extractor-Liste ist eine
Setzung; ein Test hält sie nur mit ``fritzformat.JSON_TYPES`` synchron, prüft
also interne Konsistenz — nicht, ob wir etwas übersehen.

**Nur beim Abzug erfassbar.** Das Verzeichnis steht in keiner anderen
Bundle-Datei; auch die Supportdaten enthalten es nicht (dort tauchen
ausschließlich Dienste auf, die fritzexport selbst aufgerufen hat — Spuren der
eigenen Abfragen im Box-Log). Wird es hier nicht festgehalten, ist es nach dem
Lauf verloren.

Ein Datensatz je angebotenem Dienst; ``genutzt`` sagt, ob ein Extractor ihn
abholt. Was mit ``genutzt: false`` erscheint, ist keine Fehlfunktion, sondern
eine Kandidatenliste für künftige Extractoren.
"""
from __future__ import annotations

import logging

from ..client import FritzClient

log = logging.getLogger(__name__)


def genutzte_services() -> set[str]:
    """Welche TR-064-Dienste die vorhandenen Extractoren aufrufen.

    Wird aus den Modulkonstanten der Extractoren zusammengesucht (jede heißt
    ``*_SERVICE`` und trägt eine ``urn:``-URN), statt als zweite Liste
    gepflegt zu werden: Eine Handliste veraltet still, sobald jemand einen
    Extractor ergänzt — genau der Fehler, den die feste Aufzählung in
    ``cli.py`` heute macht.
    """
    import importlib
    import pkgutil

    from . import __name__ as paket, __path__ as pfad

    gefunden: set[str] = set()
    for modul in pkgutil.iter_modules(pfad):
        if modul.name == "services":
            continue
        try:
            m = importlib.import_module(f"{paket}.{modul.name}")
        except ImportError:  # pragma: no cover — defekte Extractoren fallen anderswo auf
            continue
        for name in dir(m):
            if not name.endswith("_SERVICE") and name != "SERVICE":
                continue
            wert = getattr(m, name)
            if isinstance(wert, str) and wert.startswith("urn:"):
                gefunden.add(wert)
    return gefunden


def extract(client: FritzClient) -> list[dict]:
    # hasattr statt direktem Aufruf: Der Abzug darf nicht daran scheitern, dass
    # ein Client die Methode nicht kennt — etwa ein älterer oder ein Ersatz in
    # einem Testaufbau. Eine fehlende Dienstliste ist kein Grund, den ganzen
    # Lauf abzubrechen.
    angeboten = client.tr064_services() if hasattr(client, "tr064_services") else []
    if not angeboten:
        log.info(
            "TR-064-Dienstverzeichnis nicht abrufbar — kein Abgleich möglich. "
            "Ohne TR-064-Zugang ist das erwartbar."
        )
        return []

    genutzt = genutzte_services()
    records = [
        {
            "service_type": d["service_type"],
            "control_url": d["control_url"],
            "genutzt": d["service_type"] in genutzt,
        }
        for d in angeboten
    ]

    offen = [r["service_type"] for r in records if not r["genutzt"]]
    log.info(
        "TR-064-Dienste: %d angeboten, %d davon genutzt, %d ungenutzt.",
        len(records), len(records) - len(offen), len(offen),
    )
    if offen:
        log.info("Ungenutzt: %s", ", ".join(sorted(offen)))
    return records
