"""Tests for the cluster / node / async-task read ops not already covered by
test_new_ops.py (list_nodes, cluster_status, get_task_status, UPID parsing,
task_log node inference, and the bad-UPID teaching errors).
"""

from unittest.mock import MagicMock

import pytest

from proxmox_aiops.ops import cluster as cl


@pytest.mark.unit
def test_list_nodes_normalizes():
    conn = MagicMock(name="conn")
    conn.nodes.get.return_value = [
        {"node": "pve1", "status": "online", "cpu": 0.1, "maxcpu": 8,
         "mem": 40, "maxmem": 100, "uptime": 1000},
    ]
    rows = cl.list_nodes(conn)
    conn.nodes.get.assert_called_once_with()
    assert rows[0]["node"] == "pve1"
    assert rows[0]["maxcpu"] == 8 and rows[0]["uptime"] == 1000


@pytest.mark.unit
def test_cluster_status_reports_quorate():
    conn = MagicMock(name="conn")
    conn.cluster.status.get.return_value = [
        {"type": "cluster", "name": "prod", "quorate": 1, "nodes": 3},
        {"type": "node", "name": "pve1", "online": 1, "level": ""},
    ]
    rows = cl.cluster_status(conn)
    conn.cluster.status.get.assert_called_once_with()
    cluster_row = next(r for r in rows if r["type"] == "cluster")
    assert cluster_row["quorate"] == 1 and cluster_row["nodes"] == 3


@pytest.mark.unit
def test_get_task_status_parses_node_from_upid():
    conn = MagicMock(name="conn")
    conn.nodes.return_value.tasks.return_value.status.get.return_value = {
        "type": "qmclone", "status": "stopped", "exitstatus": "OK",
    }
    upid = "UPID:pve7:0001:0002:start:100:root@pam:"
    out = cl.get_task_status(conn, upid)
    # node parsed from the UPID (pve7), not passed explicitly
    conn.nodes.assert_called_once_with("pve7")
    conn.nodes.return_value.tasks.assert_called_once_with(upid)
    assert out["status"] == "stopped" and out["exitstatus"] == "OK"
    assert out["node"] == "pve7"


@pytest.mark.unit
def test_get_task_status_explicit_node_overrides_parse():
    conn = MagicMock(name="conn")
    conn.nodes.return_value.tasks.return_value.status.get.return_value = {}
    out = cl.get_task_status(conn, "UPID:pve1:x:y", node="pveX")
    conn.nodes.assert_called_once_with("pveX")
    assert out["node"] == "pveX"


@pytest.mark.unit
def test_get_task_status_unparseable_upid_raises():
    conn = MagicMock(name="conn")
    with pytest.raises(ValueError, match="Could not determine node"):
        cl.get_task_status(conn, "not-a-upid")


@pytest.mark.unit
def test_task_log_infers_node_and_passes_limit():
    conn = MagicMock(name="conn")
    conn.nodes.return_value.tasks.return_value.log.get.return_value = [
        {"n": 1, "t": "started"},
    ]
    result = cl.task_log(conn, "UPID:pve2:aa:bb", limit=5)
    conn.nodes.assert_called_once_with("pve2")
    # limit+1 is fetched so a truncated read can announce itself.
    conn.nodes.return_value.tasks.return_value.log.get.assert_called_once_with(limit=6)
    assert result["lines"][0]["t"] == "started"
    assert result["truncated"] is False


@pytest.mark.unit
def test_task_log_unparseable_upid_raises():
    conn = MagicMock(name="conn")
    with pytest.raises(ValueError, match="Could not determine node"):
        cl.task_log(conn, "garbage")


@pytest.mark.unit
def test_node_status_requires_node():
    conn = MagicMock(name="conn")
    with pytest.raises(ValueError, match="requires a node name"):
        cl.node_status(conn, "")


@pytest.mark.unit
def test_task_log_announces_truncation_and_caps_lines():
    """More lines than the limit → truncated=True, and only `limit` returned.

    This is the failure mode the envelope exists for: a bare list forces the
    consumer to infer "there is more" from a length coincidence, and a long
    result then gets reported as "no data returned".
    """
    conn = MagicMock(name="conn")
    # 4 lines available, limit 3 → the ops layer asks for 4 and sees the overflow.
    conn.nodes.return_value.tasks.return_value.log.get.return_value = [
        {"n": i, "t": f"line{i}"} for i in range(1, 5)
    ]
    result = cl.task_log(conn, "UPID:pve1:aa:bb", limit=3)
    assert result["truncated"] is True
    assert result["returned"] == 3
    assert len(result["lines"]) == 3
    assert result["limit"] == 3
    assert [ln["t"] for ln in result["lines"]] == ["line1", "line2", "line3"]
