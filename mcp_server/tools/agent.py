"""QEMU guest-agent read MCP tools (ping only — no guest command execution)."""

from typing import Optional

from mcp_server._shared import _get_connection, mcp, tool_errors
from proxmox_aiops.governance import governed_tool
from proxmox_aiops.ops import agent as ag


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def vm_agent_ping(
    vmid: int, target: Optional[str] = None, node: Optional[str] = None
) -> dict:
    """[READ] Ping a VM's QEMU guest agent to check it is installed and responsive.

    A non-running or absent agent yields responsive=False with an explanation
    rather than an error.

    Args:
        vmid: Numeric Proxmox VM id.
        target: Proxmox target name from config.
        node: Node name; omit to auto-locate the VM.
    """
    return ag.agent_ping(_get_connection(target), vmid, node=node)
