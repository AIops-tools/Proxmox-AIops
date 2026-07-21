"""VM disk MCP tools: grow-only resize and storage move.

``vm_resize_disk`` refuses any shrink before issuing an API call. ``vm_move_disk``
is asynchronous (returns a task UPID) and records a reverse move as its undo
token when the source storage is known.
"""

from typing import Optional

from mcp_server._shared import _get_connection, mcp, tool_errors
from proxmox_aiops.governance import governed_tool
from proxmox_aiops.ops import disk as dk


@mcp.tool()
@governed_tool(risk_level="medium")
@tool_errors("dict")
def vm_resize_disk(
    vmid: int,
    disk: str,
    size: str,
    dry_run: bool = False,
    target: Optional[str] = None,
    node: Optional[str] = None,
) -> dict:
    """[WRITE] Grow a VM disk. GROW-ONLY — shrink requests are refused.

    No undo token: growing a disk cannot be reversed. Pass dry_run=True to preview.

    Args:
        vmid: Numeric Proxmox VM id.
        disk: Disk key, e.g. 'scsi0', 'virtio0', 'sata0'.
        size: '+<N>G' increment (e.g. '+10G') or a larger absolute size.
        dry_run: If True, preview without resizing.
        target: Proxmox target name from config.
        node: Node name; omit to auto-locate the VM.
    """
    if dry_run:
        return {"dryRun": True, "wouldResize": {"vmid": vmid, "disk": disk, "size": size}}
    return dk.resize_disk(_get_connection(target), vmid, disk, size, node=node)


@mcp.tool()
@governed_tool(
    risk_level="medium",
    undo=lambda params, result: (
        {
            "tool": "vm_move_disk",
            "params": {
                "vmid": params.get("vmid"),
                "disk": params.get("disk"),
                "storage": (result or {}).get("from_storage"),
                "node": (result or {}).get("node"),
            },
            "skill": "proxmox-aiops",
            "note": "Inverse of vm_move_disk: move the disk back to its source storage.",
        }
        if isinstance(result, dict) and result.get("from_storage")
        else None
    ),
)
@tool_errors("dict")
def vm_move_disk(
    vmid: int,
    disk: str,
    storage: str,
    delete: bool = False,
    dry_run: bool = False,
    target: Optional[str] = None,
    node: Optional[str] = None,
) -> dict:
    """[WRITE] Move a VM disk to another storage. Returns task UPID. Async.

    Records a reverse move as the undo token when the source storage is known.
    Pass dry_run=True to read the disk's current placement and preview the move.

    Args:
        vmid: Numeric Proxmox VM id.
        disk: Disk key, e.g. 'scsi0'.
        storage: Destination storage id.
        delete: Remove the source copy after the move completes.
        dry_run: If True, preview the from→to move without moving anything.
        target: Proxmox target name from config.
        node: Node name; omit to auto-locate the VM.
    """
    conn = _get_connection(target)
    if dry_run:
        return {
            "dryRun": True,
            "wouldMoveDisk": dk.preview_move_disk(
                conn, vmid, disk, storage, node=node, delete=delete
            ),
        }
    return dk.move_disk(conn, vmid, disk, storage, node=node, delete=delete)
