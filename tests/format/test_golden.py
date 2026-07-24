"""Lauf gegen die echten Bundles unter ``~/testdata`` — Regressionsnetz.

Standardmäßig **deselektiert** (Marker ``golden``), weil die Daten nicht im Repo
liegen und liegen sollen. Gezielt starten mit::

    python -m pytest -m golden

Der Wert dieser Tests liegt in der Breite: echte Bundles mehrerer Boxmodelle und
mehrerer Formatstände, mit denen sich stille Formatänderungen bemerkbar machen,
bevor sie im Feld auffallen.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from fritzreport.bundle import load_bundle
from fritzreport.cli import is_bundle
from fritzreport.model import build_model
from fritzreport.render import build_html
from fritzreport.supportdata import analyze

pytestmark = pytest.mark.golden

BASE = Path(os.path.expanduser("~/testdata/_work"))


def _bundles() -> list[Path]:
    if not BASE.is_dir():
        return []
    return sorted(p for p in BASE.iterdir() if is_bundle(p))


@pytest.fixture(params=_bundles(), ids=lambda p: p.name)
def echtes_bundle(request) -> Path:
    return request.param


def test_korpus_ist_vorhanden() -> None:
    if not BASE.is_dir():
        pytest.skip(f"Golden-Korpus {BASE} nicht vorhanden")
    assert _bundles(), f"in {BASE} liegt kein erkennbares Bundle"


def test_integritaet_vollstaendig_ok(echtes_bundle: Path) -> None:
    b = load_bundle(echtes_bundle)
    schlecht = [e.file for e in b.coc if e.status == "mismatch"]
    assert not schlecht, f"Integritätsprüfung fehlgeschlagen für: {schlecht}"
    assert b.coc, "keine einzige Datei mit Sidecar gefunden"


def test_report_baut_durch(echtes_bundle: Path) -> None:
    b = load_bundle(echtes_bundle)
    model = build_model(b)
    master = model.master.get("name", "") or (model.real_aps[0] if model.real_aps else "")
    support = analyze(b, model.real_aps, master)
    html = build_html(b, model, support,
                      {"case_id": "", "item_id": "", "sb": "", "date": "2026-01-01",
                       "generated_at": "2026-01-01T00:00:00Z"})

    assert html.startswith("<!DOCTYPE html>") or "<html" in html[:200].lower()
    assert len(html) > 100_000, "Report verdächtig klein"
    assert model.hosts, "keine Hosts im Modell — Bundle wurde nicht ausgewertet"
    # Der Kopf muss aus dem Bundle stammen, nicht leer bleiben.
    assert b.meta.get("host"), "Hüllformat lieferte keinen Host"
