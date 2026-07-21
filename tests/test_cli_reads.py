"""CLI read-command tests (no live PVE).

These drive the Typer read commands through ``CliRunner``, patching the
module-local ``get_connection`` with a mocked proxmoxer conn. They assert the
command exits 0, renders expected values, and that known teaching errors are
translated to one red line + exit code 1 (the ``cli_errors`` wrapper).
"""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest
from conftest import assert_no_mutating_call
from typer.testing import CliRunner

from proxmox_aiops.cli import app

runner = CliRunner()


def _audit_tools(home) -> list[str]:
    """Tool names recorded in the audit log under ``home`` (empty if none)."""
    db = home / "audit.db"
    if not db.exists():
        return []
    conn = sqlite3.connect(db)
    try:
        return [r[0] for r in conn.execute("SELECT tool FROM audit_log ORDER BY id")]
    finally:
        conn.close()


def _patch_conn(monkeypatch, module_path: str, conn: MagicMock) -> None:
    """Patch get_connection in the given cli sub-module to yield (conn, cfg)."""
    import importlib

    mod = importlib.import_module(module_path)
    monkeypatch.setattr(mod, "get_connection", lambda target=None: (conn, object()))


# ─── cluster ─────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_cli_cluster_nodes(monkeypatch):
    conn = MagicMock()
    conn.nodes.get.return_value = [
        {"node": "pve1", "status": "online", "cpu": 0.1, "maxcpu": 8,
         "mem": 40, "maxmem": 100, "uptime": 1000},
    ]
    _patch_conn(monkeypatch, "proxmox_aiops.cli.cluster", conn)
    result = runner.invoke(app, ["cluster", "nodes"])
    assert result.exit_code == 0, result.output
    assert "pve1" in result.output


@pytest.mark.unit
def test_cli_cluster_status(monkeypatch):
    conn = MagicMock()
    conn.cluster.status.get.return_value = [
        {"type": "cluster", "name": "prod", "quorate": 1},
    ]
    _patch_conn(monkeypatch, "proxmox_aiops.cli.cluster", conn)
    result = runner.invoke(app, ["cluster", "status"])
    assert result.exit_code == 0, result.output
    assert "prod" in result.output


@pytest.mark.unit
def test_cli_cluster_resources(monkeypatch):
    conn = MagicMock()
    conn.cluster.resources.get.return_value = [
        {"id": "qemu/100", "type": "qemu", "name": "web", "node": "pve1",
         "status": "running", "vmid": 100},
    ]
    _patch_conn(monkeypatch, "proxmox_aiops.cli.cluster", conn)
    result = runner.invoke(app, ["cluster", "resources", "--type", "vm"])
    assert result.exit_code == 0, result.output
    conn.cluster.resources.get.assert_called_once_with(type="vm")


@pytest.mark.unit
def test_cli_cluster_node_status(monkeypatch):
    conn = MagicMock()
    conn.nodes.return_value.status.get.return_value = {
        "uptime": 5, "memory": {"total": 10, "used": 4, "free": 6},
    }
    _patch_conn(monkeypatch, "proxmox_aiops.cli.cluster", conn)
    result = runner.invoke(app, ["cluster", "node-status", "pve1"])
    assert result.exit_code == 0, result.output
    assert "mem_total" in result.output


@pytest.mark.unit
def test_cli_cluster_task_status_bad_upid_is_teaching_error(monkeypatch):
    conn = MagicMock()
    _patch_conn(monkeypatch, "proxmox_aiops.cli.cluster", conn)
    result = runner.invoke(app, ["cluster", "task-status", "garbage"])
    assert result.exit_code == 1
    assert "Error:" in result.output
    assert "Could not determine node" in result.output


@pytest.mark.unit
def test_cli_cluster_task_log(monkeypatch):
    conn = MagicMock()
    conn.nodes.return_value.tasks.return_value.log.get.return_value = [
        {"n": 1, "t": "started"},
    ]
    _patch_conn(monkeypatch, "proxmox_aiops.cli.cluster", conn)
    result = runner.invoke(app, ["cluster", "task-log", "UPID:pve1:a:b", "--limit", "5"])
    assert result.exit_code == 0, result.output
    assert "started" in result.output


