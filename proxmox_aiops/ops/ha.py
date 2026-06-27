"""High-Availability (HA) read operations for Proxmox VE.

HA is optional — many clusters never configure it. These helpers detect that
case and return a clear "not configured" signal instead of crashing, so an
agent can report the absence rather than surfacing a raw API error.
"""

from __future__ import annotations

from typing import Any

from proxmox_aiops.governance import sanitize


def _ha_not_configured(exc: Exception) -> bool:
    """Heuristic: does this API error mean HA simply isn't set up?"""
    text = str(exc).lower()
    return any(s in text for s in ("not found", "404", "no such", "does not exist"))


def ha_status(conn: Any) -> dict:
    """[READ] Current HA manager/status entries, or a not-configured signal.

    Returns ``{"configured": bool, "entries": [...]}``. When HA is absent the
    entries list is empty and a ``message`` explains it (no crash).
    """
    try:
        items = conn.cluster.ha.status.current.get()
    except Exception as exc:  # noqa: BLE001 — translated to a clear signal
        if _ha_not_configured(exc):
            return {
                "configured": False,
                "entries": [],
                "message": "Proxmox HA is not configured on this cluster.",
            }
        raise
    entries = [
        {
            "id": sanitize(str(i.get("id", "")), 128),
            "type": sanitize(str(i.get("type", "")), 32),
            "node": sanitize(str(i.get("node", "")), 64),
            "status": sanitize(str(i.get("status", "")), 64),
            "quorate": i.get("quorate"),
        }
        for i in items
    ]
    return {"configured": bool(entries), "entries": entries}


def ha_resource_list(conn: Any) -> list[dict]:
    """[READ] HA-managed resources (VMs/CTs), or empty when HA is not configured."""
    try:
        items = conn.cluster.ha.resources.get()
    except Exception as exc:  # noqa: BLE001 — translated to an empty list
        if _ha_not_configured(exc):
            return []
        raise
    return [
        {
            "sid": sanitize(str(r.get("sid", "")), 128),
            "type": sanitize(str(r.get("type", "")), 32),
            "state": sanitize(str(r.get("state", "")), 32),
            "group": sanitize(str(r.get("group", "")), 64),
            "max_restart": r.get("max_restart"),
            "max_relocate": r.get("max_relocate"),
        }
        for r in items
    ]
