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
    "tr069_serial": "00040E-AABBCCDDEEFF",
    "mac": "AA:BB:CC:DD:EE:FF",
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
        f"tr069_serial\t{GEHEIM['tr069_serial']}\n"
        f"maca\t{GEHEIM['mac']}\n"
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


def _kopf(serial: str, hwrev: str = "285", tr069: str | None = None) -> list[str]:
    zeilen = [f"SerialNumber\t{serial}\n", f"HWRevision\t{hwrev}\n"]
    if tr069 is not None:
        zeilen.append(f"tr069_serial\t{tr069}\n")
    return zeilen


def test_geraetekennung_verraet_die_rohwerte_nicht() -> None:
    """Die Kennung dient nur dem Zählen — sie darf nichts preisgeben."""
    serial, tr069 = "S49589630118571", "00040E-B4FC7D6DC067"
    kennung = abdeckung._geraetekennung(_kopf(serial, tr069=tr069))
    assert serial not in kennung
    assert tr069 not in kennung
    assert "B4FC7D6DC067" not in kennung
    assert len(kennung) == 16
    assert kennung == abdeckung._geraetekennung(_kopf(serial, tr069=tr069))


def test_tr069_serial_hat_vorrang_und_ueberlebt_genullte_serial() -> None:
    """Der 7490-Fall: SerialNumber genullt, tr069_serial intakt."""
    intakt = abdeckung._geraetekennung(_kopf("0000000000000000", "185", "00040E-3810D53D0D43"))
    assert intakt, "tr069_serial hätte die Kennung liefern müssen"

    # Dieselbe Box, aber mit gefüllter SerialNumber → weiterhin dieselbe
    # Kennung, weil tr069_serial Vorrang hat. Ohne Rangfolge (etwa beide
    # Felder kombiniert) zerfiele eine Box in zwei Geräte.
    spaeter = abdeckung._geraetekennung(_kopf("X12345678901234", "185", "00040E-3810D53D0D43"))
    assert intakt == spaeter

    # Verschiedene Boxen bleiben unterscheidbar.
    andere = abdeckung._geraetekennung(_kopf("0000000000000000", "185", "00040E-444E6D260163"))
    assert intakt != andere


def test_ohne_brauchbares_feld_zaehlt_einzeln() -> None:
    """Sind beide Felder unbrauchbar, dürfen Geräte nicht verschmelzen."""
    assert abdeckung._geraetekennung(_kopf("0000000000000000")) == ""
    assert abdeckung._geraetekennung(_kopf("", tr069="")) == ""
    assert abdeckung._geraetekennung(_kopf("0000", tr069="000000")) == ""
    assert abdeckung.geraetezahl([{"geraet": ""}, {"geraet": ""}]) == 2


def test_geraetezahl_fuehrt_gleiche_box_zusammen() -> None:
    gleiche = abdeckung._geraetekennung(_kopf("S49589630118571", tr069="00040E-B4FC7D6DC067"))
    andere = abdeckung._geraetekennung(_kopf("P40262732383692", tr069="00040E-50E636D393F3"))
    assert abdeckung.geraetezahl([{"geraet": gleiche}] * 3) == 1
    assert abdeckung.geraetezahl(
        [{"geraet": gleiche}, {"geraet": gleiche}, {"geraet": andere}]
    ) == 2


def _befund(genullt: bool) -> dict:
    return {
        "modell": "FRITZ!Box 7490", "hwrev": "185", "firmware": "07.62",
        "geraet": "abc1234567890def", "serial_genullt": genullt,
        "support": ["standard"],
        "datenarten": {art: "ja" for art in abdeckung.JSON_TYPES},
    }


def test_hinweis_zur_genullten_serial_nur_wenn_betroffen() -> None:
    """Der Hinweis erklärt einen Befund — ohne Befund hat er nichts zu suchen."""
    mit = abdeckung.erzeuge([_befund(True)])
    assert "### Genullte Seriennummer" in mit
    assert "generischen AVM-Image" in mit
    assert "tr069_serial" in mit, "die praktische Folge fehlt"

    ohne = abdeckung.erzeuge([_befund(False)])
    assert "### Genullte Seriennummer" not in ohne


def test_hinweis_nennt_keine_serial() -> None:
    """Auch der erklärende Text darf den Rohwert nicht enthalten."""
    text = abdeckung.erzeuge([_befund(True)])
    assert "0000000000000000" not in text


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
        # Die Gerätekennung ist ein gekürzter SHA256 und dient nur dem Zählen;
        # sie darf ebenso wenig in der Datei stehen wie die Serial selbst.
        "Hash/Gerätekennung": r"\b[0-9a-f]{12,}\b",
    }
    for name, m in muster.items():
        treffer = re.findall(m, text)
        assert not treffer, f"{name} in ABDECKUNG.md: {treffer[:3]}"
