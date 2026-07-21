"""Backup (vzdump) MCP tools: create, list, restore.

``vm_backup`` and ``backup_restore`` are asynchronous — they return a task UPID;
poll completion with ``task_status`` rather than re-issuing. ``backup_restore``
is HIGH risk (it can overwrite an existing VM) and records a safe inverse
(delete the restored VM) only when the restore created a brand-new VM.
"""

from typing import Optional

from mcp_server._shared import _get_connection, mcp, tool_errors
from proxmox_aiops.governance import governed_tool
from proxmox_aiops.ops import backup as bk


@mcp.tool()
@governed_tool(risk_level="medium")
@tool_errors("dict")
def vm_backup(
    vmid: int,
    storage: str,
    mode: str = "snapshot",
    target: Optional[str] = None,
    node: Optional[str] = None,
) -> dict:
    """[WRITE] Create a vzdump backup of a VM/CT to a storage. Returns task UPID.

    Args:
        vmid: Numeric Proxmox guest id (VM or container).
        storage: Backup-capable storage id (see storage_list / storage_content).
        mode: 'snapshot' (default, no downtime), 'suspend', or 'stop'.
        target: Proxmox target name from config.
        node: Node name; omit to auto-locate the guest.
    """
    return bk.vm_backup(_get_connection(target), vmid, storage, node=node, mode=mode)


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("list")
def backup_list(
    storage: str,
    vmid: Optional[int] = None,
    target: Optional[str] = None,
    node: Optional[str] = None,
) -> list:
    """[READ] List backup archives on a storage (optionally filtered by vmid).

    Args:
        storage: Storage id to list backups from.
        vmid: Optional guest id filter.
        target: Proxmox target name from config.
        node: Node name; omit to use the configured default node.
    """
    return bk.list_backups(_get_connection(target), storage, node=node, vmid=vmid)


@mcp.tool()
@governed_tool(
    risk_level="high",
    undo=lambda params, result: (
        {
            "tool": "vm_delete",
            "params": {"vmid": params.get("vmid"), "node": (result or {}).get("node")},
            "skill": "proxmox-aiops",
            "note": "Inverse of backup_restore: delete the freshly-restored VM.",
        }
        if isinstance(result, dict) and result.get("existed_before") is False
        else None
    ),
)
@tool_errors("dict")
def backup_restore(
    vmid: int,
    archive: str,
    storage: str,
    force: bool = False,
    dry_run: bool = False,
    target: Optional[str] = None,
    node: Optional[str] = None,
) -> dict:
    """[WRITE] Restore a QEMU VM from a backup archive. HIGH RISK. Returns task UPID.

    With force=True this OVERWRITES an existing VM (destructive, no undo).
    Restoring into a free vmid records a delete as the safe inverse. Confirm
    with the user before calling. Pass dry_run=True to preview: it runs the same
    existing-VM guard (a preview that would be refused for overwriting without
    force refuses too) and reports whether it would overwrite or create.

    Args:
        vmid: Target VM id to restore into.
        archive: Backup volume id / archive path (see backup_list).
        storage: Storage to place the restored disks on.
        force: Overwrite vmid if it already exists (destructive).
        dry_run: If True, preview (runs the existing-VM guard) without restoring.
        target: Proxmox target name from config.
        node: Node name; omit to use the configured default node.
    """
    conn = _get_connection(target)
    if dry_run:
        return {
            "dryRun": True,
            "wouldRestore": bk.preview_restore(
                conn, vmid, archive, storage, node=node, force=force
            ),
        }
    return bk.restore_backup(conn, vmid, archive, storage, node=node, force=force)
