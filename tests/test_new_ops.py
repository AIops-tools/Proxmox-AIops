"""Tests for the day-2 ops added to proxmox-aiops: backup, disk, cluster
read-views, HA, pools, firewall, and guest-agent ping.

All Proxmox calls are mocked at the proxmoxer connection (.get/.post/.put on the
resource-path proxy), so no real PVE is needed.
"""

from unittest.mock import MagicMock

import pytest

from proxmox_aiops.connection import _CONN_NODE
from proxmox_aiops.ops import agent as ag
from proxmox_aiops.ops import backup as bk
from proxmox_aiops.ops import cluster as cl
from proxmox_aiops.ops import disk as dk
from proxmox_aiops.ops import firewall as fw
from proxmox_aiops.ops import ha, pool


def _conn_with_qemu(vmid: int = 100) -> MagicMock:
    """A mocked connection whose node hosts a single QEMU VM ``vmid``."""
    conn = MagicMock(name="conn")
    conn.nodes.return_value.qemu.get.return_value = [{"vmid": vmid}]
    return conn


# ─── backups ───────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_backup_list_read_filters_by_vmid():
    conn = MagicMock(name="conn")
    conn.nodes.return_value.storage.return_value.content.get.return_value = [
        {"volid": "store:backup/vzdump-qemu-100.zst", "vmid": 100, "size": 10},
        {"volid": "store:backup/vzdump-qemu-200.zst", "vmid": 200, "size": 20},
    ]
    rows = bk.list_backups(conn, "store", node="pve1", vmid=100)
    assert len(rows) == 1
    assert rows[0]["vmid"] == 100
    conn.nodes.return_value.storage.return_value.content.get.assert_called_once_with(
        content="backup"
    )


@pytest.mark.unit
def test_backup_create_invalid_mode_rejected():
    conn = _conn_with_qemu()
    with pytest.raises(ValueError, match="Invalid backup mode"):
        bk.vm_backup(conn, 100, "store", node="pve1", mode="bogus")


@pytest.mark.unit
def test_backup_restore_refuses_overwrite_without_force():
    conn = MagicMock(name="conn")
    conn.nodes.return_value.qemu.get.return_value = [{"vmid": 100}]
    conn.nodes.return_value.lxc.get.return_value = []
    with pytest.raises(ValueError, match="already exists"):
        bk.restore_backup(conn, 100, "store:backup/a.zst", "local", node="pve1")


@pytest.mark.unit
def test_backup_restore_new_vmid_records_existed_before_false():
    conn = MagicMock(name="conn")
    conn.nodes.return_value.qemu.get.return_value = []  # vmid absent
    conn.nodes.return_value.lxc.get.return_value = []
    conn.nodes.return_value.qemu.post.return_value = "UPID:pve1:restore"
    result = bk.restore_backup(conn, 101, "store:backup/a.zst", "local", node="pve1")
    assert result["existed_before"] is False
    assert result["task"] == "UPID:pve1:restore"


# ─── disk ──────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_resize_disk_refuses_negative_increment():
    conn = _conn_with_qemu()
    with pytest.raises(ValueError, match="Refusing to shrink"):
        dk.resize_disk(conn, 100, "scsi0", "-5G", node="pve1")


@pytest.mark.unit
def test_resize_disk_refuses_smaller_absolute():
    conn = _conn_with_qemu()
    conn.nodes.return_value.qemu.return_value.config.get.return_value = {
        "scsi0": "local-lvm:vm-100-disk-0,size=32G",
    }
    with pytest.raises(ValueError, match="grow-only"):
        dk.resize_disk(conn, 100, "scsi0", "16G", node="pve1")


@pytest.mark.unit
def test_resize_disk_grow_increment_succeeds():
    conn = _conn_with_qemu()
    out = dk.resize_disk(conn, 100, "scsi0", "+10G", node="pve1")
    assert out["action"] == "vm_resize_disk"
    conn.nodes.return_value.qemu.return_value.resize.put.assert_called_once_with(
        disk="scsi0", size="+10G"
    )


