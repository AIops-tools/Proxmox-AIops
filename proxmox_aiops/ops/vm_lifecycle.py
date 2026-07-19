"""QEMU VM lifecycle operations for Proxmox VE.

Bodies are thin wrappers over proxmoxer's resource-path API, e.g.
``conn.nodes(node).qemu(vmid).status.start.post()``. All API-returned text is
run through ``sanitize()`` before reaching the caller (output hygiene).
"""

from __future__ import annotations

from typing import Any

from proxmox_aiops.connection import get_default_node
from proxmox_aiops.governance import opt_str, sanitize


class VMNotFoundError(Exception):
    """Raised when a VM (vmid) cannot be located on any node."""


class NodeRequiredError(Exception):
    """Raised when an operation needs a node but none was given or configured."""


def _require_node(conn: Any, node: str | None) -> str:
    """Resolve the node name: explicit arg → connection default → error."""
    resolved = node or get_default_node(conn)
    if not resolved:
        raise NodeRequiredError(
            "No node specified and no default node configured. Pass node=<name> "
            "or set 'node' on the target in config.yaml. List nodes via the "
            "Proxmox UI or 'pvesh get /nodes'."
        )
    return resolved


def _iter_nodes(conn: Any, node: str | None) -> list[str]:
    """Return the node list to scan: the resolved one, else all cluster nodes."""
    resolved = node or get_default_node(conn)
    if resolved:
        return [resolved]
    return [sanitize(str(n["node"]), 64) for n in conn.nodes.get()]


def _find_node_for_vmid(conn: Any, vmid: int, node: str | None) -> str:
    """Locate which node hosts ``vmid``; raise VMNotFoundError if absent."""
    for candidate in _iter_nodes(conn, node):
        for vm in conn.nodes(candidate).qemu.get():
            if int(vm["vmid"]) == int(vmid):
                return candidate
    raise VMNotFoundError(
        f"VM {vmid} not found. List VMs with vm_list to see available vmids."
    )


def list_vms(conn: Any, node: str | None = None) -> list[dict]:
    """[READ] List QEMU VMs with name, vmid, status, cpu, mem.

    Scans the given node (or the configured default; or all cluster nodes if
    neither is set). Returns a high-signal summary, not the full config blob.
    """
    out: list[dict] = []
    for candidate in _iter_nodes(conn, node):
        for vm in conn.nodes(candidate).qemu.get():
            out.append(
                {
                    "vmid": int(vm["vmid"]),
                    "name": opt_str(vm.get("name"), 128),
                    "status": opt_str(vm.get("status"), 32),
                    "cpu": vm.get("cpus", vm.get("cpu")),
                    "mem": vm.get("maxmem", vm.get("mem")),
                    "node": candidate,
                }
            )
    return out


def get_vm(conn: Any, vmid: int, node: str | None = None) -> dict:
    """[READ] Return current status detail for a single VM."""
    host_node = _find_node_for_vmid(conn, vmid, node)
    status = conn.nodes(host_node).qemu(vmid).status.current.get()
    return {
        "vmid": int(vmid),
        "node": host_node,
        "name": opt_str(status.get("name"), 128),
        "status": opt_str(status.get("status"), 32),
        "cpus": status.get("cpus"),
        "maxmem": status.get("maxmem"),
        "uptime": status.get("uptime"),
    }


def start_vm(conn: Any, vmid: int, node: str | None = None) -> dict:
    """[WRITE] Start a VM. Returns the task UPID. Inverse: stop_vm."""
    host_node = _find_node_for_vmid(conn, vmid, node)
    upid = conn.nodes(host_node).qemu(vmid).status.start.post()
    return {"vmid": int(vmid), "node": host_node, "action": "start",
            "task": sanitize(str(upid), 256)}


def stop_vm(conn: Any, vmid: int, node: str | None = None) -> dict:
    """[WRITE] Hard-stop a VM (power off). Returns the task UPID. Inverse: start_vm."""
    host_node = _find_node_for_vmid(conn, vmid, node)
    upid = conn.nodes(host_node).qemu(vmid).status.stop.post()
    return {"vmid": int(vmid), "node": host_node, "action": "stop",
            "task": sanitize(str(upid), 256)}


def snapshot_create(conn: Any, vmid: int, name: str, node: str | None = None) -> dict:
    """[WRITE] Create a named snapshot. Inverse: snapshot_delete(name)."""
    host_node = _find_node_for_vmid(conn, vmid, node)
    upid = conn.nodes(host_node).qemu(vmid).snapshot.post(snapname=name)
    return {"vmid": int(vmid), "node": host_node, "snapshot": sanitize(name, 64),
            "action": "snapshot_create", "task": sanitize(str(upid), 256)}


def snapshot_delete(conn: Any, vmid: int, name: str, node: str | None = None) -> dict:
    """[WRITE] Delete a named snapshot."""
    host_node = _find_node_for_vmid(conn, vmid, node)
    upid = conn.nodes(host_node).qemu(vmid).snapshot(name).delete()
    return {"vmid": int(vmid), "node": host_node, "snapshot": sanitize(name, 64),
            "action": "snapshot_delete", "task": sanitize(str(upid), 256)}


