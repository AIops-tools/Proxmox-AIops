"""Storage read MCP tools for Proxmox VE."""


from typing import Optional

from mcp_server._shared import _get_connection, mcp, tool_errors
from proxmox_aiops.governance import governed_tool
from proxmox_aiops.ops import storage as st


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def storage_list(target: Optional[str] = None, node: Optional[str] = None) -> list:
    """[READ] List storage pools on a node (id, type, total/used/avail bytes).

    Args:
        target: Proxmox target name from config; omit to use the default.
        node: Node name; omit to use the target's configured default node.
    """
    return st.list_storage(_get_connection(target), node=node)


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def storage_content(
    storage: str,
    content: Optional[str] = None,
    target: Optional[str] = None,
    node: Optional[str] = None,
) -> list:
    """[READ] List volumes on a storage pool (ISOs, disk images, backups, templates).

    Args:
        storage: Storage pool id (see storage_list).
        content: Optional filter — 'iso', 'images', 'backup', 'vztmpl'.
        target: Proxmox target name from config.
        node: Node name; omit to use the configured default node.
    """
    return st.list_storage_content(
        _get_connection(target), storage, node=node, content=content
    )
