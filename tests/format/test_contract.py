"""Der Formatvertrag zwischen fritzexport (schreibt) und fritzreport (liest).

Genau diese Prüfungen fehlten, solange die beiden Werkzeuge in getrennten Repos
lagen: die Datenart-Listen und das Bundle-Layout waren auf beiden Seiten von
Hand gepflegt, eine Abweichung wäre erst im Feld aufgefallen.
"""
from __future__ import annotations

import json

from fritzformat import (
    JSON_TYPES,
    SUPPORT_VARIANTS,
    TOOL_NAME,
    dataset_filename,
    read_envelope_meta,
    sha256_bytes,
    support_filename,
    verify,
    write_sidecar,
)
from fritzexport import output
from fritzexport.extractors import EXTRACTORS
from fritzexport.extractors.supportdata import _VARIANTS
from fritzreport.bundle import load_bundle
from fritzreport.cli import is_bundle


# ─────────────────────── Listen auf beiden Seiten identisch ──────────────────

def test_extractor_registry_deckt_sich_mit_den_datenarten() -> None:
    """Jeder Extractor erzeugt genau eine Datenart, die der Report auch sucht."""
    assert set(EXTRACTORS) == set(JSON_TYPES), (
        "Extractor-Registry und fritzformat.JSON_TYPES sind auseinandergelaufen: "
        f"nur im Export {set(EXTRACTORS) - set(JSON_TYPES)}, "
        f"nur im Format {set(JSON_TYPES) - set(EXTRACTORS)}"
    )


def test_supportdaten_varianten_decken_sich() -> None:
    kurznamen = {short for _feld, short in _VARIANTS}
    assert kurznamen == set(SUPPORT_VARIANTS)


# ──────────────────────────── Schreiben → Lesen ──────────────────────────────

def test_bundle_rundlauf(tmp_path) -> None:
    """Was fritzexport schreibt, muss fritzreport vollständig zurücklesen."""
    host = "https://192.168.178.1"
    ts = "20260724T101530Z"
    for type_name in JSON_TYPES:
        output.write(tmp_path, host, type_name, [{"probe": type_name}], timestamp=ts)

    # Roh-Supportdatei wie der supportdata-Extractor sie ablegt
    raw = tmp_path / support_filename("standard", ts)
    body = b"##### TITLE Version 8.20\n"
    raw.write_bytes(body)
    write_sidecar(raw, sha256_bytes(body))

    assert is_bundle(tmp_path), "geschriebenes Bundle wird nicht als solches erkannt"

    b = load_bundle(tmp_path)
    for type_name in JSON_TYPES:
        ds = b.ds(type_name)
        assert ds.present, f"Datenart '{type_name}' nicht wiedergefunden"
        assert ds.status == "ok", f"Integritätsprüfung für '{type_name}': {ds.status}"
        assert ds.records == [{"probe": type_name}]
    assert b.support["standard"].present
    assert b.integrity_ok
    assert b.meta["tool"] == TOOL_NAME


def test_dateiname_und_huelle_passen_zusammen(tmp_path) -> None:
    path = output.write(tmp_path, "https://fritz.box", "hosts", [], timestamp="20260724T101530Z")
    assert path.name == dataset_filename("https://fritz.box", "20260724T101530Z", "hosts")
    meta = read_envelope_meta(json.loads(path.read_text(encoding="utf-8")))
    assert meta["tool"] == TOOL_NAME
    assert meta["host"] == "https://fritz.box"


def test_sidecar_ueberlebt_umbenennung(tmp_path) -> None:
    """Verifiziert wird der Digest, nicht der Dateiname — ein umbenanntes
    Bundle bleibt prüfbar (genutzt beim Aufbau des Golden-Korpus)."""
    path = output.write(tmp_path, "https://fritz.box", "hosts", [{"a": 1}])
    sidecar = path.with_suffix(path.suffix + ".sha256")
    neu = path.with_name("umbenannt_hosts.json")
    path.rename(neu)
    sidecar.rename(neu.with_suffix(neu.suffix + ".sha256"))
    status, _digest = verify(neu)
    assert status == "ok"


def test_mismatch_wird_erkannt(tmp_path) -> None:
    """Gegenprobe zur Integritätsprüfung — sie darf nicht blind 'ok' sagen."""
    path = output.write(tmp_path, "https://fritz.box", "hosts", [{"a": 1}])
    path.write_bytes(path.read_bytes() + b" ")
    status, _digest = verify(path)
    assert status == "mismatch"
