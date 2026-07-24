"""Anrufliste — CSV-Download über /fon_num/foncalls_list.lua?csv=."""
from __future__ import annotations

import csv
import io

from ..client import FritzClient

CALLS_PATH = "/fon_num/foncalls_list.lua"


def extract(client: FritzClient) -> list[dict]:
    resp = client.get(CALLS_PATH, params={"csv": ""})
    resp.raise_for_status()
    text = resp.text

    lines = text.splitlines()
    while lines and not lines[0].lstrip().startswith(("Typ;", "Type;")):
        lines.pop(0)
    if not lines:
        return []

    reader = csv.DictReader(io.StringIO("\n".join(lines)), delimiter=";")
    return [{(k or "").strip(): (v or "").strip() for k, v in row.items()} for row in reader]
