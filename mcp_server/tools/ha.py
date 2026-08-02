"""High-Availability (HA) read MCP tools.

HA is optional; both tools report a clear "not configured" signal instead of
erroring when the cluster has no HA set up.
"""

from typing import Optional

from mcp_server._shared import _get_connection, mcp, tool_errors
from proxmox_aiops.governance import governed_tool
from proxmox_aiops.ops import ha


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def ha_status(target: Optional[str] = None) -> dict:
    """[READ] Current HA status entries, or a not-configured signal.

    Returns {"configured": bool, "entries": [...]}. Do NOT infer "HA is set up"
    from a non-empty entries list: every quorate cluster reports a quorum row,
    and master/lrm rows once the HA stack has run, with zero resources defined.
    "configured" is true only when HA actually manages something; when it is
    false a message explains that the rows describe the stack itself.

    Args:
        target: Proxmox target name from config.
    """
    return ha.ha_status(_get_connection(target))


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def ha_resource_list(target: Optional[str] = None) -> list:
    """[READ] HA-managed resources (VMs/CTs); empty when HA is not configured.

    Args:
        target: Proxmox target name from config.
    """
    return ha.ha_resource_list(_get_connection(target))
