"""ABDECKUNG.md ist zur Veröffentlichung bestimmt — sie darf nichts verraten.

Der Generator (``scripts/abdeckung.py``) liest echte Abzüge und schreibt eine
Datei, die im Repo landet und bei einer Veröffentlichung öffentlich wird. Ein
Fehler dort verrät Seriennummern oder Aktenzeichen an alle, unwiderruflich.
Diese Tests prüfen deshalb beides: dass der Generator aus einem präparierten
Bundle nichts Identifizierendes übernimmt, und dass die eingecheckte Datei
selbst sauber ist.
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ABDECKUNG = REPO_ROOT / "ABDECKUNG.md"

_spec = importlib.util.spec_from_file_location(
    "abdeckung", REPO_ROOT / "scripts" / "abdeckung.py"
)
abdeckung = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(abdeckung)

#: Werte, die im präparierten Bundle stehen und NIE in der Ausgabe landen dürfen.
GEHEIM = {
    "seriennummer": "X99999999999999",
    "aktenzeichen": "VG/SH/999999/2026",
    "hostname": "geheime-box.example.lan",
    "ip": "10.11.12.13",
    "sachbearbeiter": "Musterfrau",
}


@pytest.fixture
def praepariertes_bundle(tmp_path: Path) -> Path:
    """Ein Bundle, dessen Felder ausschließlich verräterische Werte enthalten."""
    b = tmp_path / "export_20260101T000000Z_test"
    b.mkdir()
    (b / "supportdata_standard_20260101T000000Z.txt").write_text(
        "HWRevision\t285\n"
        "HWSubRevision\t2\n"
        f"SerialNumber\t{GEHEIM['seriennummer']}\n"
        "firmware_info\t285.08.25,slot0=08.22-129542,slot1=08.25-134025\n"
        f"Hostname\t{GEHEIM['hostname']}\n",
        encoding="utf-8",
    )
    (b / "supportdata_mesh_20260101T000000Z.txt").write_text("x\n", encoding="utf-8")
    (b / "case.json").write_text(
        json.dumps({"case_id": GEHEIM["aktenzeichen"], "sb": GEHEIM["sachbearbeiter"]}),
        encoding="utf-8",
    )
    # 7 Anrufe — die Zahl darf nirgends auftauchen, sie ist ein Rückschluss
    # auf den Haushalt.
    (b / f"fritzexport_{GEHEIM['ip']}_20260101T000000Z_calls.json").write_text(
        json.dumps({
            "tool": "fritzexport", "version": "0.4.0",
            "host": f"https://{GEHEIM['ip']}",
            "extracted_at": "2026-01-01T00:00:00Z", "type": "calls",
            "records": [{"nr": i} for i in range(7)],
        }),
        encoding="utf-8",
    )
    return tmp_path


def test_generator_verraet_nichts(praepariertes_bundle: Path) -> None:
    befunde = [
        b for b in (
            abdeckung.lies_bundle(p)
            for p in praepariertes_bundle.iterdir() if p.is_dir()
        ) if b
    ]
    assert befunde, "Testbundle wurde nicht erkannt"
    text = abdeckung.erzeuge(befunde)

    for was, wert in GEHEIM.items():
        assert wert not in text, f"{was} steht in der erzeugten Matrix"
    # Auch der Bundle-Verzeichnisname (trägt den Abzugszeitpunkt) darf nicht rein.
    assert "export_20260101T000000Z_test" not in text
    assert "20260101T000000Z" not in text


def test_generator_gibt_keine_datensatzzahlen_aus(praepariertes_bundle: Path) -> None:
    """Nur ob eine Datenart Daten lieferte, nie wie viele."""
    befunde = [
        b for b in (
            abdeckung.lies_bundle(p)
            for p in praepariertes_bundle.iterdir() if p.is_dir()
        ) if b
    ]
    text = abdeckung.erzeuge(befunde)
    zeile = next(z for z in text.splitlines() if z.startswith("| FRITZ!Box"))
    assert "7" not in zeile.split("|")[4:], "Datensatzzahl in der Matrixzeile"
    assert befunde[0]["datenarten"]["calls"] == "ja"


def test_firmware_ohne_slot_angaben() -> None:
    """Slot-Angaben würden gleiche FRITZ!OS-Stände als verschiedene Zeilen zeigen."""
    assert abdeckung.firmware_kurz("285.08.25,slot0=08.22-1,slot1=08.25-2") == "08.25"
    assert abdeckung.firmware_kurz("154.08.02") == "08.02"
    assert abdeckung.firmware_kurz("07.29") == "07.29"
    assert abdeckung.firmware_kurz("") == ""


@pytest.mark.skipif(not ABDECKUNG.exists(), reason="ABDECKUNG.md nicht vorhanden")
def test_eingecheckte_datei_ist_sauber() -> None:
    """Die Datei im Repo selbst — sie ist es, die veröffentlicht wird."""
    text = ABDECKUNG.read_text(encoding="utf-8")

    muster = {
        "Seriennummer": r"\b[A-Z]\d{14}\b",
        "Aktenzeichen": r"VG[/-]SH[/-]\d+",
        "IP-Adresse": r"\b(?:192\.168|10\.|172\.(?:1[6-9]|2\d|3[01]))\.\d+\.\d+\b",
        "Bundle-Zeitstempel": r"\b20\d{6}T\d{6}Z\b",
        "interner Hostname": r"\b[\w-]+\.(?:lan|local|intern)\b",
    }
    for name, m in muster.items():
        treffer = re.findall(m, text)
        assert not treffer, f"{name} in ABDECKUNG.md: {treffer[:3]}"
