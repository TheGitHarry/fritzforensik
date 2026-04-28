"""Telefonbuch — Liste aller Bücher via data.lua, Export via firmwarecfg."""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET

from ..client import FritzClient

DATA_PATH = "/data.lua"
FIRMWARECFG_PATH = "/cgi-bin/firmwarecfg"

# Neuere FRITZ!OS-Stände rendern bookLi als HTML-Tab-Inhalt; die Buchliste
# steckt dort als JS-Initialisierung `g_books = [...]`.
_GBOOKS_RE = re.compile(r"g_books\s*=\s*(\[.*?\])\s*;", re.DOTALL)


def _parse_books_payload(text: str) -> list[dict]:
    """Akzeptiert sowohl JSON-Antworten (data.phonebooks) als auch HTML mit g_books."""
    try:
        data = json.loads(text)
    except ValueError:
        data = None
    if isinstance(data, dict):
        books_raw = ((data.get("data") or {}).get("phonebooks")) or []
    else:
        m = _GBOOKS_RE.search(text)
        if not m:
            return []
        try:
            books_raw = json.loads(m.group(1))
        except ValueError:
            return []

    books: list[dict] = []
    for entry in books_raw:
        if not isinstance(entry, dict):
            continue
        try:
            book_id = int(entry.get("uniqueid", entry.get("id", -1)))
        except (TypeError, ValueError):
            continue
        if book_id < 0:
            continue
        books.append({"id": book_id, "name": entry.get("name", "")})
    return books


def _list_phonebooks(client: FritzClient) -> list[dict]:
    resp = client.post(
        DATA_PATH,
        data={"page": "bookLi", "xhr": "1", "xhrId": "all", "lang": "de"},
    )
    resp.raise_for_status()
    return _parse_books_payload(resp.text)


def _export_phonebook(client: FritzClient, book_id: int) -> str:
    files = {
        "sid": (None, client.sid),
        "PhonebookId": (None, str(book_id)),
        "PhonebookExportName": (None, f"Phonebook_{book_id}"),
        "PhonebookExport": (None, ""),
    }
    resp = client.session.post(client.base_url + FIRMWARECFG_PATH, files=files, timeout=30)
    resp.raise_for_status()
    return resp.text


def _parse_xml(xml_text: str, book_id: int, book_name: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    contacts: list[dict] = []
    for contact in root.iter("contact"):
        person = contact.find("person")
        name = (person.findtext("realName") if person is not None else "") or ""
        numbers = [
            {
                "type": n.get("type", ""),
                "number": (n.text or "").strip(),
                "vanity": n.get("vanity", ""),
            }
            for n in contact.iter("number")
            if (n.text or "").strip()
        ]
        contacts.append(
            {
                "phonebook_id": book_id,
                "phonebook_name": book_name,
                "name": name.strip(),
                "numbers": numbers,
            }
        )
    return contacts


def extract(client: FritzClient) -> list[dict]:
    books = _list_phonebooks(client)
    all_entries: list[dict] = []
    for book in books:
        xml_text = _export_phonebook(client, book["id"])
        all_entries.extend(_parse_xml(xml_text, book["id"], book.get("name", "")))
    return all_entries
