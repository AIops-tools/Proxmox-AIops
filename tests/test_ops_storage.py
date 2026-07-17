"""Tests for the storage read-view ops (proxmox_aiops/ops/storage.py).

All Proxmox calls are mocked at the proxmoxer connection proxy, so no live PVE
is needed. Assertions check the exact resource path / method called, the params
passed, normalization of canned responses, and the node-required teaching error.
"""

from unittest.mock import MagicMock

import pytest

from proxmox_aiops.connection import _CONN_NODE
from proxmox_aiops.ops import storage as st


@pytest.mark.unit
def test_list_storage_normalizes_and_hits_node_path():
    conn = MagicMock(name="conn")
    conn.nodes.return_value.storage.get.return_value = [
        {
            "storage": "local-lvm",
            "type": "lvmthin",
            "active": 1,
            "enabled": 1,
            "total": 100,
            "used": 40,
            "avail": 60,
        },
    ]
    rows = st.list_storage(conn, node="pve1")
    conn.nodes.assert_called_once_with("pve1")
    conn.nodes.return_value.storage.get.assert_called_once_with()
    assert len(rows) == 1
    row = rows[0]
    assert row["storage"] == "local-lvm"
    assert row["type"] == "lvmthin"
    assert row["total"] == 100 and row["avail"] == 60
    assert row["node"] == "pve1"


@pytest.mark.unit
def test_list_storage_uses_default_node_when_omitted():
    conn = MagicMock(name="conn")
    conn.nodes.return_value.storage.get.return_value = []
    _CONN_NODE[id(conn)] = "pve-default"
    try:
        assert st.list_storage(conn) == []
        conn.nodes.assert_called_once_with("pve-default")
    finally:
        _CONN_NODE.pop(id(conn), None)


@pytest.mark.unit
def test_list_storage_without_node_raises_node_required():
    conn = MagicMock(name="conn")
    with pytest.raises(st.NodeRequiredError, match="No node specified"):
        st.list_storage(conn)


@pytest.mark.unit
def test_list_storage_content_without_filter():
    conn = MagicMock(name="conn")
    endpoint = conn.nodes.return_value.storage.return_value.content
    endpoint.get.return_value = [
        {
            "volid": "local:iso/debian.iso",
            "content": "iso",
            "format": "iso",
            "size": 700,
            "vmid": None,
        },
    ]
    rows = st.list_storage_content(conn, "local", node="pve1")
    conn.nodes.assert_called_once_with("pve1")
    conn.nodes.return_value.storage.assert_called_once_with("local")
    # No content filter → bare get()
    endpoint.get.assert_called_once_with()
    assert rows[0]["volid"] == "local:iso/debian.iso"
    assert rows[0]["content"] == "iso"


@pytest.mark.unit
def test_list_storage_content_with_content_filter_passes_param():
    conn = MagicMock(name="conn")
    endpoint = conn.nodes.return_value.storage.return_value.content
    endpoint.get.return_value = [
        {"volid": "local:backup/x.zst", "content": "backup", "format": "zst",
         "size": 10, "vmid": 100},
    ]
    rows = st.list_storage_content(conn, "local", node="pve1", content="backup")
    endpoint.get.assert_called_once_with(content="backup")
    assert rows[0]["vmid"] == 100


@pytest.mark.unit
def test_list_storage_content_without_node_raises():
    conn = MagicMock(name="conn")
    with pytest.raises(st.NodeRequiredError):
        st.list_storage_content(conn, "local")
