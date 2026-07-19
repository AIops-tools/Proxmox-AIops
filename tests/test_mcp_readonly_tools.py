"""Governed-twin tests for the read-only MCP tool modules (cluster, agent,
backup_list) that were previously exercised only at the ops layer. Each test
patches the module-local ``_get_connection`` with a mocked proxmoxer conn and
drives the tool through its full governance decorator stack, asserting the
resource path/method and normalized shape.
"""

from unittest.mock import MagicMock

import pytest

from mcp_server.tools import agent as agent_tools
from mcp_server.tools import backup as backup_tools
from mcp_server.tools import cluster as cluster_tools

# ─── cluster read tools ──────────────────────────────────────────────────────


@pytest.mark.unit
def test_node_list_tool(monkeypatch):
    conn = MagicMock(name="conn")
    conn.nodes.get.return_value = [{"node": "pve1", "status": "online"}]
    monkeypatch.setattr(cluster_tools, "_get_connection", lambda target=None: conn)
    rows = cluster_tools.node_list()
    assert rows[0]["node"] == "pve1"


@pytest.mark.unit
def test_cluster_status_tool(monkeypatch):
    conn = MagicMock(name="conn")
    conn.cluster.status.get.return_value = [
        {"type": "cluster", "name": "c", "quorate": 1},
    ]
    monkeypatch.setattr(cluster_tools, "_get_connection", lambda target=None: conn)
    rows = cluster_tools.cluster_status()
    assert rows[0]["quorate"] == 1


@pytest.mark.unit
def test_task_status_tool(monkeypatch):
    conn = MagicMock(name="conn")
    conn.nodes.return_value.tasks.return_value.status.get.return_value = {
        "status": "stopped", "exitstatus": "OK",
    }
    monkeypatch.setattr(cluster_tools, "_get_connection", lambda target=None: conn)
    out = cluster_tools.task_status("UPID:pve1:a:b")
    assert out["status"] == "stopped"
    assert out["node"] == "pve1"


@pytest.mark.unit
def test_task_status_tool_bad_upid_returns_safe_error(monkeypatch):
    conn = MagicMock(name="conn")
    monkeypatch.setattr(cluster_tools, "_get_connection", lambda target=None: conn)
    out = cluster_tools.task_status("garbage")
    # tool_errors("dict") sanitizes the ValueError into an error envelope
    assert "error" in out
    assert "Could not determine node" in out["error"]


@pytest.mark.unit
def test_cluster_resources_tool_passes_type_filter(monkeypatch):
    conn = MagicMock(name="conn")
    conn.cluster.resources.get.return_value = [
        {"id": "qemu/100", "type": "qemu", "vmid": 100},
    ]
    monkeypatch.setattr(cluster_tools, "_get_connection", lambda target=None: conn)
    rows = cluster_tools.cluster_resources(resource_type="vm")
    conn.cluster.resources.get.assert_called_once_with(type="vm")
    assert rows[0]["vmid"] == 100


@pytest.mark.unit
def test_node_status_tool(monkeypatch):
    conn = MagicMock(name="conn")
    conn.nodes.return_value.status.get.return_value = {
        "uptime": 5, "memory": {"total": 10, "used": 4, "free": 6},
    }
    monkeypatch.setattr(cluster_tools, "_get_connection", lambda target=None: conn)
    out = cluster_tools.node_status("pve1")
    assert out["mem_total"] == 10 and out["mem_free"] == 6


@pytest.mark.unit
def test_task_log_tool(monkeypatch):
    conn = MagicMock(name="conn")
    conn.nodes.return_value.tasks.return_value.log.get.return_value = [
        {"n": 1, "t": "line"},
    ]
    monkeypatch.setattr(cluster_tools, "_get_connection", lambda target=None: conn)
    result = cluster_tools.task_log("UPID:pve1:a:b", limit=3)
    # One extra line is requested so truncation is measured, not guessed.
    conn.nodes.return_value.tasks.return_value.log.get.assert_called_once_with(limit=4)
    assert result["lines"][0]["t"] == "line"
    assert result["returned"] == 1
    assert result["truncated"] is False


@pytest.mark.unit
def test_next_vmid_tool(monkeypatch):
    conn = MagicMock(name="conn")
    conn.cluster.nextid.get.return_value = "111"
    monkeypatch.setattr(cluster_tools, "_get_connection", lambda target=None: conn)
    assert cluster_tools.next_vmid() == {"vmid": 111}


# ─── agent + backup_list read tools ──────────────────────────────────────────


@pytest.mark.unit
def test_vm_agent_ping_tool_responsive(monkeypatch):
    conn = MagicMock(name="conn")
    conn.nodes.return_value.qemu.get.return_value = [{"vmid": 100}]
    conn.nodes.return_value.qemu.return_value.agent.ping.post.return_value = {}
    monkeypatch.setattr(agent_tools, "_get_connection", lambda target=None: conn)
    out = agent_tools.vm_agent_ping(100, node="pve1")
    assert out["responsive"] is True


@pytest.mark.unit
def test_backup_list_tool_filters_by_vmid(monkeypatch):
    conn = MagicMock(name="conn")
    conn.nodes.return_value.storage.return_value.content.get.return_value = [
        {"volid": "s:backup/a.zst", "vmid": 100, "size": 1},
        {"volid": "s:backup/b.zst", "vmid": 200, "size": 2},
    ]
    monkeypatch.setattr(backup_tools, "_get_connection", lambda target=None: conn)
    rows = backup_tools.backup_list("store", vmid=100, node="pve1")
    assert [r["vmid"] for r in rows] == [100]


@pytest.mark.unit
def test_vm_backup_tool_medium_risk_and_posts(monkeypatch):
    conn = MagicMock(name="conn")
    conn.nodes.return_value.vzdump.post.return_value = "UPID:pve1:vzdump"
    monkeypatch.setattr(backup_tools, "_get_connection", lambda target=None: conn)
    assert backup_tools.vm_backup._risk_level == "medium"
    out = backup_tools.vm_backup(100, "store", node="pve1")
    assert out["action"] == "vm_backup"
