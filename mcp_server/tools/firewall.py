"""Firewall read MCP tools (inspection only — no rule mutation)."""

from typing import Optional

from mcp_server._shared import _get_connection, mcp, tool_errors
from proxmox_aiops.governance import governed_tool
from proxmox_aiops.ops import firewall as fw


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def vm_firewall_rules_list(
    vmid: int, target: Optional[str] = None, node: Optional[str] = None
) -> list:
    """[READ] List the firewall rules attached to a VM.

    Args:
        vmid: Numeric Proxmox VM id.
        target: Proxmox target name from config.
        node: Node name; omit to auto-locate the VM.
    """
    return fw.vm_firewall_rules(_get_connection(target), vmid, node=node)


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def cluster_firewall_status(target: Optional[str] = None) -> dict:
    """[READ] Cluster-wide firewall options (notably whether it is enabled).

    Args:
        target: Proxmox target name from config.
    """
    return fw.cluster_firewall_status(_get_connection(target))
