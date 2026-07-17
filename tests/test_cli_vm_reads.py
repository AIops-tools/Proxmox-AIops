"""CLI tests for ``proxmox-aiops vm ...`` read commands and write dry-run
previews (no live PVE). Read commands patch the module-local ``get_connection``;
dry-run previews take the early branch and never touch a connection.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from proxmox_aiops.cli import app

runner = CliRunner()


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


# ─── write dry-run previews (no connection touched) ──────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize(
    "argv",
    [
        ["vm", "stop", "100", "--dry-run"],
        ["vm", "shutdown", "100", "--dry-run"],
        ["vm", "delete", "100", "--dry-run"],
        ["vm", "snapshot-delete", "100", "--name", "s1", "--dry-run"],
        ["vm", "snapshot-rollback", "100", "--name", "s1", "--dry-run"],
        ["vm", "reconfigure", "100", "--cores", "4", "--dry-run"],
        ["vm", "migrate", "100", "--to-node", "pve2", "--dry-run"],
        ["vm", "resize-disk", "100", "--disk", "scsi0", "--size", "+10G", "--dry-run"],
        ["vm", "move-disk", "100", "--disk", "scsi0", "--storage", "ceph", "--dry-run"],
    ],
)
def test_vm_write_dry_run_previews(monkeypatch, argv):
    conn = MagicMock()
    _patch_conn(monkeypatch, conn)
    result = runner.invoke(app, argv)
    assert result.exit_code == 0, result.output
    assert "DRY-RUN" in result.output
    conn.nodes.assert_not_called()
