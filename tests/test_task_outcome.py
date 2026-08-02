"""Proxmox writes are asynchronous — a UPID is not an outcome.

Regression suite for a defect found against a real Proxmox VE 8.4.19 node on
2026-08-02. ``POST .../status/start`` answers 200 with a task UPID *before* the
operation runs, and the tool treated that as success. In one live session three
operations that FAILED on the node — a start that died with ``QEMU exited with
code 1``, a shutdown that ended in ``VM quit/powerdown failed - got timeout``,
and a backup that ended in ``job errors`` — were each recorded ``status=ok``
with an undo token flagged ``effect_verified=1``. The audit, which is this
tool's central promise, was asserting state changes that never happened.

These tests pin the three outcomes and, more importantly, what each one must do
to the audit row and the undo token. The mock suite could not have caught the
original bug because its fixtures modelled a synchronous Proxmox that does not
exist; the fixtures now model the task endpoint, so an outcome must be declared.
"""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import MagicMock

import pytest
from conftest import mock_task

import proxmox_aiops.governance.audit as audit_mod
import proxmox_aiops.governance.policy as policy_mod
import proxmox_aiops.governance.undo as undo_mod
from proxmox_aiops.ops._task import (
    FAILED,
    OK,
    UNDETERMINED,
    TaskFailed,
    settle,
    wait_for_task,
)

_UPID = "UPID:pve1:00000760:00008483:6A6E964C:qmstart:900:root@pam!aiops:"


@pytest.fixture(autouse=True)
def _instant(monkeypatch):
    """Never sleep: read the task status once and classify it."""
    monkeypatch.setenv("PROXMOX_TASK_WAIT_SECONDS", "0")


def _conn(status: dict | None = None, *, raises: bool = False) -> MagicMock:
    conn = MagicMock(name="conn")
    getter = conn.nodes.return_value.tasks.return_value.status.get
    if raises:
        getter.side_effect = RuntimeError("connection reset while polling")
    else:
        getter.return_value = status
    return conn


# ─── the three verdicts ─────────────────────────────────────────────────────


@pytest.mark.unit
def test_finished_task_with_exitstatus_ok_is_confirmed():
    verdict, _ = wait_for_task(_conn({"status": "stopped", "exitstatus": "OK"}), _UPID)
    assert verdict == OK


@pytest.mark.unit
def test_finished_task_with_a_non_ok_exitstatus_is_a_failure():
    """The exact shape of the live defect: PVE accepted the request, then the
    task died. Anything other than 'OK' is a failure, not a success."""
    conn = _conn({"status": "stopped",
                  "exitstatus": "start failed: QEMU exited with code 1"})
    verdict, detail = wait_for_task(conn, _UPID)
    assert verdict == FAILED
    assert "QEMU exited with code 1" in detail


@pytest.mark.unit
def test_still_running_task_is_undetermined_not_ok():
    verdict, detail = wait_for_task(_conn({"status": "running"}), _UPID)
    assert verdict == UNDETERMINED
    assert "still running" in detail


@pytest.mark.unit
def test_unreadable_task_status_is_undetermined_never_ok():
    """A failed probe must never look like success — the 'failure disguised as
    health' shape this line treats as a bug class in its own right."""
    verdict, _ = wait_for_task(_conn(raises=True), _UPID)
    assert verdict == UNDETERMINED


@pytest.mark.unit
def test_finished_task_without_an_exitstatus_is_undetermined():
    """The node never actually said it succeeded, so we must not say so."""
    verdict, _ = wait_for_task(_conn({"status": "stopped"}), _UPID)
    assert verdict == UNDETERMINED


@pytest.mark.unit
def test_unparseable_upid_is_undetermined_not_a_crash():
    verdict, detail = wait_for_task(_conn({"status": "stopped", "exitstatus": "OK"}),
                                    "not-a-upid")
    assert verdict == UNDETERMINED
    assert "node" in detail


# ─── settle(): what each verdict does to the caller ─────────────────────────


@pytest.mark.unit
def test_settle_returns_the_result_untouched_on_success():
    out = settle(_conn({"status": "stopped", "exitstatus": "OK"}),
                 {"vmid": 900, "action": "start"}, upid=_UPID)
    assert out["vmid"] == 900 and out["taskStatus"] == OK
    assert "outcomeUnknown" not in out


@pytest.mark.unit
def test_settle_raises_on_a_failed_task_so_the_audit_records_an_error():
    conn = _conn({"status": "stopped", "exitstatus": "job errors"})
    with pytest.raises(TaskFailed, match="job errors"):
        settle(conn, {"vmid": 900, "action": "vm_backup"}, upid=_UPID)


