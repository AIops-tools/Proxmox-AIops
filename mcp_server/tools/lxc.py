"""LXC container MCP tools: list / start / stop (start/stop carry undo tokens)."""

from typing import Optional

from mcp_server._shared import _get_connection, mcp, tool_errors
from proxmox_aiops.governance import governed_tool
from proxmox_aiops.ops import lxc


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def ct_list(target: Optional[str] = None, node: Optional[str] = None) -> list:
    """[READ] List LXC containers with name, vmid, status, cpu, mem.

    Args:
        target: Proxmox target name from config; omit to use the default.
        node: Node name; omit to use the configured default / all nodes.
    """
    return lxc.list_cts(_get_connection(target), node=node)


@mcp.tool()
@governed_tool(
    risk_level="medium",
    undo=lambda params, result: (
        {
            "tool": "ct_stop",
            "params": {"vmid": params.get("vmid"), "node": params.get("node")},
            "skill": "proxmox-aiops",
            "note": "Inverse of ct_start: stop the container again.",
        }
        if isinstance(result, dict) and not result.get("dryRun")
        else None
    ),
)
@tool_errors("dict")
def ct_start(
    vmid: int,
    dry_run: bool = False,
    target: Optional[str] = None,
    node: Optional[str] = None,
) -> dict:
    """[WRITE] Start an LXC container. Returns the task UPID. Inverse: ct_stop.

    Pass dry_run=True to preview.

    Args:
        vmid: Numeric container id (see ct_list).
        dry_run: If True, preview without starting.
        target: Proxmox target name from config.
        node: Node name; omit to auto-locate the container.
    """
    if dry_run:
        return {"dryRun": True, "wouldStart": {"vmid": vmid, "node": node}}
    return lxc.start_ct(_get_connection(target), vmid, node=node)


@mcp.tool()
@governed_tool(
    risk_level="medium",
    undo=lambda params, result: (
        {
            "tool": "ct_start",
            "params": {"vmid": params.get("vmid"), "node": params.get("node")},
            "skill": "proxmox-aiops",
            "note": "Inverse of ct_stop: start the container again.",
        }
        if isinstance(result, dict) and not result.get("dryRun")
        else None
    ),
)
@tool_errors("dict")
def ct_stop(
    vmid: int,
    dry_run: bool = False,
    target: Optional[str] = None,
    node: Optional[str] = None,
) -> dict:
    """[WRITE] Stop an LXC container. Returns the task UPID. Inverse: ct_start.

    Pass dry_run=True to preview.

    Args:
        vmid: Numeric container id (see ct_list).
        dry_run: If True, preview without stopping.
        target: Proxmox target name from config.
        node: Node name; omit to auto-locate the container.
    """
    if dry_run:
        return {"dryRun": True, "wouldStop": {"vmid": vmid, "node": node}}
    return lxc.stop_ct(_get_connection(target), vmid, node=node)
