"""VM disk operations for Proxmox VE: grow-only resize and storage move.

Resize is deliberately grow-only — Proxmox cannot safely shrink a virtual disk,
so a shrink request is refused before any API call is made (fail-fast). Move is
asynchronous and returns a task UPID.
"""

from __future__ import annotations

from typing import Any

from proxmox_aiops.governance import sanitize
from proxmox_aiops.ops.vm_lifecycle import _find_node_for_vmid

_UNIT_BYTES: dict[str, int] = {
    "K": 1024,
    "M": 1024**2,
    "G": 1024**3,
    "T": 1024**4,
}


def _to_bytes(size: str) -> int:
    """Parse a Proxmox size token (e.g. '32G', '512M') into bytes."""
    text = size.strip().lstrip("+")
    if not text:
        raise ValueError(f"Empty disk size {size!r}.")
    unit = text[-1].upper()
    if unit in _UNIT_BYTES:
        return int(float(text[:-1]) * _UNIT_BYTES[unit])
    return int(text)  # raw bytes


def _current_disk_bytes(conn: Any, node: str, vmid: int, disk: str) -> int | None:
    """Return the current size (bytes) of ``disk`` from the VM config, if known."""
    cfg = conn.nodes(node).qemu(vmid).config.get()
    spec = cfg.get(disk)
    if not isinstance(spec, str):
        return None
    for part in spec.split(","):
        if part.startswith("size="):
            return _to_bytes(part.split("=", 1)[1])
    return None


def _reject_shrink(conn: Any, node: str, vmid: int, disk: str, size: str) -> None:
    """Raise ValueError if ``size`` would shrink ``disk`` (grow-only policy)."""
    trimmed = size.strip()
    if trimmed.startswith("-"):
        raise ValueError(
            f"Refusing to shrink disk {disk!r}: Proxmox cannot safely shrink a "
            f"virtual disk. Use a '+<N>G' increment or a larger absolute size."
        )
    if trimmed.startswith("+"):
        return  # any positive increment is a grow
    current = _current_disk_bytes(conn, node, vmid, disk)
    if current is not None and _to_bytes(trimmed) < current:
        raise ValueError(
            f"Refusing to shrink disk {disk!r} from {current} bytes to "
            f"{_to_bytes(trimmed)} bytes. Resize is grow-only."
        )


def resize_disk(
    conn: Any, vmid: int, disk: str, size: str, node: str | None = None
) -> dict:
    """[WRITE] Grow a VM disk. ``size`` is '+<N>G' (increment) or a larger absolute.

    Shrinking is refused. No clean inverse — growing a disk is not reversible.
    """
    host_node = _find_node_for_vmid(conn, vmid, node)
    _reject_shrink(conn, host_node, vmid, disk, size)
    conn.nodes(host_node).qemu(vmid).resize.put(disk=disk, size=size)
    return {
        "vmid": int(vmid),
        "node": host_node,
        "disk": sanitize(disk, 32),
        "size": sanitize(size, 32),
        "action": "vm_resize_disk",
    }


def move_disk(
    conn: Any,
    vmid: int,
    disk: str,
    storage: str,
    node: str | None = None,
    delete: bool = False,
) -> dict:
    """[WRITE] Move a VM disk to another storage. Returns task UPID.

    ``delete`` removes the source copy once the move completes. The source
    storage is captured so a reverse move can be recorded as the undo token.
    """
    host_node = _find_node_for_vmid(conn, vmid, node)
    source_storage = _disk_source_storage(conn, host_node, vmid, disk)
    upid = conn.nodes(host_node).qemu(vmid).move_disk.post(
        disk=disk, storage=storage, delete=1 if delete else 0
    )
    return {
        "vmid": int(vmid),
        "node": host_node,
        "disk": sanitize(disk, 32),
        "to_storage": sanitize(storage, 64),
        "from_storage": sanitize(source_storage, 64),
        "action": "vm_move_disk",
        "task": sanitize(str(upid), 256),
    }


def _disk_source_storage(conn: Any, node: str, vmid: int, disk: str) -> str:
    """Read the storage id a ``disk`` currently lives on, from the VM config."""
    cfg = conn.nodes(node).qemu(vmid).config.get()
    spec = cfg.get(disk, "")
    return spec.split(":", 1)[0] if isinstance(spec, str) and ":" in spec else ""


def preview_move_disk(
    conn: Any,
    vmid: int,
    disk: str,
    storage: str,
    node: str | None = None,
    delete: bool = False,
) -> dict:
    """[READ] Preview move_disk — reads the disk's current placement, changes nothing.

    Reads the same VM config the real move inspects to learn the source storage,
    and reports the from→to move that WOULD run without issuing the POST.
    """
    host_node = _find_node_for_vmid(conn, vmid, node)
    source_storage = _disk_source_storage(conn, host_node, vmid, disk)
    return {
        "vmid": int(vmid),
        "node": host_node,
        "disk": sanitize(disk, 32),
        "from_storage": sanitize(source_storage, 64),
        "to_storage": sanitize(storage, 64),
        "delete": delete,
        "action": "vm_move_disk",
    }
