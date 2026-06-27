"""Resource-pool read MCP tools."""

from typing import Optional

from mcp_server._shared import _get_connection, mcp, tool_errors
from proxmox_aiops.governance import governed_tool
from proxmox_aiops.ops import pool


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def pool_list(target: Optional[str] = None) -> list:
    """[READ] List resource pools (poolid + comment).

    Args:
        target: Proxmox target name from config.
    """
    return pool.pool_list(_get_connection(target))


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def pool_members(poolid: str, target: Optional[str] = None) -> dict:
    """[READ] List the members of a pool (VMs, CTs, storage).

    Args:
        poolid: Pool id (see pool_list).
        target: Proxmox target name from config.
    """
    return pool.pool_members(_get_connection(target), poolid)
