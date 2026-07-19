"""Tests for the diagnostics / RCA analyses (pure functions + MCP collection).

The heuristics are pure, so most tests pass telemetry rows directly. Two tests
drive the MCP tools with a mocked proxmoxer connection to prove collection +
governance wiring.
"""

from unittest.mock import MagicMock

import pytest

from proxmox_aiops.ops import diagnostics as diag


@pytest.mark.unit
def test_node_pressure_flags_cpu_mem_disk_with_cited_numbers():
    rows = [
        {
            "node": "pve1",
            "type": "node",
            "status": "online",
            "cpu": 0.92,
            "mem": 95,
            "maxmem": 100,
            "disk": 96,
            "maxdisk": 100,
        },
    ]
    result = diag.node_pressure_findings(rows)
    signals = {f["signal"] for f in result["findings"]}
    assert signals == {"high CPU", "high memory", "root fs near full"}
    # Every finding cites its measured number.
    assert all(any(c.isdigit() for c in f["detail"]) for f in result["findings"])
    # 96% disk and 95% mem cross the critical (>=95/97) lines → ranked first.
    assert result["findings"][0]["severity"] == "critical"
    assert result["summary"][0]["cpuPct"] == 92.0


@pytest.mark.unit
def test_node_pressure_healthy_node_yields_no_findings():
    rows = [
        {
            "node": "pve1",
            "type": "node",
            "status": "online",
            "cpu": 0.10,
            "mem": 20,
            "maxmem": 100,
            "disk": 30,
            "maxdisk": 100,
        }
    ]
    result = diag.node_pressure_findings(rows)
    assert result["findings"] == []
    assert result["nodesAnalyzed"] == 1


@pytest.mark.unit
def test_node_pressure_offline_node_is_critical():
    rows = [{"node": "pve2", "type": "node", "status": "offline"}]
    result = diag.node_pressure_findings(rows)
    assert result["findings"][0]["signal"] == "node offline"
    assert result["findings"][0]["severity"] == "critical"


@pytest.mark.unit
def test_node_pressure_missing_maxmem_does_not_crash():
    rows = [{"node": "pve1", "type": "node", "status": "online", "mem": 50}]
    result = diag.node_pressure_findings(rows)
    assert result["summary"][0]["memPct"] is None
    assert result["findings"] == []


@pytest.mark.unit
def test_guest_health_flags_running_guest_saturation_and_lists_stopped():
    rows = [
        {
            "type": "qemu",
            "name": "web",
            "vmid": 100,
            "node": "pve1",
            "status": "running",
            "mem": 96,
            "maxmem": 100,
            "disk": 50,
            "maxdisk": 100,
        },
        {
            "type": "lxc",
            "name": "db",
            "vmid": 200,
            "node": "pve1",
            "status": "stopped",
            "mem": 0,
            "maxmem": 100,
        },
    ]
    result = diag.guest_health_findings(rows)
    assert result["guestsAnalyzed"] == 2
    assert [g["vmid"] for g in result["stopped"]] == [200]
    assert result["findings"][0]["signal"] == "guest memory saturated"
    assert "100" in result["findings"][0]["detail"]  # cites vmid + pct


@pytest.mark.unit
def test_guest_health_disk_near_full_is_critical_over_95():
    rows = [
        {
            "type": "qemu",
            "name": "big",
            "vmid": 101,
            "node": "pve1",
            "status": "running",
            "mem": 10,
            "maxmem": 100,
            "disk": 97,
            "maxdisk": 100,
        }
    ]
    result = diag.guest_health_findings(rows)
    assert result["findings"][0]["signal"] == "guest disk near full"
    assert result["findings"][0]["severity"] == "critical"


@pytest.mark.unit
def test_mcp_node_pressure_rca_collects_and_is_governed(monkeypatch):
    from mcp_server.tools import diagnostics as tools

    assert tools.node_pressure_rca._is_governed_tool is True
    conn = MagicMock(name="conn")
    conn.cluster.resources.get.return_value = [
        {
            "node": "pve1",
            "type": "node",
            "status": "online",
            "cpu": 0.9,
            "mem": 10,
            "maxmem": 100,
            "disk": 10,
            "maxdisk": 100,
        },
    ]
    monkeypatch.setattr(tools, "_get_connection", lambda target=None: conn)
    result = tools.node_pressure_rca()
    assert result["nodesAnalyzed"] == 1
    assert result["findings"][0]["signal"] == "high CPU"


@pytest.mark.unit
def test_mcp_guest_health_rca_filters_to_guests(monkeypatch):
    from mcp_server.tools import diagnostics as tools

    conn = MagicMock(name="conn")
    conn.cluster.resources.get.return_value = [
        {"type": "node", "name": "pve1"},  # filtered out
        {"type": "storage", "name": "local"},  # filtered out
        {
            "type": "qemu",
            "name": "web",
            "vmid": 100,
            "node": "pve1",
            "status": "running",
            "mem": 99,
            "maxmem": 100,
        },
    ]
    monkeypatch.setattr(tools, "_get_connection", lambda target=None: conn)
    result = tools.guest_health_rca()
    assert result["guestsAnalyzed"] == 1
    assert result["findings"][0]["signal"] == "guest memory saturated"


@pytest.mark.unit
def test_rank_assigns_explicit_worst_first_rank():
    """Findings state their priority explicitly, not implicitly by list order.

    A consumer — notably a smaller local model summarising the result — must not
    have to infer urgency from a finding's position in the list.
    """
    from proxmox_aiops.ops import diagnostics as _diag

    ranked = _diag._rank([{"severity": "info"}, {"severity": "critical"}, {"severity": "warning"}])
    assert [f["severity"] for f in ranked] == ["critical", "warning", "info"]
    assert [f["rank"] for f in ranked] == [1, 2, 3]