@pytest.mark.unit
def test_move_disk_captures_source_storage():
    conn = _conn_with_qemu()
    conn.nodes.return_value.qemu.return_value.config.get.return_value = {
        "scsi0": "local-lvm:vm-100-disk-0,size=32G",
    }
    conn.nodes.return_value.qemu.return_value.move_disk.post.return_value = "UPID:x"
    out = dk.move_disk(conn, 100, "scsi0", "ceph", node="pve1")
    assert out["from_storage"] == "local-lvm"
    assert out["to_storage"] == "ceph"


# ─── cluster read-views ──────────────────────────────────────────────────────


@pytest.mark.unit
def test_cluster_resources_read():
    conn = MagicMock(name="conn")
    conn.cluster.resources.get.return_value = [
        {"id": "qemu/100", "type": "qemu", "name": "web", "node": "pve1",
         "status": "running", "vmid": 100},
        {"id": "node/pve1", "type": "node", "node": "pve1", "status": "online"},
    ]
    rows = cl.cluster_resources(conn)
    assert {r["type"] for r in rows} == {"qemu", "node"}
    assert rows[0]["vmid"] == 100


@pytest.mark.unit
def test_node_status_flattens_memory():
    conn = MagicMock(name="conn")
    conn.nodes.return_value.status.get.return_value = {
        "uptime": 1000, "cpu": 0.1, "loadavg": [0.1, 0.2, 0.3],
        "memory": {"total": 100, "used": 40, "free": 60},
    }
    st = cl.node_status(conn, "pve1")
    assert st["mem_total"] == 100 and st["mem_free"] == 60


@pytest.mark.unit
def test_task_log_and_next_vmid():
    conn = MagicMock(name="conn")
    conn.nodes.return_value.tasks.return_value.log.get.return_value = [
        {"n": 1, "t": "started"}, {"n": 2, "t": "done"},
    ]
    result = cl.task_log(conn, "UPID:pve1:0001:task", limit=10)
    assert result["lines"][0]["t"] == "started"
    assert result["returned"] == 2
    assert result["truncated"] is False
    conn.cluster.nextid.get.return_value = "101"
    assert cl.next_vmid(conn) == {"vmid": 101}


# ─── HA (absence handled gracefully) ─────────────────────────────────────────


@pytest.mark.unit
def test_ha_status_reports_not_configured():
    conn = MagicMock(name="conn")
    conn.cluster.ha.status.current.get.side_effect = Exception("500 no such resource")
    result = ha.ha_status(conn)
    assert result["configured"] is False
    assert result["entries"] == []
    assert "not configured" in result["message"].lower()


@pytest.mark.unit
def test_ha_status_configured():
    conn = MagicMock(name="conn")
    conn.cluster.ha.status.current.get.return_value = [
        {"id": "vm:100", "type": "service", "node": "pve1", "status": "started"},
    ]
    result = ha.ha_status(conn)
    assert result["configured"] is True
    assert result["entries"][0]["id"] == "vm:100"


@pytest.mark.unit
def test_ha_resource_list_empty_when_absent():
    conn = MagicMock(name="conn")
    conn.cluster.ha.resources.get.side_effect = Exception("404 not found")
    assert ha.ha_resource_list(conn) == []


# ─── pools & firewall & agent ────────────────────────────────────────────────


@pytest.mark.unit
def test_pool_list_and_members():
    conn = MagicMock(name="conn")
    conn.pools.get.return_value = [{"poolid": "prod", "comment": "Production"}]
    assert pool.pool_list(conn)[0]["poolid"] == "prod"
    conn.pools.return_value.get.return_value = {
        "comment": "Production",
        "members": [{"id": "qemu/100", "type": "qemu", "vmid": 100, "node": "pve1"}],
    }
    members = pool.pool_members(conn, "prod")
    assert members["members"][0]["vmid"] == 100


@pytest.mark.unit
def test_cluster_firewall_status_read():
    conn = MagicMock(name="conn")
    conn.cluster.firewall.options.get.return_value = {
        "enable": 1, "policy_in": "DROP", "policy_out": "ACCEPT",
    }
    st = fw.cluster_firewall_status(conn)
    assert st["enable"] == 1 and st["policy_in"] == "DROP"


