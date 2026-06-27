"""Smoke tests for the proxmox-aiops skeleton.

Proves: every module imports, the CLI Typer app builds and --help works, the
MCP server exposes the expected tools, and EVERY MCP tool carries the
proxmox-aiops harness marker ``_is_governed_tool`` (i.e. the governance harness
wraps them). No real Proxmox connection is needed — ``proxmoxer.ProxmoxAPI``
is mocked.
"""

import asyncio
import importlib
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

EXPECTED_TOOLS = {
    # VM lifecycle
    "vm_list", "vm_get", "vm_config",
    "vm_start", "vm_stop", "vm_shutdown", "vm_reboot", "vm_reconfigure",
    "vm_clone", "vm_delete", "vm_migrate",
    "vm_snapshot_create", "vm_snapshot_delete", "vm_snapshot_rollback", "vm_list_snapshots",
    # cluster / tasks
    "node_list", "cluster_status", "task_status",
    "cluster_resources", "node_status", "task_log", "next_vmid",
    # LXC containers
    "ct_list", "ct_start", "ct_stop",
    # storage
    "storage_list", "storage_content",
    # backups
    "vm_backup", "backup_list", "backup_restore",
    # disk
    "vm_resize_disk", "vm_move_disk",
    # HA
    "ha_status", "ha_resource_list",
    # pools
    "pool_list", "pool_members",
    # firewall
    "vm_firewall_rules_list", "cluster_firewall_status",
    # agent
    "vm_agent_ping",
}

WRITE_TOOLS_WITH_UNDO = {
    "vm_start", "vm_stop", "vm_shutdown", "vm_reconfigure", "vm_clone", "vm_migrate",
    "vm_snapshot_create", "ct_start", "ct_stop",
}


@pytest.fixture(autouse=True)
def _mock_proxmoxer(monkeypatch):
    """Replace proxmoxer.ProxmoxAPI so no real connection is attempted."""
    import proxmoxer

    monkeypatch.setattr(proxmoxer, "ProxmoxAPI", MagicMock(name="ProxmoxAPI"))


@pytest.mark.unit
def test_all_modules_import():
    for name in (
        "proxmox_aiops",
        "proxmox_aiops.config",
        "proxmox_aiops.connection",
        "proxmox_aiops.doctor",
        "proxmox_aiops.ops.vm_lifecycle",
        "proxmox_aiops.ops.storage",
        "proxmox_aiops.ops.cluster",
        "proxmox_aiops.ops.lxc",
        "proxmox_aiops.ops.backup",
        "proxmox_aiops.ops.disk",
        "proxmox_aiops.ops.ha",
        "proxmox_aiops.ops.pool",
        "proxmox_aiops.ops.firewall",
        "proxmox_aiops.ops.agent",
        "proxmox_aiops.cli",
        "proxmox_aiops.cli._root",
        "proxmox_aiops.cli._common",
        "proxmox_aiops.cli.vm",
        "proxmox_aiops.cli.cluster",
        "proxmox_aiops.cli.lxc",
        "proxmox_aiops.cli.storage",
        "proxmox_aiops.cli.backup",
        "proxmox_aiops.cli.ha",
        "proxmox_aiops.cli.pool",
        "proxmox_aiops.cli.firewall",
        "proxmox_aiops.cli.doctor",
        "mcp_server.server",
        "mcp_server._shared",
        "mcp_server.tools.vm",
        "mcp_server.tools.cluster",
        "mcp_server.tools.lxc",
        "mcp_server.tools.storage",
        "mcp_server.tools.backup",
        "mcp_server.tools.disk",
        "mcp_server.tools.ha",
        "mcp_server.tools.pool",
        "mcp_server.tools.firewall",
        "mcp_server.tools.agent",
    ):
        importlib.import_module(name)


@pytest.mark.unit
def test_version():
    import proxmox_aiops

    assert proxmox_aiops.__version__ == "0.2.0"


@pytest.mark.unit
def test_cli_app_builds_and_help_works():
    from proxmox_aiops.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for sub in ("vm", "ct", "cluster", "storage", "backup", "ha", "pool",
                "firewall", "doctor", "mcp"):
        assert sub in result.output


@pytest.mark.unit
def test_cli_leaf_help_triggers_lazy_imports():
    """Recurse into leaf commands so any broken lazy import surfaces (踩坑 #27)."""
    from proxmox_aiops.cli import app

    runner = CliRunner()
    for cmd in (
        ["vm", "--help"], ["ct", "--help"], ["cluster", "--help"],
        ["storage", "--help"], ["backup", "--help"], ["ha", "--help"],
        ["pool", "--help"], ["firewall", "--help"], ["doctor", "--help"],
    ):
        result = runner.invoke(app, cmd)
        assert result.exit_code == 0, f"{cmd} failed: {result.output}"
    for cmd in (
        ["vm", "list", "--help"], ["vm", "get", "--help"], ["vm", "config", "--help"],
        ["vm", "start", "--help"], ["vm", "stop", "--help"], ["vm", "shutdown", "--help"],
        ["vm", "reboot", "--help"], ["vm", "reconfigure", "--help"], ["vm", "clone", "--help"],
        ["vm", "delete", "--help"], ["vm", "migrate", "--help"],
        ["vm", "snapshot-create", "--help"], ["vm", "snapshot-delete", "--help"],
        ["vm", "snapshot-rollback", "--help"], ["vm", "snapshot-list", "--help"],
        ["vm", "resize-disk", "--help"], ["vm", "move-disk", "--help"],
        ["vm", "agent-ping", "--help"],
        ["ct", "list", "--help"], ["ct", "start", "--help"], ["ct", "stop", "--help"],
        ["cluster", "nodes", "--help"], ["cluster", "status", "--help"],
        ["cluster", "task-status", "--help"], ["cluster", "resources", "--help"],
        ["cluster", "node-status", "--help"], ["cluster", "task-log", "--help"],
        ["cluster", "next-vmid", "--help"],
        ["storage", "list", "--help"], ["storage", "content", "--help"],
        ["backup", "create", "--help"], ["backup", "list", "--help"],
        ["backup", "restore", "--help"],
        ["ha", "status", "--help"], ["ha", "resources", "--help"],
        ["pool", "list", "--help"], ["pool", "members", "--help"],
        ["firewall", "vm-rules", "--help"], ["firewall", "cluster-status", "--help"],
    ):
        result = runner.invoke(app, cmd)
        assert result.exit_code == 0, f"{cmd} failed: {result.output}"