def list_snapshots(conn: Any, vmid: int, node: str | None = None) -> list[dict]:
    """[READ] List snapshots for a VM (name + description)."""
    host_node = _find_node_for_vmid(conn, vmid, node)
    snaps = conn.nodes(host_node).qemu(vmid).snapshot.get()
    return [
        {
            "name": opt_str(s.get("name"), 64),
            "description": opt_str(s.get("description"), 200),
            "vmstate": s.get("vmstate"),
        }
        for s in snaps
    ]


def shutdown_vm(conn: Any, vmid: int, node: str | None = None) -> dict:
    """[WRITE] Graceful ACPI shutdown (vs hard stop_vm). Inverse: start_vm."""
    host_node = _find_node_for_vmid(conn, vmid, node)
    upid = conn.nodes(host_node).qemu(vmid).status.shutdown.post()
    return {"vmid": int(vmid), "node": host_node, "action": "shutdown",
            "task": sanitize(str(upid), 256)}


def reboot_vm(conn: Any, vmid: int, node: str | None = None) -> dict:
    """[WRITE] Reboot a VM (graceful). No clean inverse."""
    host_node = _find_node_for_vmid(conn, vmid, node)
    upid = conn.nodes(host_node).qemu(vmid).status.reboot.post()
    return {"vmid": int(vmid), "node": host_node, "action": "reboot",
            "task": sanitize(str(upid), 256)}


def get_vm_config(conn: Any, vmid: int, node: str | None = None) -> dict:
    """[READ] Return the VM's config (cores, memory, disks, net, boot order)."""
    host_node = _find_node_for_vmid(conn, vmid, node)
    cfg = conn.nodes(host_node).qemu(vmid).config.get()
    return {
        "vmid": int(vmid),
        "node": host_node,
        "name": opt_str(cfg.get("name"), 128),
        "cores": cfg.get("cores"),
        "sockets": cfg.get("sockets"),
        "memory": cfg.get("memory"),
        "ostype": opt_str(cfg.get("ostype"), 32),
        "boot": opt_str(cfg.get("boot"), 128),
    }


def reconfigure_vm(
    conn: Any,
    vmid: int,
    cores: int | None = None,
    memory: int | None = None,
    node: str | None = None,
) -> dict:
    """[WRITE] Change a VM's cores and/or memory (MiB).

    Captures the previous values so the harness can record an inverse
    reconfigure as the undo token. At least one of cores/memory is required.
    """
    if cores is None and memory is None:
        raise ValueError("reconfigure_vm needs at least one of cores / memory.")
    host_node = _find_node_for_vmid(conn, vmid, node)
    prev = conn.nodes(host_node).qemu(vmid).config.get()
    changes: dict[str, Any] = {}
    if cores is not None:
        changes["cores"] = int(cores)
    if memory is not None:
        changes["memory"] = int(memory)
    conn.nodes(host_node).qemu(vmid).config.post(**changes)
    return {
        "vmid": int(vmid),
        "node": host_node,
        "action": "reconfigure",
        "applied": changes,
        "previous": {"cores": prev.get("cores"), "memory": prev.get("memory")},
    }


def clone_vm(
    conn: Any,
    vmid: int,
    newid: int,
    name: str | None = None,
    node: str | None = None,
) -> dict:
    """[WRITE] Clone a VM to a new vmid. Returns the task UPID. Inverse: delete_vm(newid)."""
    host_node = _find_node_for_vmid(conn, vmid, node)
    kwargs: dict[str, Any] = {"newid": int(newid)}
    if name:
        kwargs["name"] = name
    upid = conn.nodes(host_node).qemu(vmid).clone.post(**kwargs)
    return {"vmid": int(vmid), "newid": int(newid), "node": host_node,
            "action": "clone", "task": sanitize(str(upid), 256)}


def delete_vm(conn: Any, vmid: int, node: str | None = None) -> dict:
    """[WRITE] Destroy a VM permanently. No safe inverse — irreversible."""
    host_node = _find_node_for_vmid(conn, vmid, node)
    upid = conn.nodes(host_node).qemu(vmid).delete()
    return {"vmid": int(vmid), "node": host_node, "action": "delete",
            "task": sanitize(str(upid), 256)}


def migrate_vm(
    conn: Any, vmid: int, target_node: str, node: str | None = None, online: bool = True
) -> dict:
    """[WRITE] Migrate a VM to another node. Returns the task UPID.

    Records the source node so the harness can record the reverse migration as
    the undo token.
    """
    host_node = _find_node_for_vmid(conn, vmid, node)
    upid = conn.nodes(host_node).qemu(vmid).migrate.post(
        target=target_node, online=1 if online else 0
    )
    return {"vmid": int(vmid), "from_node": host_node, "to_node": target_node,
            "action": "migrate", "task": sanitize(str(upid), 256)}


def rollback_snapshot(conn: Any, vmid: int, name: str, node: str | None = None) -> dict:
    """[WRITE] Roll a VM back to a snapshot. No clean inverse (discards changes)."""
    host_node = _find_node_for_vmid(conn, vmid, node)
    upid = conn.nodes(host_node).qemu(vmid).snapshot(name).rollback.post()
    return {"vmid": int(vmid), "node": host_node, "snapshot": sanitize(name, 64),
            "action": "snapshot_rollback", "task": sanitize(str(upid), 256)}