@pytest.mark.unit
def test_vm_firewall_rules_read():
    conn = _conn_with_qemu()
    conn.nodes.return_value.qemu.return_value.firewall.rules.get.return_value = [
        {"pos": 0, "type": "in", "action": "ACCEPT", "proto": "tcp", "dport": "22"},
    ]
    rules = fw.vm_firewall_rules(conn, 100, node="pve1")
    assert rules[0]["dport"] == "22"


@pytest.mark.unit
def test_agent_ping_responsive_and_absent():
    conn = _conn_with_qemu()
    conn.nodes.return_value.qemu.return_value.agent.ping.post.return_value = {}
    assert ag.agent_ping(conn, 100, node="pve1")["responsive"] is True

    conn2 = _conn_with_qemu()
    conn2.nodes.return_value.qemu.return_value.agent.ping.post.side_effect = Exception(
        "QEMU guest agent is not running"
    )
    out = ag.agent_ping(conn2, 100, node="pve1")
    assert out["responsive"] is False
    assert "agent" in out["message"].lower()


@pytest.mark.unit
def test_backup_restore_mcp_tool_is_high_risk():
    """backup_restore is gated at the highest risk tier (overwrite is destructive)."""
    from mcp_server.tools import backup as backup_tools

    assert backup_tools.backup_restore._is_governed_tool is True
    assert backup_tools.backup_restore._risk_level == "high"


@pytest.mark.unit
def test_backup_restore_undo_deletes_only_new_vm(monkeypatch):
    """Restoring into a free vmid records a vm_delete inverse via the harness."""
    import proxmox_aiops.governance.undo as undo_mod
    from mcp_server.tools import backup as backup_tools

    conn = MagicMock(name="conn")
    conn.nodes.return_value.qemu.get.return_value = []  # vmid absent → new VM
    conn.nodes.return_value.lxc.get.return_value = []
    conn.nodes.return_value.qemu.post.return_value = "UPID:pve1:restore"
    monkeypatch.setattr(backup_tools, "_get_connection", lambda target=None: conn)

    recorded = {}

    class _Store:
        def record(self, *, skill, tool, undo_descriptor, orig_params):
            recorded["descriptor"] = undo_descriptor
            return "undo-r"

    monkeypatch.setattr(undo_mod, "get_undo_store", lambda: _Store())

    result = backup_tools.backup_restore(
        vmid=101, archive="store:backup/a.zst", storage="local", node="pve1"
    )
    assert "error" not in result
    assert recorded["descriptor"]["tool"] == "vm_delete"
    assert recorded["descriptor"]["params"]["vmid"] == 101


@pytest.mark.unit
def test_move_disk_undo_moves_back_to_source(monkeypatch):
    """vm_move_disk records a reverse move to the captured source storage."""
    import proxmox_aiops.governance.undo as undo_mod
    from mcp_server.tools import disk as disk_tools

    conn = _conn_with_qemu()
    conn.nodes.return_value.qemu.return_value.config.get.return_value = {
        "scsi0": "local-lvm:vm-100-disk-0,size=32G",
    }
    conn.nodes.return_value.qemu.return_value.move_disk.post.return_value = "UPID:x"
    monkeypatch.setattr(disk_tools, "_get_connection", lambda target=None: conn)

    recorded = {}

    class _Store:
        def record(self, *, skill, tool, undo_descriptor, orig_params):
            recorded["descriptor"] = undo_descriptor
            return "undo-m"

    monkeypatch.setattr(undo_mod, "get_undo_store", lambda: _Store())

    result = disk_tools.vm_move_disk(vmid=100, disk="scsi0", storage="ceph", node="pve1")
    assert "error" not in result
    d = recorded["descriptor"]
    assert d["tool"] == "vm_move_disk"
    assert d["params"]["storage"] == "local-lvm"  # back to source


@pytest.mark.unit
def test_list_backups_uses_default_node():
    """Default node from the connection is honoured when node is omitted."""
    conn = MagicMock(name="conn")
    conn.nodes.return_value.storage.return_value.content.get.return_value = []
    _CONN_NODE[id(conn)] = "pve-default"
    try:
        assert bk.list_backups(conn, "store") == []
        conn.nodes.assert_called_with("pve-default")
    finally:
        _CONN_NODE.pop(id(conn), None)
