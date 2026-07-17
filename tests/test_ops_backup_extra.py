"""Tests for backup ops guest-location logic and vm_backup path not covered by
test_new_ops.py: explicit node, default-node scan, full cluster scan, the
VMNotFoundError teaching error, and list_backups' node-required guard.
"""

from unittest.mock import MagicMock

import pytest

from proxmox_aiops.connection import _CONN_NODE
from proxmox_aiops.ops import backup as bk
from proxmox_aiops.ops.vm_lifecycle import VMNotFoundError


@pytest.mark.unit
def test_vm_backup_trusts_explicit_node_and_posts_vzdump():
    conn = MagicMock(name="conn")
    conn.nodes.return_value.vzdump.post.return_value = "UPID:pve1:vzdump"
    out = bk.vm_backup(conn, 100, "store", node="pve1", mode="stop", compress="zstd")
    conn.nodes.assert_called_with("pve1")
    conn.nodes.return_value.vzdump.post.assert_called_once_with(
        vmid=100, storage="store", mode="stop", compress="zstd"
    )
    assert out["action"] == "vm_backup"
    assert out["mode"] == "stop"
    assert out["task"] == "UPID:pve1:vzdump"


@pytest.mark.unit
def test_vm_backup_locates_guest_via_default_node():
    conn = MagicMock(name="conn")
    conn.nodes.return_value.qemu.get.return_value = [{"vmid": 100}]
    conn.nodes.return_value.lxc.get.return_value = []
    conn.nodes.return_value.vzdump.post.return_value = "UPID:x"
    _CONN_NODE[id(conn)] = "pve-default"
    try:
        out = bk.vm_backup(conn, 100, "store")
        assert out["node"] == "pve-default"
    finally:
        _CONN_NODE.pop(id(conn), None)


@pytest.mark.unit
def test_vm_backup_scans_cluster_nodes_when_no_default():
    """No default node → every cluster node is scanned; the CT match wins."""
    conn = MagicMock(name="conn")
    conn.nodes.get.return_value = [{"node": "pve1"}, {"node": "pve2"}]

    def _qemu_for(node):
        m = MagicMock()
        m.qemu.get.return_value = []  # not a QEMU VM anywhere
        m.lxc.get.return_value = [{"vmid": 100}] if node == "pve2" else []
        m.vzdump.post.return_value = "UPID:pve2:vzdump"
        return m

    conn.nodes.side_effect = lambda node: _qemu_for(node)
    out = bk.vm_backup(conn, 100, "store")
    assert out["node"] == "pve2"


@pytest.mark.unit
def test_vm_backup_missing_guest_raises_vmnotfound():
    conn = MagicMock(name="conn")
    conn.nodes.get.return_value = [{"node": "pve1"}]
    conn.nodes.return_value.qemu.get.return_value = []
    conn.nodes.return_value.lxc.get.return_value = []
    with pytest.raises(VMNotFoundError, match="not found"):
        bk.vm_backup(conn, 999, "store")


@pytest.mark.unit
def test_list_backups_without_node_raises():
    conn = MagicMock(name="conn")
    with pytest.raises(bk.NodeRequiredError):
        bk.list_backups(conn, "store")
