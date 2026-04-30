"""Mesh-Topologie — TR-064 X_AVM-DE_GetMeshListPath, JSON-Fetch.

Forensische Goldgrube: liefert pro Knoten (Box, Repeater, Powerline-Adapter,
Endgerät) und pro Verbindung (LAN/WLAN-2.4/5/Powerline) je einen Record mit
`record_type`-Diskriminator. Felder: UID, Geräte-Modell/MAC/IP, Mesh-Rolle,
Link-State, Datenraten, Parent/Child-Beziehung.

Pfad: TR-064 `X_AVM-DE_GetMeshListPath` → relativer URL inkl. eigener SID →
JSON-Fetch direkt auf Box-Host. Web-UI-Fallback via `meshlist.lua` mit
Session-SID, falls TR-064 deaktiviert.
"""
from __future__ import annotations

import logging

from ..client import FritzClient, Tr064Disabled, Tr064Error

log = logging.getLogger(__name__)

HOSTS_SERVICE = "urn:dslforum-org:service:Hosts:1"
HOSTS_CONTROL = "/upnp/control/hosts"
MESH_ACTION = "X_AVM-DE_GetMeshListPath"
MESH_RESULT_KEY = "NewX_AVM-DE_MeshListPath"
WEBUI_FALLBACK_PATH = "/meshlist.lua"


def _get_meshlist_path_via_tr064(client: FritzClient) -> str | None:
    try:
        resp = client.tr064_call(HOSTS_SERVICE, HOSTS_CONTROL, MESH_ACTION)
    except Tr064Disabled as e:
        log.info("TR-064 GetMeshListPath nicht zugänglich: %s — Web-UI-Fallback.", e)
        return None
    except Tr064Error as e:
        log.warning("TR-064 GetMeshListPath fehlgeschlagen: %s — Web-UI-Fallback.", e)
        return None
    return (resp.get(MESH_RESULT_KEY) or "").strip() or None


def _split_path_query(url_path: str) -> tuple[str, dict[str, str]]:
    if "?" not in url_path:
        return url_path, {}
    path, _, query = url_path.partition("?")
    params = dict(p.split("=", 1) for p in query.split("&") if "=" in p)
    return path, params


def _fetch_meshlist_json_tr064(client: FritzClient, mesh_path: str) -> dict | None:
    """JSON via TR-064-gelieferten Pfad (eigene SID darin, nicht überschreiben)."""
    path, params = _split_path_query(mesh_path)
    # client.get würde die Session-SID an die Query hängen — nicht erwünscht,
    # weil der Pfad seine eigene fresh-SID mitbringt. Daher direkt session.get.
    resp = client.session.get(client.base_url + path, params=params, timeout=30)
    resp.raise_for_status()
    try:
        return resp.json()
    except ValueError:
        log.warning("Mesh-List-Antwort ist kein JSON (TR-064-Pfad)")
        return None


def _fetch_meshlist_json_webui(client: FritzClient) -> dict | None:
    """Fallback: meshlist.lua direkt mit Session-SID."""
    resp = client.get(WEBUI_FALLBACK_PATH)
    resp.raise_for_status()
    try:
        return resp.json()
    except ValueError:
        log.warning("Mesh-List-Antwort ist kein JSON (Web-UI-Fallback)")
        return None


def _node_record(node: dict) -> dict:
    return {
        "record_type": "node",
        "uid": node.get("uid", ""),
        "device_name": node.get("device_name", ""),
        "device_model": node.get("device_model", ""),
        "device_manufacturer": node.get("device_manufacturer", ""),
        "device_firmware_version": node.get("device_firmware_version", ""),
        "device_mac_address": node.get("device_mac_address", ""),
        "is_meshed": bool(node.get("is_meshed", False)),
        "mesh_role": node.get("mesh_role", ""),
        "meshd_version": node.get("meshd_version", ""),
        "raw": node,
    }


def _link_record(link: dict, node_uid: str, interface_uid: str) -> dict:
    return {
        "record_type": "link",
        "uid": link.get("uid", ""),
        "type": link.get("type", ""),
        "state": link.get("state", ""),
        "node_1_uid": link.get("node_1_uid", ""),
        "node_2_uid": link.get("node_2_uid", ""),
        "node_interface_1_uid": link.get("node_interface_1_uid", ""),
        "node_interface_2_uid": link.get("node_interface_2_uid", ""),
        "max_data_rate_rx": link.get("max_data_rate_rx", ""),
        "max_data_rate_tx": link.get("max_data_rate_tx", ""),
        "cur_data_rate_rx": link.get("cur_data_rate_rx", ""),
        "cur_data_rate_tx": link.get("cur_data_rate_tx", ""),
        "owning_node_uid": node_uid,
        "owning_interface_uid": interface_uid,
        "raw": link,
    }


def _flatten(payload: dict) -> list[dict]:
    nodes = payload.get("nodes") or []
    records: list[dict] = []
    seen_links: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            continue
        records.append(_node_record(node))
        for iface in node.get("node_interfaces") or []:
            if not isinstance(iface, dict):
                continue
            iface_uid = iface.get("uid", "")
            for link in iface.get("node_links") or []:
                if not isinstance(link, dict):
                    continue
                # Links erscheinen in beiden Endpoint-Interfaces; per UID dedupen.
                link_uid = link.get("uid", "")
                if link_uid and link_uid in seen_links:
                    continue
                if link_uid:
                    seen_links.add(link_uid)
                records.append(_link_record(link, node.get("uid", ""), iface_uid))
    return records


def extract(client: FritzClient) -> list[dict]:
    """Mesh-Topologie: Nodes + Links als flache Records mit record_type-Marker."""
    payload: dict | None = None
    mesh_path = _get_meshlist_path_via_tr064(client)
    if mesh_path:
        try:
            payload = _fetch_meshlist_json_tr064(client, mesh_path)
        except Exception as e:
            log.info("Mesh-Fetch via TR-064-Pfad fehlgeschlagen: %s", e)
    if payload is None:
        try:
            payload = _fetch_meshlist_json_webui(client)
        except Exception as e:
            log.info("Mesh-Fetch via Web-UI-Fallback fehlgeschlagen: %s", e)
            return []
    if not isinstance(payload, dict):
        return []
    return _flatten(payload)
