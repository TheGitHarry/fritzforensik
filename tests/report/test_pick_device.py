"""Identität der abgezogenen Box aus der Mesh-Liste wählen (#41).

Der Reportkopf trägt Gerät, Firmware und **Geräte-MAC des Asservats**. Die Quelle
dafür ist der Mesh-Knoten, dessen Name zur Host-URL des Abzugs passt — und „passt"
hieß bis #41 *Teilzeichenfolge*. Die Mesh-Liste enthält aber nicht nur Access
Points, sondern alle Knoten samt Clientnamen; im Korpus bis zu 103 Einträge.
"""
from __future__ import annotations

import pytest

from fritzreport.render import _pick_device

#: Das kollidierende Paar steht real in **einer** Mesh-Liste des Korpus
#: (Abzug export_20260713T114105Z_7690), MACs hier durch Platzhalter ersetzt.
FB7590MC = {"name": "fb7590mc", "model": "FRITZ!Box 7590", "mac": "aa:bb:cc:dd:ee:02",
            "role": "slave", "is_ap": True}
FB7590MC2 = {"name": "fb7590mc2", "model": "FRITZ!Box 7590", "mac": "aa:bb:cc:dd:ee:01",
             "role": "master", "is_ap": True}
CLIENT_NC = {"name": "nc", "model": "", "mac": "aa:bb:cc:dd:ee:03",
             "role": "client", "is_ap": False}


def test_laengerer_name_wird_nicht_vom_kuerzeren_verdraengt():
    """Der Befund aus #41: 'fb7590mc' ist Teilzeichenfolge von 'fb7590mc2', und der
    erste Treffer in Listenreihenfolge gewann — der Report wies die MAC einer
    anderen Box als Geräte-MAC des Asservats aus."""
    knoten = [FB7590MC, FB7590MC2]
    assert _pick_device(knoten, "https://fb7590mc2.lan")["mac"] == FB7590MC2["mac"]
    assert _pick_device(knoten, "https://fb7590mc.lan")["mac"] == FB7590MC["mac"]


def test_kurzer_clientname_trifft_nicht_jede_url():
    """Nebenbefund gleicher Ursache: Ein Knoten namens 'nc' steckt als Zeichenfolge
    in fast jeder Host-URL. Dass es bisher gutging, war Zufall der Zeichenauswahl."""
    knoten = [CLIENT_NC, FB7590MC2]
    gewaehlt = _pick_device(knoten, "https://fb7590mc2.lan")
    assert gewaehlt["name"] == "fb7590mc2", "Clientname hat die Box verdrängt"


@pytest.mark.parametrize("host", [
    "https://fb7590mc2.lan",
    "http://fb7590mc2.lan/",
    "https://fb7590mc2.lan:8443",
    "fb7590mc2.lan",
    "fb7590mc2",
    "https://FB7590MC2.lan",
])
def test_hostformen(host):
    """--host akzeptiert Schema, Port und Trailing-Slash; der Vergleich muss die
    alle gleich behandeln, sonst hängt die Geräteidentität an der Schreibweise."""
    assert _pick_device([FB7590MC, FB7590MC2], host)["name"] == "fb7590mc2"


def test_ip_host_faellt_in_die_bisherige_kette():
    """Bei einer IP gibt es keinen Namenstreffer — dann entscheidet wie bisher die
    pred-Kette, die im Korpus nachweislich richtig liegt (Master mit Modell)."""
    knoten = [CLIENT_NC, FB7590MC2, FB7590MC]
    assert _pick_device(knoten, "https://192.168.178.1")["name"] == "fb7590mc2"


def test_ohne_treffer_und_ohne_knoten():
    assert _pick_device([], "https://fritz.box") == {}
    fremd = _pick_device([FB7590MC], "https://ganz-andere-box.lan")
    assert fremd["name"] == "fb7590mc", "ohne Namenstreffer bleibt die pred-Kette"


def test_kein_urllib_in_fritzreport():
    """Der Vorschlag im Ticket wollte `urlsplit` benutzen — `urllib` steht aber auf
    der Netz-Sperrliste von `tests/format/test_stdlib_only.py`. Die Zerlegung muss
    deshalb ohne auskommen; dieser Test hält den Rückweg zu."""
    import ast
    from pathlib import Path

    quelle = Path(__file__).resolve().parents[2] / "fritzreport" / "render.py"
    baum = ast.parse(quelle.read_text(encoding="utf-8"))
    module = {
        (n.names[0].name if isinstance(n, ast.Import) else n.module or "")
        for n in ast.walk(baum) if isinstance(n, (ast.Import, ast.ImportFrom))
    }
    assert not any(m.split(".")[0] == "urllib" for m in module)
