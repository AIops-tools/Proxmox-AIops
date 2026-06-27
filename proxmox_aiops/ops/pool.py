"""Resource-pool read operations for Proxmox VE.

Pools group VMs/CTs/storage for permission and organization purposes. These
read helpers list pools and their members.
"""

from __future__ import annotations

from typing import Any

from proxmox_aiops.governance import sanitize


def pool_list(conn: Any) -> list[dict]:
    """[READ] List resource pools (poolid + comment)."""
    out: list[dict] = []
    for p in conn.pools.get():
        out.append(
            {
                "poolid": sanitize(str(p.get("poolid", "")), 64),
                "comment": sanitize(str(p.get("comment", "")), 200),
            }
        )
    return out


def pool_members(conn: Any, poolid: str) -> dict:
    """[READ] List members of a pool (VMs, CTs, storage) with the pool comment."""
    if not poolid:
        raise ValueError("pool_members requires a poolid. See pool_list.")
    data = conn.pools(poolid).get()
    members = [
        {
            "id": sanitize(str(m.get("id", "")), 128),
            "type": sanitize(str(m.get("type", "")), 32),
            "node": sanitize(str(m.get("node", "")), 64),
            "vmid": m.get("vmid"),
            "storage": sanitize(str(m.get("storage", "")), 64),
            "status": sanitize(str(m.get("status", "")), 32),
        }
        for m in (data.get("members", []) or [])
    ]
    return {
        "poolid": sanitize(str(poolid), 64),
        "comment": sanitize(str(data.get("comment", "")), 200),
        "members": members,
    }