@pytest.mark.unit
def test_mcp_list_tools_exposes_expected_tools():
    from mcp_server.server import mcp

    tools = asyncio.run(mcp.list_tools())
    names = {t.name for t in tools}
    assert EXPECTED_TOOLS <= names, f"missing: {EXPECTED_TOOLS - names}"


@pytest.mark.unit
def test_every_mcp_tool_is_governed_by_harness():
    """Every registered tool callable must carry the @governed_tool marker."""
    from mcp_server import _shared

    # FastMCP keeps the registered callables in its tool manager.
    tool_objs = _shared.mcp._tool_manager._tools
    assert EXPECTED_TOOLS <= set(tool_objs), "tool registry incomplete"
    for name, tool in tool_objs.items():
        fn = getattr(tool, "fn", None)
        assert fn is not None, f"{name} has no fn"
        assert getattr(fn, "_is_governed_tool", False), (
            f"{name} is not wrapped with @governed_tool (harness marker missing)"
        )


@pytest.mark.unit
def test_write_tool_records_undo_token_via_harness(monkeypatch):
    """Calling vm_start through the harness records an inverse undo descriptor.

    Proves the @governed_tool ``undo=`` feature lights up: the harness invokes the
    undo lambda on success and persists the inverse to the undo store.
    """
    import proxmox_aiops.governance.undo as undo_mod
    from mcp_server.tools import vm as vm_tools

    # Mock the proxmoxer connection used by the tool.
    conn = MagicMock(name="conn")
    conn.nodes.return_value.qemu.get.return_value = [{"vmid": 100, "name": "x"}]
    conn.nodes.return_value.qemu.return_value.status.start.post.return_value = "UPID:..."
    monkeypatch.setattr(vm_tools, "_get_connection", lambda target=None: conn)

    recorded = {}

    class _Store:
        def record(self, *, skill, tool, undo_descriptor, orig_params):
            recorded["descriptor"] = undo_descriptor
            recorded["tool"] = tool
            return "undo-123"

    monkeypatch.setattr(undo_mod, "get_undo_store", lambda: _Store())

    result = vm_tools.vm_start(vmid=100, node="pve1")
    assert "error" not in result
    assert recorded["descriptor"]["tool"] == "vm_stop"  # inverse of start
    assert recorded["descriptor"]["params"]["vmid"] == 100
    assert result.get("_undo_id") == "undo-123"


@pytest.mark.unit
def test_reconfigure_undo_restores_previous_values(monkeypatch):
    """vm_reconfigure's undo descriptor restores the captured prior cores/memory."""
    import proxmox_aiops.governance.undo as undo_mod
    from mcp_server.tools import vm as vm_tools

    conn = MagicMock(name="conn")
    conn.nodes.return_value.qemu.get.return_value = [{"vmid": 100, "name": "x"}]
    conn.nodes.return_value.qemu.return_value.config.get.return_value = {
        "cores": 2, "memory": 2048,
    }
    monkeypatch.setattr(vm_tools, "_get_connection", lambda target=None: conn)

    recorded = {}

    class _Store:
        def record(self, *, skill, tool, undo_descriptor, orig_params):
            recorded["descriptor"] = undo_descriptor
            return "undo-rc"

    monkeypatch.setattr(undo_mod, "get_undo_store", lambda: _Store())

    result = vm_tools.vm_reconfigure(vmid=100, cores=8, memory=8192, node="pve1")
    assert "error" not in result
    d = recorded["descriptor"]
    assert d["tool"] == "vm_reconfigure"
    assert d["params"]["cores"] == 2  # restores the previous value
    assert d["params"]["memory"] == 2048


@pytest.mark.unit
def test_ops_use_mocked_connection():
    """list_vms works end-to-end against a mocked proxmoxer connection."""
    from proxmox_aiops.connection import _CONN_NODE
    from proxmox_aiops.ops import vm_lifecycle as vl

    conn = MagicMock(name="conn")
    conn.nodes.return_value.qemu.get.return_value = [
        {"vmid": 100, "name": "web-01", "status": "running", "cpus": 2, "maxmem": 2048},
    ]
    _CONN_NODE[id(conn)] = "pve1"
    rows = vl.list_vms(conn, node="pve1")
    assert rows[0]["vmid"] == 100
    assert rows[0]["name"] == "web-01"
    _CONN_NODE.pop(id(conn), None)
