"""Backup (vzdump) operations for Proxmox VE.

vzdump creates a compressed backup archive of a guest (QEMU VM or LXC CT) onto a
storage that supports the ``backup`` content type. Restores recreate a guest
from such an archive. All three operations are asynchronous on PVE and return a
task UPID — poll it with ``task_status`` rather than re-issuing.
"""

from __future__ import annotations

from typing import Any

from proxmox_aiops.connection import get_default_node
from proxmox_aiops.governance import opt_str, sanitize
from proxmox_aiops.ops.vm_lifecycle import NodeRequiredError, VMNotFoundError


def _guest_exists(conn: Any, node: str, vmid: int) -> bool:
    """Return True if ``vmid`` is a QEMU VM or LXC CT on ``node``."""
    for vm in conn.nodes(node).qemu.get():
        if int(vm["vmid"]) == int(vmid):
            return True
    for ct in conn.nodes(node).lxc.get():
        if int(ct["vmid"]) == int(vmid):
            return True
    return False


def _find_guest_node(conn: Any, vmid: int, node: str | None) -> str:
    """Locate the node hosting guest ``vmid`` (QEMU or LXC).

    An explicit node is trusted as-is; otherwise the configured default node,
    then every cluster node, is scanned.
    """
    if node:
        return node
    default = get_default_node(conn)
    candidates = (
        [default]
        if default
        else [sanitize(str(n["node"]), 64) for n in conn.nodes.get()]
    )
    for cand in candidates:
        if _guest_exists(conn, cand, vmid):
            return cand
    raise VMNotFoundError(
        f"Guest {vmid} not found. List VMs with vm_list / containers with ct_list."
    )


def vm_backup(
    conn: Any,
    vmid: int,
    storage: str,
    node: str | None = None,
    mode: str = "snapshot",
    compress: str = "zstd",
) -> dict:
    """[WRITE] Create a vzdump backup of a VM/CT to ``storage``. Returns task UPID.

    ``mode`` is one of 'snapshot' (default, no downtime), 'suspend', or 'stop'.
    """
    if mode not in ("snapshot", "suspend", "stop"):
        raise ValueError(
            f"Invalid backup mode {mode!r}; expected snapshot, suspend, or stop."
        )
    host_node = _find_guest_node(conn, vmid, node)
    upid = conn.nodes(host_node).vzdump.post(
        vmid=int(vmid), storage=storage, mode=mode, compress=compress
    )
    return {
        "vmid": int(vmid),
        "node": host_node,
        "storage": sanitize(storage, 64),
        "mode": sanitize(mode, 16),
        "action": "vm_backup",
        "task": sanitize(str(upid), 256),
    }


def list_backups(
    conn: Any, storage: str, node: str | None = None, vmid: int | None = None
) -> list[dict]:
    """[READ] List backup archives on a storage (optionally filter by vmid)."""
    resolved = node or get_default_node(conn)
    if not resolved:
        raise NodeRequiredError(
            "No node specified and no default node configured. Pass node=<name>."
        )
    items = conn.nodes(resolved).storage(storage).content.get(content="backup")
    out: list[dict] = []
    for v in items:
        if vmid is not None and v.get("vmid") is not None and int(v["vmid"]) != int(vmid):
            continue
        out.append(
            {
                "volid": opt_str(v.get("volid"), 256),
                "vmid": v.get("vmid"),
                "size": v.get("size"),
                "format": opt_str(v.get("format"), 32),
                "ctime": v.get("ctime"),
                "notes": opt_str(v.get("notes"), 200),
            }
        )
    return out


def restore_backup(
    conn: Any,
    vmid: int,
    archive: str,
    storage: str,
    node: str | None = None,
    force: bool = False,
) -> dict:
    """[WRITE] Restore a QEMU VM from a backup archive into ``vmid``.

    HIGH RISK: with ``force`` this overwrites an existing VM. The pre-restore
    existence of ``vmid`` is captured so the harness can record a safe inverse
    (delete the VM) only when the restore created a brand-new VM.
    """
    resolved = node or get_default_node(conn)
    if not resolved:
        raise NodeRequiredError(
            "No node specified and no default node configured. Pass node=<name>."
        )
    existed_before = _guest_exists(conn, resolved, vmid)
    if existed_before and not force:
        raise ValueError(
            f"VM {vmid} already exists on {resolved}. Pass force=True to overwrite "
            f"(this destroys the current VM) or choose a free vmid (see next_vmid)."
        )
    upid = conn.nodes(resolved).qemu.post(
        vmid=int(vmid), archive=archive, storage=storage, force=1 if force else 0
    )
    return {
        "vmid": int(vmid),
        "node": resolved,
        "archive": sanitize(archive, 256),
        "storage": sanitize(storage, 64),
        "existed_before": existed_before,
        "action": "backup_restore",
        "task": sanitize(str(upid), 256),
    }


def preview_restore(
    conn: Any,
    vmid: int,
    archive: str,
    storage: str,
    node: str | None = None,
    force: bool = False,
) -> dict:
    """[READ] Guarded dry-run preview for restore_backup — reads only, changes nothing.

    Runs the SAME existing-VM guard as the real restore: it reads whether
    ``vmid`` already exists on the target node, and if it does and ``force`` is
    False it refuses here too (the identical error), so a preview that would be
    refused says so instead of showing a green "would restore" banner. Reports
    whether the restore would OVERWRITE an existing VM or CREATE a new one.
    """
    resolved = node or get_default_node(conn)
    if not resolved:
        raise NodeRequiredError(
            "No node specified and no default node configured. Pass node=<name>."
        )
    existed_before = _guest_exists(conn, resolved, vmid)
    if existed_before and not force:
        raise ValueError(
            f"VM {vmid} already exists on {resolved}. Pass force=True to overwrite "
            f"(this destroys the current VM) or choose a free vmid (see next_vmid)."
        )
    return {
        "vmid": int(vmid),
        "node": resolved,
        "archive": sanitize(archive, 256),
        "storage": sanitize(storage, 64),
        "existed_before": existed_before,
        "wouldOverwrite": existed_before,
        "action": "backup_restore",
    }
