"""CLI tests for ``proxmox-aiops vm ...`` read commands and write dry-run
previews (no live PVE). Read commands patch the module-local ``get_connection``;
dry-run previews are routed through the governed twin with ``dry_run=True``, so
they are audited like any other governed call and must issue no mutating verb.
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


def _patch_conn(monkeypatch, conn: MagicMock) -> None:
    import proxmox_aiops.cli.vm as vm_cli

    monkeypatch.setattr(vm_cli, "get_connection", lambda target=None: (conn, object()))


def _conn_one_vm(vmid: int = 100) -> MagicMock:
    conn = MagicMock()
    conn.nodes.return_value.qemu.get.return_value = [{"vmid": vmid, "name": "web"}]
    return conn


# ─── read commands ───────────────────────────────────────────────────────────


@pytest.mark.unit
def test_vm_list(monkeypatch):
    conn = MagicMock()
    conn.nodes.return_value.qemu.get.return_value = [
        {"vmid": 100, "name": "web", "status": "running", "cpus": 2, "maxmem": 1024},
    ]
    # scan needs a node; use default node via cluster scan fallback
    conn.nodes.get.return_value = [{"node": "pve1"}]
    _patch_conn(monkeypatch, conn)
    result = runner.invoke(app, ["vm", "list", "--node", "pve1"])
    assert result.exit_code == 0, result.output
    assert "web" in result.output


@pytest.mark.unit
def test_vm_get(monkeypatch):
    conn = _conn_one_vm()
    conn.nodes.return_value.qemu.return_value.status.current.get.return_value = {
        "name": "web", "status": "running", "cpus": 2, "maxmem": 1024, "uptime": 999,
    }
    _patch_conn(monkeypatch, conn)
    result = runner.invoke(app, ["vm", "get", "100", "--node", "pve1"])
    assert result.exit_code == 0, result.output
    assert "running" in result.output


@pytest.mark.unit
def test_vm_get_missing_is_teaching_error(monkeypatch):
    conn = MagicMock()
    conn.nodes.return_value.qemu.get.return_value = []  # not found on node
    _patch_conn(monkeypatch, conn)
    result = runner.invoke(app, ["vm", "get", "999", "--node", "pve1"])
    assert result.exit_code == 1
    assert "not found" in result.output.lower()


@pytest.mark.unit
def test_vm_config(monkeypatch):
    conn = _conn_one_vm()
    conn.nodes.return_value.qemu.return_value.config.get.return_value = {
        "cores": 4, "memory": 2048, "ostype": "l26", "boot": "order=scsi0",
    }
    _patch_conn(monkeypatch, conn)
    result = runner.invoke(app, ["vm", "config", "100", "--node", "pve1"])
    assert result.exit_code == 0, result.output
    assert "cores" in result.output


@pytest.mark.unit
def test_vm_snapshot_list(monkeypatch):
    conn = _conn_one_vm()
    conn.nodes.return_value.qemu.return_value.snapshot.get.return_value = [
        {"name": "pre-upgrade", "description": "before patch"},
    ]
    _patch_conn(monkeypatch, conn)
    result = runner.invoke(app, ["vm", "snapshot-list", "100", "--node", "pve1"])
    assert result.exit_code == 0, result.output
    assert "pre-upgrade" in result.output


@pytest.mark.unit
def test_vm_agent_ping_not_responding(monkeypatch):
    conn = _conn_one_vm()
    conn.nodes.return_value.qemu.return_value.agent.ping.post.side_effect = Exception(
        "QEMU guest agent is not running"
    )
    _patch_conn(monkeypatch, conn)
    result = runner.invoke(app, ["vm", "agent-ping", "100", "--node", "pve1"])
    assert result.exit_code == 0, result.output
    assert "not responding" in result.output


# ─── write dry-run previews ──────────────────────────────────────────────────


def _patch_governed_conn(monkeypatch, conn: MagicMock) -> None:
    """Put the mock on the GOVERNED path too.

    The rerouted dry-run branches call the twins in ``mcp_server.tools``, which
    resolve their connection through ``mcp_server._shared._get_connection`` —
    not the CLI module's ``get_connection``. Patching only the latter would make
    every no-mutation assertion below vacuously true.
    """
    import mcp_server.tools.disk as disk_tools
    import mcp_server.tools.vm as vm_tools

    for mod in (vm_tools, disk_tools):
        monkeypatch.setattr(mod, "_get_connection", lambda target=None: conn)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("argv", "audited_as"),
    [
        (["vm", "stop", "100", "--dry-run"], "vm_stop"),
        (["vm", "shutdown", "100", "--dry-run"], "vm_shutdown"),
        (["vm", "delete", "100", "--dry-run"], "vm_delete"),
        (["vm", "snapshot-delete", "100", "--name", "s1", "--dry-run"], "vm_snapshot_delete"),
        (["vm", "snapshot-rollback", "100", "--name", "s1", "--dry-run"],
         "vm_snapshot_rollback"),
        (["vm", "migrate", "100", "--to-node", "pve2", "--dry-run"], "vm_migrate"),
        (["vm", "resize-disk", "100", "--disk", "scsi0", "--size", "+10G", "--dry-run"],
         "vm_resize_disk"),
        # reconfigure / move-disk now route through the governed twin too: their
        # previews READ the VM's current config (cores/memory, disk placement)
        # through the guarded path and are audited like the rest — no longer the
        # old hardcoded, unaudited banner.
        (["vm", "reconfigure", "100", "--cores", "4", "--dry-run"], "vm_reconfigure"),
        (["vm", "move-disk", "100", "--disk", "scsi0", "--storage", "ceph", "--dry-run"],
         "vm_move_disk"),
    ],
)
def test_vm_write_dry_run_previews(monkeypatch, tmp_path, argv, audited_as):
    """A preview renders, mutates nothing, and — being routed — is audited."""
    conn = MagicMock()
    # Enough shape for the read-backed previews (reconfigure / move-disk) to
    # locate the VM and read its config; harmless for the previews that do not.
    conn.nodes.get.return_value = [{"node": "pve1"}]
    conn.nodes.return_value.qemu.get.return_value = [{"vmid": 100, "name": "web"}]
    conn.nodes.return_value.qemu.return_value.config.get.return_value = {
        "cores": 2, "memory": 2048, "scsi0": "local:vm-100-disk-0,size=32G",
    }
    _patch_conn(monkeypatch, conn)
    _patch_governed_conn(monkeypatch, conn)
    result = runner.invoke(app, argv)
    assert result.exit_code == 0, result.output
    assert "DRY-RUN" in result.output
    assert_no_mutating_call(conn)
    assert _audit_tools(tmp_path) == [audited_as]
