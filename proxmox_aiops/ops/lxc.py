"""LXC container operations for Proxmox VE.

Proxmox runs LXC containers alongside QEMU VMs; these mirror the VM lifecycle
shape (list/start/stop) so the harness's audit / risk-tier / undo behavior
applies identically. Kept minimal in the skeleton — create/clone/destroy are
the obvious next additions.
"""

from __future__ import annotations

from typing import Any

from proxmox_aiops.connection import get_default_node
from proxmox_aiops.governance import sanitize


class ContainerNotFoundError(Exception):
    """Raised when an LXC container (vmid) cannot be located on any node."""


def _iter_nodes(conn: Any, node: str | None) -> list[str]:
    resolved = node or get_default_node(conn)
    if resolved:
        return [resolved]
    return [sanitize(str(n["node"]), 64) for n in conn.nodes.get()]


def _find_node_for_ct(conn: Any, vmid: int, node: str | None) -> str:
    for candidate in _iter_nodes(conn, node):
        for ct in conn.nodes(candidate).lxc.get():
            if int(ct["vmid"]) == int(vmid):
                return candidate
    raise ContainerNotFoundError(
        f"Container {vmid} not found. List containers with ct_list."
    )


def list_cts(conn: Any, node: str | None = None) -> list[dict]:
    """[READ] List LXC containers with name, vmid, status, cpu, mem."""
    out: list[dict] = []
    for candidate in _iter_nodes(conn, node):
        for ct in conn.nodes(candidate).lxc.get():
            out.append(
                {
                    "vmid": int(ct["vmid"]),
                    "name": sanitize(str(ct.get("name", "")), 128),
                    "status": sanitize(str(ct.get("status", "")), 32),
                    "cpu": ct.get("cpus", ct.get("cpu")),
                    "mem": ct.get("maxmem", ct.get("mem")),
                    "node": candidate,
                }
            )
    return out


def start_ct(conn: Any, vmid: int, node: str | None = None) -> dict:
    """[WRITE] Start an LXC container. Returns task UPID. Inverse: stop_ct."""
    host_node = _find_node_for_ct(conn, vmid, node)
    upid = conn.nodes(host_node).lxc(vmid).status.start.post()
    return {"vmid": int(vmid), "node": host_node, "action": "ct_start",
            "task": sanitize(str(upid), 256)}


def stop_ct(conn: Any, vmid: int, node: str | None = None) -> dict:
    """[WRITE] Stop an LXC container. Returns task UPID. Inverse: start_ct."""
    host_node = _find_node_for_ct(conn, vmid, node)
    upid = conn.nodes(host_node).lxc(vmid).status.stop.post()
    return {"vmid": int(vmid), "node": host_node, "action": "ct_stop",
            "task": sanitize(str(upid), 256)}
