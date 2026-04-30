"""Offline-Tests für Mesh-Extractor (TR-064-Pfad + Web-UI-Fallback)."""
from __future__ import annotations

from unittest.mock import MagicMock

from legacy_export.client import Tr064Disabled
from legacy_export.extractors import mesh as mesh_mod


# Realistisches AVM-Mesh-JSON (gekürzt). Zwei Knoten, ein Link, der in beiden
# Endpoint-Interfaces auftaucht — Test prüft Dedup via link.uid.
MESH_PAYLOAD = {
    "schema_version": "1.9",
    "nodes": [
        {
            "uid": "n-1",
            "device_name": "fritz.box",
            "device_model": "FRITZ!Box 7590",
            "device_manufacturer": "AVM",
            "device_firmware_version": "07.50",
            "device_mac_address": "AA:BB:CC:DD:EE:01",
            "is_meshed": True,
            "mesh_role": "master",
            "node_interfaces": [
                {
                    "uid": "ni-11",
                    "name": "WLAN-5",
                    "type": "WLAN",
                    "node_links": [
                        {
                            "uid": "nl-1",
                            "type": "WLAN",
                            "state": "CONNECTED",
                            "node_1_uid": "n-1",
                            "node_2_uid": "n-2",
                            "node_interface_1_uid": "ni-11",
                            "node_interface_2_uid": "ni-21",
                            "max_data_rate_rx": 1300000,
                            "max_data_rate_tx": 1300000,
                            "cur_data_rate_rx": 800000,
                            "cur_data_rate_tx": 750000,
                        }
                    ],
                }
            ],
        },
        {
            "uid": "n-2",
            "device_name": "FRITZ!Repeater",
            "device_model": "FRITZ!Repeater 3000",
            "device_manufacturer": "AVM",
            "device_firmware_version": "07.50",
            "device_mac_address": "AA:BB:CC:DD:EE:02",
            "is_meshed": True,
            "mesh_role": "slave",
            "node_interfaces": [
                {
                    "uid": "ni-21",
                    "name": "WLAN-5",
                    "type": "WLAN",
                    "node_links": [
                        # Gleicher Link von der anderen Seite — soll dedupt werden.
                        {
                            "uid": "nl-1",
                            "type": "WLAN",
                            "state": "CONNECTED",
                            "node_1_uid": "n-1",
                            "node_2_uid": "n-2",
                        }
                    ],
                }
            ],
        },
    ],
}


def test_flatten_emits_node_and_link_records_with_dedup():
    records = mesh_mod._flatten(MESH_PAYLOAD)
    nodes = [r for r in records if r["record_type"] == "node"]
    links = [r for r in records if r["record_type"] == "link"]
    assert len(nodes) == 2
    assert {n["uid"] for n in nodes} == {"n-1", "n-2"}
    # Master-Felder
    master = next(n for n in nodes if n["mesh_role"] == "master")
    assert master["device_model"] == "FRITZ!Box 7590"
    assert master["is_meshed"] is True
    # Link einmal, trotz beidseitigem Auftauchen
    assert len(links) == 1
    link = links[0]
    assert link["uid"] == "nl-1"
    assert link["type"] == "WLAN"
    assert link["state"] == "CONNECTED"
    assert link["max_data_rate_tx"] == 1300000


def test_flatten_handles_empty_payload():
    assert mesh_mod._flatten({}) == []
    assert mesh_mod._flatten({"nodes": []}) == []


def test_flatten_skips_non_dict_entries():
    payload = {"nodes": [None, "garbage", {"uid": "n-1", "node_interfaces": [None, {"uid": "ni-1", "node_links": ["bad", {"uid": "nl-1"}]}]}]}
    records = mesh_mod._flatten(payload)
    assert len(records) == 2
    assert records[0]["record_type"] == "node"
    assert records[1]["record_type"] == "link"


def test_extract_uses_tr064_path_when_available():
    client = MagicMock()
    client.tr064_call.return_value = {"NewX_AVM-DE_MeshListPath": "/meshlist.lua?sid=abc&hkid=xyz"}
    client.base_url = "https://192.168.2.1"
    client.tr064_url.return_value = "http://192.168.2.1:49000/meshlist.lua"
    fake_resp = MagicMock()
    fake_resp.json.return_value = MESH_PAYLOAD
    fake_resp.raise_for_status.return_value = None
    client.session.get.return_value = fake_resp
    records = mesh_mod.extract(client)
    assert any(r["record_type"] == "node" for r in records)
    # TR-064 muss genau einmal angefragt werden, Web-UI-Fallback NICHT genutzt
    client.tr064_call.assert_called_once()
    # session.get muss mit Pfad-eigener SID aufgerufen worden sein, nicht mit Session-SID
    args, kwargs = client.session.get.call_args
    assert "/meshlist.lua" in args[0]
    assert kwargs["params"].get("sid") == "abc"


def test_extract_falls_back_to_webui_when_tr064_disabled():
    client = MagicMock()
    client.tr064_call.side_effect = Tr064Disabled("TR-064 aus", error_code=606)
    fake_resp = MagicMock()
    fake_resp.json.return_value = MESH_PAYLOAD
    fake_resp.raise_for_status.return_value = None
    client.session.get.return_value = fake_resp
    records = mesh_mod.extract(client)
    assert any(r["record_type"] == "node" for r in records)
    # Fallback nutzt session.get auf Port-49000-URL, nicht client.get
    client.session.get.assert_called_once()


def test_extract_returns_empty_when_both_paths_fail():
    client = MagicMock()
    client.tr064_call.side_effect = Tr064Disabled("aus")
    client.session.get.side_effect = OSError("network down")
    assert mesh_mod.extract(client) == []


def test_extract_returns_empty_when_tr064_path_empty():
    client = MagicMock()
    client.tr064_call.return_value = {"NewX_AVM-DE_MeshListPath": ""}
    # Ohne TR-064-Pfad → Web-UI-Fallback wird genutzt (auf Port 49000)
    fake_resp = MagicMock()
    fake_resp.json.return_value = MESH_PAYLOAD
    fake_resp.raise_for_status.return_value = None
    client.session.get.return_value = fake_resp
    records = mesh_mod.extract(client)
    assert any(r["record_type"] == "node" for r in records)
    client.session.get.assert_called_once()
