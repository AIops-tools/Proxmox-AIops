"""CLI confirmed-write path — past dry-run, through governance, onto disk.

The CLI write commands delegate real execution to the ``@governed_tool``
functions in ``mcp_server.tools``. These tests drive a write command PAST the
dry-run branch and the double-confirm prompts and assert the call really went
through the governed path (audit row on disk) — the regression test for the
"CLI writes were unaudited" line-wide fix.
"""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

import pytest
from conftest import assert_no_mutating_call
from typer.testing import CliRunner

import proxmox_aiops.governance.audit as audit_mod
import proxmox_aiops.governance.policy as policy_mod
import proxmox_aiops.governance.undo as undo_mod


@pytest.fixture
def gov_home(tmp_path, monkeypatch):
    monkeypatch.setenv("PROXMOX_AIOPS_HOME", str(tmp_path))
    audit_mod.reset_engine()
    policy_mod.reset_policy_engine()
    undo_mod.reset_undo_store()
    yield tmp_path
    audit_mod.reset_engine()
    policy_mod.reset_policy_engine()
    undo_mod.reset_undo_store()


def _audit_tools(db_path) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        return [r[0] for r in conn.execute("SELECT tool FROM audit_log ORDER BY id")]
    finally:
        conn.close()


def _mock_vm_conn() -> MagicMock:
    conn = MagicMock(name="conn")
    conn.nodes.get.return_value = [{"node": "pve1"}]  # cluster node scan
    conn.nodes.return_value.qemu.get.return_value = [{"vmid": 100, "name": "web"}]
    conn.nodes.return_value.qemu.return_value.status.stop.post.return_value = "UPID:stop"
    return conn


@pytest.mark.unit
def test_cli_vm_stop_dry_run_writes_nothing_but_is_audited(gov_home, monkeypatch):
    """A preview may read; it must never write — and it IS audited.

    The CLI dry-run branch now calls the governed twin with dry_run=True instead
    of printing a hardcoded string, so the preview runs the same guards the real
    write would and leaves the same audit trail. The surviving prohibition is
    narrower than the old 'no call, no audit': no MUTATING verb may be issued.
    """
    import mcp_server.tools.vm as gov_vm
    from proxmox_aiops.cli import app

    conn = _mock_vm_conn()
    monkeypatch.setattr(gov_vm, "_get_connection", lambda target=None: conn)
    result = CliRunner().invoke(app, ["vm", "stop", "100", "--dry-run"])
    assert result.exit_code == 0
    assert "DRY-RUN" in result.output
    assert_no_mutating_call(conn)
    assert _audit_tools(gov_home / "audit.db") == ["vm_stop"]


@pytest.mark.unit
def test_cli_vm_stop_confirmed_goes_through_governance(gov_home, monkeypatch):
    """Confirmed CLI write must execute via the governed twin: the API call runs
    AND an audit row lands in audit.db (this is what the reroute fix bought)."""
    import mcp_server.tools.vm as gov_vm
    from proxmox_aiops.cli import app

    conn = _mock_vm_conn()
    monkeypatch.setattr(gov_vm, "_get_connection", lambda target=None: conn)
    result = CliRunner().invoke(app, ["vm", "stop", "100"], input="y\ny\n")
    assert result.exit_code == 0, result.output
    conn.nodes.return_value.qemu.return_value.status.stop.post.assert_called_once_with()
    assert _audit_tools(gov_home / "audit.db") == ["vm_stop"]


@pytest.mark.unit
def test_cli_vm_stop_aborts_without_double_confirm(gov_home, monkeypatch):
    import mcp_server.tools.vm as gov_vm
    from proxmox_aiops.cli import app

    conn = _mock_vm_conn()
    monkeypatch.setattr(gov_vm, "_get_connection", lambda target=None: conn)
    result = CliRunner().invoke(app, ["vm", "stop", "100"], input="y\nn\n")
    assert result.exit_code != 0
    conn.nodes.assert_not_called()
    assert not (gov_home / "audit.db").exists()