@pytest.mark.unit
def test_settle_marks_an_unfinished_task_unknown():
    out = settle(_conn({"status": "running"}), {"vmid": 900}, upid=_UPID)
    assert out["outcomeUnknown"] is True
    assert out["taskStatus"] == UNDETERMINED


@pytest.mark.unit
def test_settle_does_not_mutate_the_result_it_was_given():
    original = {"vmid": 900, "action": "start"}
    settle(_conn({"status": "stopped", "exitstatus": "OK"}), original, upid=_UPID)
    assert original == {"vmid": 900, "action": "start"}


@pytest.mark.unit
def test_a_synchronous_write_with_no_upid_is_confirmed_by_its_2xx():
    """An offline config edit returns no task. That is the one case where
    'no task' legitimately means success — the 2xx IS the confirmation."""
    conn = _conn(raises=True)  # would be UNDETERMINED if it were polled at all
    out = settle(conn, {"vmid": 900, "action": "reconfigure"}, upid="None")
    assert out["taskStatus"] == OK
    conn.nodes.return_value.tasks.assert_not_called()


# ─── the consequences the live defect actually had ──────────────────────────


@pytest.fixture
def gov_home(tmp_path, monkeypatch):
    monkeypatch.setenv("PROXMOX_AIOPS_HOME", str(tmp_path))
    for mod in (audit_mod, policy_mod, undo_mod):
        getattr(mod, {"audit": "reset_engine", "policy": "reset_policy_engine",
                      "undo": "reset_undo_store"}[mod.__name__.rsplit(".", 1)[-1]])()
    yield tmp_path
    for mod in (audit_mod, policy_mod, undo_mod):
        getattr(mod, {"audit": "reset_engine", "policy": "reset_policy_engine",
                      "undo": "reset_undo_store"}[mod.__name__.rsplit(".", 1)[-1]])()


def _rows(db, table):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(f"SELECT * FROM {table}")]  # noqa: S608
    finally:
        conn.close()


def _vm_conn(exitstatus):
    conn = MagicMock(name="conn")
    conn.nodes.return_value.qemu.get.return_value = [{"vmid": 900, "name": "t"}]
    conn.nodes.return_value.qemu.return_value.status.start.post.return_value = _UPID
    return mock_task(conn, exitstatus)


@pytest.mark.integration
def test_a_write_whose_task_failed_is_audited_as_error_with_no_undo(gov_home, monkeypatch):
    """THE regression. Live, this exact sequence produced audit status=ok and an
    undo token with effect_verified=1 for a VM that never started — so
    ``undo_apply`` offered to stop something that was never running."""
    from mcp_server.tools import vm as gov

    monkeypatch.setattr(
        gov, "_get_connection",
        lambda target=None: _vm_conn("start failed: QEMU exited with code 1"))

    result = gov.vm_start(vmid=900, node="pve1")
    assert result.get("error"), "a task that failed must not return a success payload"
    assert "_undo_id" not in result

    audit = _rows(gov_home / "audit.db", "audit_log")
    assert [r["status"] for r in audit] == ["error"]
    assert not (gov_home / "undo.db").exists() or \
        not _rows(gov_home / "undo.db", "undo_log")


@pytest.mark.integration
def test_a_write_whose_task_is_unfinished_is_audited_unknown(gov_home, monkeypatch):
    """Long clones and backups legitimately outlast the wait budget. The honest
    answer is 'undetermined', and any undo token must say effect_verified=0 so
    nobody replays an inverse for a change that may not have happened."""
    from mcp_server.tools import vm as gov

    monkeypatch.setattr(gov, "_get_connection", lambda target=None: _vm_conn(None))

    result = gov.vm_start(vmid=900, node="pve1")
    assert result["outcomeUnknown"] is True

    audit = _rows(gov_home / "audit.db", "audit_log")
    assert [r["status"] for r in audit] == ["unknown"]


@pytest.mark.integration
def test_a_write_whose_task_succeeded_still_audits_ok_with_a_verified_undo(
    gov_home, monkeypatch
):
    """The fix must not make honest successes look doubtful."""
    from mcp_server.tools import vm as gov

    monkeypatch.setattr(gov, "_get_connection", lambda target=None: _vm_conn("OK"))

    result = gov.vm_start(vmid=900, node="pve1")
    assert result["taskStatus"] == OK
    assert result.get("_undo_id")

    audit = _rows(gov_home / "audit.db", "audit_log")
    assert [r["status"] for r in audit] == ["ok"]
    undo = _rows(gov_home / "undo.db", "undo_log")
    assert len(undo) == 1 and undo[0]["effect_verified"] == 1
    assert json.loads(undo[0]["undo_params"])["vmid"] == 900
