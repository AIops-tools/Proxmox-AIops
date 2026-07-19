"""Diagnostics / RCA MCP tools: node pressure and guest health.

Read-only signature analyses (risk_level="low"). Each tool collects the
``/cluster/resources`` inventory once and hands it to a pure analysis function
in ``proxmox_aiops.ops.diagnostics`` — so the heuristics stay unit-testable
without a live cluster, and the collection stays here where the connection is.
"""

from typing import Optional

from mcp_server._shared import _get_connection, mcp, tool_errors
from proxmox_aiops.governance import governed_tool
from proxmox_aiops.ops import cluster as cl
from proxmox_aiops.ops import diagnostics as diag

_GUEST_TYPES = {"qemu", "lxc"}


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def node_pressure_rca(target: Optional[str] = None) -> dict:
    """[READ] Rank cluster nodes by CPU / memory / root-fs pressure.

    Pulls the /cluster/resources node view and flags each node over the CPU
    (85%), memory (90%), or disk (85%) thresholds, worst-first, citing the
    measured percentage and a concrete action for every finding.

    Args:
        target: Proxmox target name from config; omit to use the default.
    """
    conn = _get_connection(target)
    node_rows = cl.cluster_resources(conn, resource_type="node")
    return diag.node_pressure_findings(node_rows)


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def guest_health_rca(target: Optional[str] = None) -> dict:
    """[READ] Scan VMs and containers for stopped guests, memory saturation,
    and disks near full.

    Pulls the /cluster/resources guest view (qemu + lxc) and reports worst-first
    findings plus the list of stopped guests, each finding citing the measured
    number and a concrete remediation.

    Args:
        target: Proxmox target name from config; omit to use the default.
    """
    conn = _get_connection(target)
    rows = cl.cluster_resources(conn)
    guest_rows = [r for r in rows if str(r.get("type")) in _GUEST_TYPES]
    return diag.guest_health_findings(guest_rows)
