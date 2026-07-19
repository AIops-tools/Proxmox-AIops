"""Resource-pool read operations for Proxmox VE.

Pools group VMs/CTs/storage for permission and organization purposes. These
read helpers list pools and their members.
"""

from __future__ import annotations

from typing import Any

from proxmox_aiops.governance import opt_str, sanitize


def pool_list(conn: Any) -> list[dict]:
    """[READ] List resource pools (poolid + comment)."""
    out: list[dict] = []
    for p in conn.pools.get():
        out.append(
            {
                "poolid": opt_str(p.get("poolid"), 64),
                "comment": opt_str(p.get("comment"), 200),
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
            "id": opt_str(m.get("id"), 128),
            "type": opt_str(m.get("type"), 32),
            "node": opt_str(m.get("node"), 64),
            "vmid": m.get("vmid"),
            "storage": opt_str(m.get("storage"), 64),
            "status": opt_str(m.get("status"), 32),
        }
        for m in (data.get("members", []) or [])
    ]
    return {
        "poolid": sanitize(str(poolid), 64),
        "comment": opt_str(data.get("comment"), 200),
        "members": members,
    }
