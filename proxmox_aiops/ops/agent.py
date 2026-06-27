"""QEMU guest-agent read operations for Proxmox VE.

Only the non-mutating ``ping`` probe is exposed — guest command execution
(``agent exec``) is intentionally omitted as too risky for an automated tool.
A ping tells you whether the qemu-guest-agent is installed and responsive
inside the VM; absence is reported, never crashed on.
"""

from __future__ import annotations

from typing import Any

from proxmox_aiops.governance import sanitize
from proxmox_aiops.ops.vm_lifecycle import _find_node_for_vmid


def agent_ping(conn: Any, vmid: int, node: str | None = None) -> dict:
    """[READ] Ping the QEMU guest agent of a VM.

    Returns ``{"vmid", "node", "responsive": bool, "message"?}``. A non-running
    or absent agent yields ``responsive=False`` with an explanation instead of
    an error.
    """
    host_node = _find_node_for_vmid(conn, vmid, node)
    try:
        conn.nodes(host_node).qemu(vmid).agent.ping.post()
    except Exception as exc:  # noqa: BLE001 — absence is a normal, reportable state
        return {
            "vmid": int(vmid),
            "node": host_node,
            "responsive": False,
            "message": sanitize(
                "Guest agent did not respond (not installed, not running, or "
                f"VM stopped): {exc}",
                300,
            ),
        }
    return {"vmid": int(vmid), "node": host_node, "responsive": True}
