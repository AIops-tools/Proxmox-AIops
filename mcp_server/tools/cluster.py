"""Cluster / node / async-task MCP tools (all read-only)."""

from typing import Optional

from mcp_server._shared import _get_connection, mcp, tool_errors
from proxmox_aiops.governance import governed_tool
from proxmox_aiops.ops import cluster as cl


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def node_list(target: Optional[str] = None) -> list:
    """[READ] List Proxmox cluster nodes with status, cpu load, and memory.

    Args:
        target: Proxmox target name from config; omit to use the default.
    """
    return cl.list_nodes(_get_connection(target))


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def cluster_status(target: Optional[str] = None) -> list:
    """[READ] Return cluster membership + quorum status.

    The ``type=cluster`` row's ``quorate`` field indicates whether the cluster
    currently has quorum.

    Args:
        target: Proxmox target name from config.
    """
    return cl.cluster_status(_get_connection(target))


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def task_status(upid: str, target: Optional[str] = None, node: Optional[str] = None) -> dict:
    """[READ] Poll a Proxmox async task (clone / migrate / backup) by its UPID.

    Use after a write that returned a task UPID to check completion instead of
    re-issuing the operation. The node is parsed from the UPID when omitted.

    Args:
        upid: The task UPID returned by an async write tool.
        target: Proxmox target name from config.
        node: Node the task runs on; omit to parse it from the UPID.
    """
    return cl.get_task_status(_get_connection(target), upid, node=node)
