"""Functional coverage for the destructive MCP surface (previously registration-only).

Every governed lifecycle write tool is invoked twice against a mocked proxmoxer
connection (the ``test_new_ops.py`` style — MagicMock resource-path proxies):

  a. ``dry_run=True`` → NO API call is made and a ``dryRun`` preview comes back
     (and no undo descriptor is recorded);
  b. the real call → the expected proxmoxer method/path is hit with the right
     params.

Plus: risk tiers are asserted (delete / rollback / migrate / snapshot-delete =
high) and, where an undo callback exists, the inverse descriptor is built from
state captured off the mock — not guessed.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import proxmox_aiops.governance.audit as audit_mod
import proxmox_aiops.governance.policy as policy_mod
import proxmox_aiops.governance.undo as undo_mod
from mcp_server.tools import disk as disk_tools
from mcp_server.tools import lxc as lxc_tools
from mcp_server.tools import vm as vm_tools


@pytest.fixture(autouse=True)
def _gov_home(tmp_path, monkeypatch):
    """Isolate harness state (audit/undo/rules) in a throwaway home."""
    monkeypatch.setenv("PROXMOX_AIOPS_HOME", str(tmp_path))
    audit_mod.reset_engine()
    policy_mod.reset_policy_engine()
    undo_mod.reset_undo_store()
    yield
    audit_mod.reset_engine()
    policy_mod.reset_policy_engine()
    undo_mod.reset_undo_store()


@pytest.fixture
def undo_recorder(monkeypatch):
    """Capture undo descriptors the harness records."""
    recorded: list[dict] = []

    class _Store:
        def record(self, *, skill, tool, undo_descriptor, orig_params, effect_verified=True):
            recorded.append(undo_descriptor)
            return f"undo-{len(recorded)}"

    monkeypatch.setattr(undo_mod, "get_undo_store", lambda: _Store())
    return recorded


def _qemu_conn(vmid: int = 100) -> MagicMock:
    """A mocked connection whose node 'pve1' hosts QEMU VM ``vmid``."""
    conn = MagicMock(name="conn")
    conn.nodes.return_value.qemu.get.return_value = [{"vmid": vmid, "name": "web"}]
    return conn


def _lxc_conn(vmid: int = 200) -> MagicMock:
    """A mocked connection whose node 'pve1' hosts LXC container ``vmid``."""
    conn = MagicMock(name="conn")
    conn.nodes.return_value.lxc.get.return_value = [{"vmid": vmid, "name": "ct"}]
    return conn


def _wire(monkeypatch, module, conn) -> None:
    monkeypatch.setattr(module, "_get_connection", lambda target=None: conn)


def _vm_proxy(conn: MagicMock) -> MagicMock:
    """The ``conn.nodes(<node>).qemu(<vmid>)`` resource proxy."""
    return conn.nodes.return_value.qemu.return_value


def _ct_proxy(conn: MagicMock) -> MagicMock:
    return conn.nodes.return_value.lxc.return_value


# ─── risk tiers (line consistency: delete/rollback/migrate = high) ──────────


@pytest.mark.unit
def test_risk_tiers_of_lifecycle_writes():
    expected = {
        vm_tools.vm_delete: "high",
        vm_tools.vm_snapshot_rollback: "high",
        vm_tools.vm_migrate: "high",
        vm_tools.vm_snapshot_delete: "high",  # destroys a rollback point, no undo
        vm_tools.vm_stop: "medium",
        vm_tools.vm_shutdown: "medium",
        vm_tools.vm_clone: "medium",
        vm_tools.vm_snapshot_create: "medium",
        disk_tools.vm_resize_disk: "medium",
        lxc_tools.ct_start: "medium",
        lxc_tools.ct_stop: "medium",
    }
    for tool, risk in expected.items():
        assert tool._is_governed_tool is True, tool.__name__
        assert tool._risk_level == risk, tool.__name__


# ─── vm_stop ─────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_vm_stop_dry_run_makes_no_api_call(monkeypatch, undo_recorder):
    conn = _qemu_conn()
    _wire(monkeypatch, vm_tools, conn)
    out = vm_tools.vm_stop(vmid=100, dry_run=True, node="pve1")
    assert out["dryRun"] is True
    assert out["wouldStop"]["vmid"] == 100
    conn.nodes.assert_not_called()
    assert undo_recorder == []  # a preview must not record an undo


@pytest.mark.unit
def test_vm_stop_real_call_and_undo_inverse(monkeypatch, undo_recorder):
    conn = _qemu_conn()
    _vm_proxy(conn).status.stop.post.return_value = "UPID:stop"
    _wire(monkeypatch, vm_tools, conn)
    out = vm_tools.vm_stop(vmid=100, node="pve1")
    assert "error" not in out
    assert out["task"] == "UPID:stop"
    conn.nodes.return_value.qemu.assert_called_once_with(100)
    _vm_proxy(conn).status.stop.post.assert_called_once_with()
    assert undo_recorder[0]["tool"] == "vm_start"
    assert undo_recorder[0]["params"]["vmid"] == 100
    assert out.get("_undo_id") == "undo-1"


# ─── vm_shutdown ─────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_vm_shutdown_dry_run_makes_no_api_call(monkeypatch, undo_recorder):
    conn = _qemu_conn()
    _wire(monkeypatch, vm_tools, conn)
    out = vm_tools.vm_shutdown(vmid=100, dry_run=True, node="pve1")
    assert out["dryRun"] is True and out["wouldShutdown"]["vmid"] == 100
    conn.nodes.assert_not_called()
    assert undo_recorder == []


@pytest.mark.unit
def test_vm_shutdown_real_call_and_undo_inverse(monkeypatch, undo_recorder):
    conn = _qemu_conn()
    _vm_proxy(conn).status.shutdown.post.return_value = "UPID:shut"
    _wire(monkeypatch, vm_tools, conn)
    out = vm_tools.vm_shutdown(vmid=100, node="pve1")
    assert "error" not in out
    _vm_proxy(conn).status.shutdown.post.assert_called_once_with()
    assert undo_recorder[0]["tool"] == "vm_start"
    assert undo_recorder[0]["params"]["vmid"] == 100


# ─── vm_delete (high, irreversible) ──────────────────────────────────────────


@pytest.mark.unit
def test_vm_delete_dry_run_makes_no_api_call(monkeypatch):
    conn = _qemu_conn()
    _wire(monkeypatch, vm_tools, conn)
    out = vm_tools.vm_delete(vmid=100, dry_run=True, node="pve1")
    assert out["dryRun"] is True and out["wouldDelete"]["vmid"] == 100
    conn.nodes.assert_not_called()


@pytest.mark.unit
def test_vm_delete_real_call_hits_delete_endpoint(monkeypatch, undo_recorder):
    conn = _qemu_conn()
    _vm_proxy(conn).delete.return_value = "UPID:del"
    _wire(monkeypatch, vm_tools, conn)
    out = vm_tools.vm_delete(vmid=100, node="pve1")
    assert "error" not in out
    assert out["action"] == "delete"
    conn.nodes.return_value.qemu.assert_called_once_with(100)
    _vm_proxy(conn).delete.assert_called_once_with()
    assert undo_recorder == []  # irreversible: must record no undo


# ─── vm_migrate (high, undo = migrate back to CAPTURED source node) ─────────


@pytest.mark.unit
def test_vm_migrate_dry_run_makes_no_api_call(monkeypatch, undo_recorder):
    conn = _qemu_conn()
    _wire(monkeypatch, vm_tools, conn)
    out = vm_tools.vm_migrate(vmid=100, target_node="pve2", dry_run=True, node="pve1")
    assert out["dryRun"] is True
    assert out["wouldMigrate"] == {"vmid": 100, "target_node": "pve2", "online": True}
    conn.nodes.assert_not_called()
    assert undo_recorder == []


@pytest.mark.unit
def test_vm_migrate_real_call_and_undo_returns_to_captured_source(monkeypatch, undo_recorder):
    conn = _qemu_conn()
    _vm_proxy(conn).migrate.post.return_value = "UPID:mig"
    _wire(monkeypatch, vm_tools, conn)
    out = vm_tools.vm_migrate(vmid=100, target_node="pve2", online=False, node="pve1")
    assert "error" not in out
    _vm_proxy(conn).migrate.post.assert_called_once_with(target="pve2", online=0)
    assert out["from_node"] == "pve1" and out["to_node"] == "pve2"
    # Undo must migrate back to the source node captured from the mock lookup.
    d = undo_recorder[0]
    assert d["tool"] == "vm_migrate"
    assert d["params"]["target_node"] == "pve1"
    assert d["params"]["node"] == "pve2"


# ─── vm_clone (undo deletes the freshly-cloned vmid from the result) ────────


@pytest.mark.unit
def test_vm_clone_dry_run_makes_no_api_call(monkeypatch, undo_recorder):
    conn = _qemu_conn()
    _wire(monkeypatch, vm_tools, conn)
    out = vm_tools.vm_clone(vmid=100, newid=101, dry_run=True, node="pve1")
    assert out["dryRun"] is True and out["wouldClone"]["newid"] == 101
    conn.nodes.assert_not_called()
    assert undo_recorder == []


@pytest.mark.unit
def test_vm_clone_real_call_and_undo_deletes_new_vmid(monkeypatch, undo_recorder):
    conn = _qemu_conn()
    _vm_proxy(conn).clone.post.return_value = "UPID:clone"
    _wire(monkeypatch, vm_tools, conn)
    out = vm_tools.vm_clone(vmid=100, newid=101, name="web-copy", node="pve1")
    assert "error" not in out
    _vm_proxy(conn).clone.post.assert_called_once_with(newid=101, name="web-copy")
    d = undo_recorder[0]
    assert d["tool"] == "vm_delete"
    assert d["params"]["vmid"] == 101  # the clone, never the source


# ─── snapshots ───────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_vm_snapshot_create_dry_run_makes_no_api_call(monkeypatch, undo_recorder):
    conn = _qemu_conn()
    _wire(monkeypatch, vm_tools, conn)
    out = vm_tools.vm_snapshot_create(vmid=100, name="pre-change", dry_run=True, node="pve1")
    assert out["dryRun"] is True and out["wouldSnapshot"]["name"] == "pre-change"
    conn.nodes.assert_not_called()
    assert undo_recorder == []


@pytest.mark.unit
def test_vm_snapshot_create_real_call_and_undo_deletes_it(monkeypatch, undo_recorder):
    conn = _qemu_conn()
    _vm_proxy(conn).snapshot.post.return_value = "UPID:snap"
    _wire(monkeypatch, vm_tools, conn)
    out = vm_tools.vm_snapshot_create(vmid=100, name="pre-change", node="pve1")
    assert "error" not in out
    _vm_proxy(conn).snapshot.post.assert_called_once_with(snapname="pre-change")
    d = undo_recorder[0]
    assert d["tool"] == "vm_snapshot_delete"
    assert d["params"] == {"vmid": 100, "name": "pre-change", "node": "pve1"}


@pytest.mark.unit
def test_vm_snapshot_delete_dry_run_makes_no_api_call(monkeypatch):
    conn = _qemu_conn()
    _wire(monkeypatch, vm_tools, conn)
    out = vm_tools.vm_snapshot_delete(vmid=100, name="old", dry_run=True, node="pve1")
    assert out["dryRun"] is True and out["wouldDeleteSnapshot"]["name"] == "old"
    conn.nodes.assert_not_called()


@pytest.mark.unit
def test_vm_snapshot_delete_real_call_hits_snapshot_delete(monkeypatch, undo_recorder):
    conn = _qemu_conn()
    _vm_proxy(conn).snapshot.return_value.delete.return_value = "UPID:sdel"
    _wire(monkeypatch, vm_tools, conn)
    out = vm_tools.vm_snapshot_delete(vmid=100, name="old", node="pve1")
    assert "error" not in out
    _vm_proxy(conn).snapshot.assert_called_once_with("old")
    _vm_proxy(conn).snapshot.return_value.delete.assert_called_once_with()
    assert undo_recorder == []  # destroys a rollback point: no undo


@pytest.mark.unit
def test_vm_snapshot_rollback_dry_run_makes_no_api_call(monkeypatch):
    conn = _qemu_conn()
    _wire(monkeypatch, vm_tools, conn)
    out = vm_tools.vm_snapshot_rollback(vmid=100, name="golden", dry_run=True, node="pve1")
    assert out["dryRun"] is True and out["wouldRollback"]["name"] == "golden"
    conn.nodes.assert_not_called()


@pytest.mark.unit
def test_vm_snapshot_rollback_real_call_hits_rollback_endpoint(monkeypatch, undo_recorder):
    conn = _qemu_conn()
    _vm_proxy(conn).snapshot.return_value.rollback.post.return_value = "UPID:rb"
    _wire(monkeypatch, vm_tools, conn)
    out = vm_tools.vm_snapshot_rollback(vmid=100, name="golden", node="pve1")
    assert "error" not in out
    _vm_proxy(conn).snapshot.assert_called_once_with("golden")
    _vm_proxy(conn).snapshot.return_value.rollback.post.assert_called_once_with()
    assert undo_recorder == []  # discarded state cannot be recovered


# ─── vm_resize_disk (grow-only, irreversible) ────────────────────────────────


@pytest.mark.unit
def test_vm_resize_disk_dry_run_makes_no_api_call(monkeypatch):
    conn = _qemu_conn()
    _wire(monkeypatch, disk_tools, conn)
    out = disk_tools.vm_resize_disk(vmid=100, disk="scsi0", size="+10G", dry_run=True, node="pve1")
    assert out["dryRun"] is True
    assert out["wouldResize"] == {"vmid": 100, "disk": "scsi0", "size": "+10G"}
    conn.nodes.assert_not_called()


@pytest.mark.unit
def test_vm_resize_disk_real_call_hits_resize_put(monkeypatch):
    conn = _qemu_conn()
    _wire(monkeypatch, disk_tools, conn)
    out = disk_tools.vm_resize_disk(vmid=100, disk="scsi0", size="+10G", node="pve1")
    assert "error" not in out
    assert out["action"] == "vm_resize_disk"
    _vm_proxy(conn).resize.put.assert_called_once_with(disk="scsi0", size="+10G")


# ─── LXC containers ──────────────────────────────────────────────────────────


@pytest.mark.unit
def test_ct_start_dry_run_makes_no_api_call(monkeypatch, undo_recorder):
    conn = _lxc_conn()
    _wire(monkeypatch, lxc_tools, conn)
    out = lxc_tools.ct_start(vmid=200, dry_run=True, node="pve1")
    assert out["dryRun"] is True and out["wouldStart"]["vmid"] == 200
    conn.nodes.assert_not_called()
    assert undo_recorder == []


@pytest.mark.unit
def test_ct_start_real_call_and_undo_inverse(monkeypatch, undo_recorder):
    conn = _lxc_conn()
    _ct_proxy(conn).status.start.post.return_value = "UPID:ctstart"
    _wire(monkeypatch, lxc_tools, conn)
    out = lxc_tools.ct_start(vmid=200, node="pve1")
    assert "error" not in out
    conn.nodes.return_value.lxc.assert_called_once_with(200)
    _ct_proxy(conn).status.start.post.assert_called_once_with()
    assert undo_recorder[0]["tool"] == "ct_stop"
    assert undo_recorder[0]["params"]["vmid"] == 200


@pytest.mark.unit
def test_ct_stop_dry_run_makes_no_api_call(monkeypatch, undo_recorder):
    conn = _lxc_conn()
    _wire(monkeypatch, lxc_tools, conn)
    out = lxc_tools.ct_stop(vmid=200, dry_run=True, node="pve1")
    assert out["dryRun"] is True and out["wouldStop"]["vmid"] == 200
    conn.nodes.assert_not_called()
    assert undo_recorder == []


@pytest.mark.unit
def test_ct_stop_real_call_and_undo_inverse(monkeypatch, undo_recorder):
    conn = _lxc_conn()
    _ct_proxy(conn).status.stop.post.return_value = "UPID:ctstop"
    _wire(monkeypatch, lxc_tools, conn)
    out = lxc_tools.ct_stop(vmid=200, node="pve1")
    assert "error" not in out
    _ct_proxy(conn).status.stop.post.assert_called_once_with()
    assert undo_recorder[0]["tool"] == "ct_start"
    assert undo_recorder[0]["params"]["vmid"] == 200