@pytest.mark.unit
def test_cli_cluster_next_vmid(monkeypatch):
    conn = MagicMock()
    conn.cluster.nextid.get.return_value = "123"
    _patch_conn(monkeypatch, "proxmox_aiops.cli.cluster", conn)
    result = runner.invoke(app, ["cluster", "next-vmid"])
    assert result.exit_code == 0, result.output
    assert "123" in result.output


# ─── storage ─────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_cli_storage_list(monkeypatch):
    conn = MagicMock()
    conn.nodes.return_value.storage.get.return_value = [
        {"storage": "local-lvm", "type": "lvmthin", "active": 1,
         "total": 100, "used": 40, "avail": 60},
    ]
    _patch_conn(monkeypatch, "proxmox_aiops.cli.storage", conn)
    result = runner.invoke(app, ["storage", "list", "--node", "pve1"])
    assert result.exit_code == 0, result.output
    assert "local-lvm" in result.output


@pytest.mark.unit
def test_cli_storage_list_without_node_teaching_error(monkeypatch):
    conn = MagicMock()
    _patch_conn(monkeypatch, "proxmox_aiops.cli.storage", conn)
    result = runner.invoke(app, ["storage", "list"])
    assert result.exit_code == 1
    assert "No node specified" in result.output


@pytest.mark.unit
def test_cli_storage_content(monkeypatch):
    conn = MagicMock()
    conn.nodes.return_value.storage.return_value.content.get.return_value = [
        {"volid": "local:iso/x.iso", "content": "iso", "format": "iso",
         "size": 700, "vmid": None},
    ]
    _patch_conn(monkeypatch, "proxmox_aiops.cli.storage", conn)
    result = runner.invoke(
        app, ["storage", "content", "local", "--content", "iso", "--node", "pve1"]
    )
    assert result.exit_code == 0, result.output
    conn.nodes.return_value.storage.return_value.content.get.assert_called_once_with(
        content="iso"
    )


# ─── pool ────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_cli_pool_list(monkeypatch):
    conn = MagicMock()
    conn.pools.get.return_value = [{"poolid": "prod", "comment": "Production"}]
    _patch_conn(monkeypatch, "proxmox_aiops.cli.pool", conn)
    result = runner.invoke(app, ["pool", "list"])
    assert result.exit_code == 0, result.output
    assert "prod" in result.output


@pytest.mark.unit
def test_cli_pool_members(monkeypatch):
    conn = MagicMock()
    conn.pools.return_value.get.return_value = {
        "comment": "Production",
        "members": [{"id": "qemu/100", "type": "qemu", "vmid": 100,
                     "node": "pve1", "status": "running"}],
    }
    _patch_conn(monkeypatch, "proxmox_aiops.cli.pool", conn)
    result = runner.invoke(app, ["pool", "members", "prod"])
    assert result.exit_code == 0, result.output
    assert "qemu/100" in result.output


# ─── ha ──────────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_cli_ha_status_not_configured(monkeypatch):
    conn = MagicMock()
    conn.cluster.ha.status.current.get.side_effect = Exception("404 not found")
    _patch_conn(monkeypatch, "proxmox_aiops.cli.ha", conn)
    result = runner.invoke(app, ["ha", "status"])
    assert result.exit_code == 0, result.output
    assert "not configured" in result.output.lower()


@pytest.mark.unit
def test_cli_ha_status_configured(monkeypatch):
    conn = MagicMock()
    conn.cluster.ha.status.current.get.return_value = [
        {"id": "vm:100", "type": "service", "node": "pve1", "status": "started"},
    ]
    _patch_conn(monkeypatch, "proxmox_aiops.cli.ha", conn)
    result = runner.invoke(app, ["ha", "status"])
    assert result.exit_code == 0, result.output
    assert "vm:100" in result.output


@pytest.mark.unit
def test_cli_ha_resources_empty(monkeypatch):
    conn = MagicMock()
    conn.cluster.ha.resources.get.side_effect = Exception("404 not found")
    _patch_conn(monkeypatch, "proxmox_aiops.cli.ha", conn)
    result = runner.invoke(app, ["ha", "resources"])
    assert result.exit_code == 0, result.output
    assert "No HA resources" in result.output


