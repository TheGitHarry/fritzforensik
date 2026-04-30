"""Erweiterte Supportdaten — POST /cgi-bin/firmwarecfg mit getextendedsupdatadata=1."""
from __future__ import annotations

import logging

from ..client import FritzClient

log = logging.getLogger(__name__)

FIRMWARECFG_PATH = "/cgi-bin/firmwarecfg"


def extract(client: FritzClient) -> list[dict]:
    resp = client.session.post(
        client.base_url + FIRMWARECFG_PATH,
        data={"sid": client.sid, "getextendedsupdatadata": "1"},
        timeout=60,
    )
    resp.raise_for_status()

    content_type = resp.headers.get("Content-Type", "")
    try:
        text = resp.content.decode("utf-8")
    except UnicodeDecodeError:
        text = resp.content.decode("latin-1")

    if not text.strip():
        log.warning("Supportdaten-Response ist leer — TR-064 oder Benutzerrecht fehlt?")

    return [
        {
            "content_type": content_type,
            "size_bytes": len(resp.content),
            "content": text,
        }
    ]
