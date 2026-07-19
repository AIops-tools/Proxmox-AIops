"""Absent fields come back as null, not as an empty string.

An empty string reads as "this field exists and is empty"; a missing field is a
different fact. Collapsing the two hides information from any consumer, and a
smaller local model will confidently invent the difference. These tests pin the
contract end-to-end: helper, ops layer, and the CLI rendering that has to cope
with a null.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from proxmox_aiops.cli import app
from proxmox_aiops.governance import opt_str
from proxmox_aiops.ops import cluster as cl

runner = CliRunner()


@pytest.mark.unit
def test_opt_str_distinguishes_absent_from_empty():
    assert opt_str(None) is None, "absent must stay absent"
    assert opt_str("") == "", "a genuinely empty value is not the same as absent"
    assert opt_str("pve1", 64) == "pve1"


@pytest.mark.unit
def test_opt_str_still_sanitizes_and_truncates():
    assert opt_str("a\x00b") == "ab"  # control character stripped
    assert opt_str("abcdef", 3) == "abc"


@pytest.mark.unit
def test_opt_str_accepts_non_string_values():
    assert opt_str(42) == "42"


@pytest.mark.unit
def test_ops_report_absent_fields_as_none():
    """A node row with no status/level reports null, not ''."""
    conn = MagicMock()
    conn.cluster.status.get.return_value = [{"type": "cluster"}]  # name/level absent
    rows = cl.cluster_status(conn)
    assert rows[0]["type"] == "cluster"
    assert rows[0]["name"] is None
    assert rows[0]["level"] is None


@pytest.mark.unit
def test_ops_keep_empty_string_when_source_is_empty():
    """An explicitly empty upstream value is preserved as '' — not turned into null."""
    conn = MagicMock()
    conn.cluster.status.get.return_value = [{"type": "cluster", "name": ""}]
    rows = cl.cluster_status(conn)
    assert rows[0]["name"] == ""


@pytest.mark.unit
def test_ops_never_drop_the_key_itself():
    """Keys are always present; only their value may be null.

    Omitting a key entirely is worse than a null — the consumer cannot tell the
    field was even considered.
    """
    conn = MagicMock()
    conn.cluster.status.get.return_value = [{}]
    row = cl.cluster_status(conn)[0]
    for key in ("type", "name", "online", "quorate", "nodes", "level"):
        assert key in row, f"{key} must be present even when the source omitted it"


@pytest.mark.unit
def test_cli_renders_rows_with_null_fields(monkeypatch):
    """The table must survive a null field rather than crashing on render."""
    import proxmox_aiops.cli.vm as vm_cli

    conn = MagicMock()
    # A VM with no name and no status — both become None at the ops layer.
    conn.nodes.return_value.qemu.get.return_value = [{"vmid": 100}]
    conn.nodes.get.return_value = [{"node": "pve1"}]
    monkeypatch.setattr(vm_cli, "get_connection", lambda target=None: (conn, object()))

    result = runner.invoke(app, ["vm", "list"])
    assert result.exit_code == 0, result.output
    assert "100" in result.output


@pytest.mark.unit
def test_undo_list_envelope_measures_truncation(monkeypatch):
    from mcp_server.tools import undo as undo_tools

    rows = [
        {
            "undo_id": f"u{i}",
            "ts": "2026-07-18T00:00:00Z",
            "tool": "some_tool",
            "undo_tool": "some_inverse_tool",
            "note": "",
        }
        for i in range(4)
    ]
    captured = {}

    class _Store:
        def list(self, *, status=None, limit=50):
            captured["limit"] = limit
            return rows[:limit]

    monkeypatch.setattr(undo_tools, "get_undo_store", lambda: _Store())
    result = undo_tools.undo_list(limit=3)
    assert captured["limit"] == 4, "one extra row is fetched to measure truncation"
    assert result["returned"] == 3
    assert result["limit"] == 3
    assert result["truncated"] is True
    assert len(result["undos"]) == 3
