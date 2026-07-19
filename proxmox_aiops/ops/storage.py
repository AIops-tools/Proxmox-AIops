"""Storage read operations for Proxmox VE."""

from __future__ import annotations

from typing import Any

from proxmox_aiops.connection import get_default_node
from proxmox_aiops.governance import opt_str

# Single shared exception type: cli/_common.py and mcp_server/_shared.py catch
# the vm_lifecycle class — a local duplicate here would dodge those handlers
# and dump raw tracebacks (the storage-list-without-node bug).
from proxmox_aiops.ops.vm_lifecycle import NodeRequiredError

__all__ = ["NodeRequiredError", "list_storage", "list_storage_content"]


def list_storage(conn: Any, node: str | None = None) -> list[dict]:
    """[READ] List storage pools visible on a node (name, type, usage).

    Returns a high-signal summary: storage id, type, enabled/active flags,
    and total/used/avail bytes. Pass node=<name> or rely on the configured
    default target node.
    """
    resolved = node or get_default_node(conn)
    if not resolved:
        raise NodeRequiredError(
            "No node specified and no default node configured. Pass node=<name> "
            "or set 'node' on the target in config.yaml."
        )
    out: list[dict] = []
    for s in conn.nodes(resolved).storage.get():
        out.append(
            {
                "storage": opt_str(s.get("storage"), 64),
                "type": opt_str(s.get("type"), 32),
                "active": s.get("active"),
                "enabled": s.get("enabled"),
                "total": s.get("total"),
                "used": s.get("used"),
                "avail": s.get("avail"),
                "node": resolved,
            }
        )
    return out


def list_storage_content(
    conn: Any, storage: str, node: str | None = None, content: str | None = None
) -> list[dict]:
    """[READ] List volumes on a storage pool (ISOs, disk images, backups, templates).

    ``content`` optionally filters by type (e.g. 'iso', 'images', 'backup',
    'vztmpl'). Pass node=<name> or rely on the configured default node.
    """
    resolved = node or get_default_node(conn)
    if not resolved:
        raise NodeRequiredError(
            "No node specified and no default node configured. Pass node=<name>."
        )
    endpoint = conn.nodes(resolved).storage(storage).content
    items = endpoint.get(content=content) if content else endpoint.get()
    out: list[dict] = []
    for v in items:
        out.append(
            {
                "volid": opt_str(v.get("volid"), 256),
                "content": opt_str(v.get("content"), 32),
                "format": opt_str(v.get("format"), 32),
                "size": v.get("size"),
                "vmid": v.get("vmid"),
            }
        )
    return out
