"""Tests for LXC container ops (proxmox_aiops/ops/lxc.py): list, start, stop,
node inference, and the not-found teaching error.
"""

from unittest.mock import MagicMock

import pytest

from proxmox_aiops.connection import _CONN_NODE
from proxmox_aiops.ops import lxc


@pytest.mark.unit
def test_list_cts_normalizes_cpu_mem_fallbacks():
    conn = MagicMock(name="conn")
    conn.nodes.return_value.lxc.get.return_value = [
        {"vmid": 200, "name": "web", "status": "running", "cpus": 2, "maxmem": 512},
    ]
    _CONN_NODE[id(conn)] = "pve1"
    try:
        rows = lxc.list_cts(conn)
        conn.nodes.assert_called_with("pve1")
        assert rows[0]["vmid"] == 200
        assert rows[0]["cpu"] == 2  # from "cpus"
        assert rows[0]["mem"] == 512  # from "maxmem"
        assert rows[0]["node"] == "pve1"
    finally:
        _CONN_NODE.pop(id(conn), None)


@pytest.mark.unit
def test_list_cts_scans_all_nodes_without_default():
    conn = MagicMock(name="conn")
    conn.nodes.get.return_value = [{"node": "pve1"}, {"node": "pve2"}]

    def _node(node):
        m = MagicMock()
        m.lxc.get.return_value = [{"vmid": 300}] if node == "pve2" else []
        return m

    conn.nodes.side_effect = _node
    rows = lxc.list_cts(conn)
    assert [r["vmid"] for r in rows] == [300]
    assert rows[0]["node"] == "pve2"


@pytest.mark.unit
def test_start_ct_posts_to_status_start():
    conn = MagicMock(name="conn")
    conn.nodes.return_value.lxc.get.return_value = [{"vmid": 200}]
    conn.nodes.return_value.lxc.return_value.status.start.post.return_value = "UPID:s"
    _CONN_NODE[id(conn)] = "pve1"
    try:
        out = lxc.start_ct(conn, 200)
        assert out["action"] == "ct_start"
        assert out["task"] == "UPID:s"
        conn.nodes.return_value.lxc.return_value.status.start.post.assert_called_once_with()
    finally:
        _CONN_NODE.pop(id(conn), None)


@pytest.mark.unit
def test_stop_ct_posts_to_status_stop():
    conn = MagicMock(name="conn")
    conn.nodes.return_value.lxc.get.return_value = [{"vmid": 200}]
    conn.nodes.return_value.lxc.return_value.status.stop.post.return_value = "UPID:t"
    _CONN_NODE[id(conn)] = "pve1"
    try:
        out = lxc.stop_ct(conn, 200)
        assert out["action"] == "ct_stop"
        conn.nodes.return_value.lxc.return_value.status.stop.post.assert_called_once_with()
    finally:
        _CONN_NODE.pop(id(conn), None)


@pytest.mark.unit
def test_find_node_for_ct_not_found_raises():
    conn = MagicMock(name="conn")
    conn.nodes.return_value.lxc.get.return_value = []
    _CONN_NODE[id(conn)] = "pve1"
    try:
        with pytest.raises(lxc.ContainerNotFoundError, match="not found"):
            lxc.start_ct(conn, 999)
    finally:
        _CONN_NODE.pop(id(conn), None)