# ─── firewall ────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_cli_firewall_vm_rules(monkeypatch):
    conn = MagicMock()
    conn.nodes.return_value.qemu.get.return_value = [{"vmid": 100}]
    conn.nodes.return_value.qemu.return_value.firewall.rules.get.return_value = [
        {"pos": 0, "type": "in", "action": "ACCEPT", "proto": "tcp",
         "dport": "22", "source": "", "dest": "", "enable": 1},
    ]
    _patch_conn(monkeypatch, "proxmox_aiops.cli.firewall", conn)
    result = runner.invoke(app, ["firewall", "vm-rules", "100", "--node", "pve1"])
    assert result.exit_code == 0, result.output
    assert "ACCEPT" in result.output


@pytest.mark.unit
def test_cli_firewall_cluster_status(monkeypatch):
    conn = MagicMock()
    conn.cluster.firewall.options.get.return_value = {
        "enable": 1, "policy_in": "DROP", "policy_out": "ACCEPT",
    }
    _patch_conn(monkeypatch, "proxmox_aiops.cli.firewall", conn)
    result = runner.invoke(app, ["firewall", "cluster-status"])
    assert result.exit_code == 0, result.output
    assert "DROP" in result.output


# ─── lxc + backup read commands ──────────────────────────────────────────────


@pytest.mark.unit
def test_cli_ct_list(monkeypatch):
    conn = MagicMock()
    conn.nodes.return_value.lxc.get.return_value = [
        {"vmid": 200, "name": "web", "status": "running", "cpus": 2, "maxmem": 512},
    ]
    _patch_conn(monkeypatch, "proxmox_aiops.cli.lxc", conn)
    result = runner.invoke(app, ["ct", "list", "--node", "pve1"])
    assert result.exit_code == 0, result.output
    assert "web" in result.output


@pytest.mark.unit
def test_cli_backup_list(monkeypatch):
    conn = MagicMock()
    conn.nodes.return_value.storage.return_value.content.get.return_value = [
        {"volid": "s:backup/a.zst", "vmid": 100, "size": 10, "format": "zst",
         "ctime": 1700000000, "notes": ""},
    ]
    _patch_conn(monkeypatch, "proxmox_aiops.cli.backup", conn)
    result = runner.invoke(app, ["backup", "list", "store", "--node", "pve1"])
    assert result.exit_code == 0, result.output
    assert "s:backup/a.zst" in result.output


@pytest.mark.unit
def test_cli_backup_restore_dry_run_no_execute(monkeypatch, tmp_path):
    """backup_restore's twin takes no dry_run parameter, so this preview is NOT
    routed through governance: it mutates nothing, but it also cannot see the
    guards the real restore would hit, and leaves no audit row. The audit
    assertion pins the gap so it is noticed if the twin ever gains dry_run."""
    conn = MagicMock()
    _patch_conn(monkeypatch, "proxmox_aiops.cli.backup", conn)
    result = runner.invoke(
        app,
        ["backup", "restore", "101", "--archive", "s:backup/a.zst",
         "--storage", "local", "--dry-run"],
    )
    assert result.exit_code == 0, result.output
    assert "DRY-RUN" in result.output
    assert_no_mutating_call(conn)
    assert not (tmp_path / "audit.db").exists()


@pytest.mark.unit
def test_cli_ct_stop_dry_run_writes_nothing_but_is_audited(monkeypatch, tmp_path):
    """The rerouted container preview: governed, audited, mutates nothing."""
    import mcp_server.tools.lxc as lxc_tools

    conn = MagicMock()
    conn.nodes.return_value.lxc.get.return_value = [{"vmid": 200, "name": "ct"}]
    _patch_conn(monkeypatch, "proxmox_aiops.cli.lxc", conn)
    monkeypatch.setattr(lxc_tools, "_get_connection", lambda target=None: conn)
    result = runner.invoke(app, ["ct", "stop", "200", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "DRY-RUN" in result.output
    assert_no_mutating_call(conn)
    assert _audit_tools(tmp_path) == ["ct_stop"]
