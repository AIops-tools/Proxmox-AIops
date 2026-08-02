"""High-Availability (HA) read operations for Proxmox VE.

HA is optional — many clusters never configure it. These helpers detect that
case and return a clear "not configured" signal instead of crashing, so an
agent can report the absence rather than surfacing a raw API error.
"""

from __future__ import annotations

from typing import Any

from proxmox_aiops.governance import opt_str


def _ha_not_configured(exc: Exception) -> bool:
    """Heuristic: does this API error mean HA simply isn't set up?"""
    text = str(exc).lower()
    return any(s in text for s in ("not found", "404", "no such", "does not exist"))


def ha_status(conn: Any) -> dict:
    """[READ] Current HA manager/status entries, or a not-configured signal.

    Returns ``{"configured": bool, "entries": [...]}``. ``configured`` means
    "HA actually manages something", which is decided by the presence of
    ``service`` entries — NOT by the list being non-empty. Every quorate
    cluster answers this endpoint with a synthetic ``quorum`` row (and, once
    the HA stack has ever run, ``master``/``lrm`` rows) even when zero
    resources are defined, so a truthiness test on the list reports HA as
    configured on every cluster in existence.
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
            "id": opt_str(i.get("id"), 128),
            "type": opt_str(i.get("type"), 32),
            "node": opt_str(i.get("node"), 64),
            "status": opt_str(i.get("status"), 64),
            "quorate": i.get("quorate"),
            # Service rows carry the desired/actual state as real fields. They
            # used to be reachable only by parsing the human ``status`` string
            # ("vm:900 (pve1, started)"); the keys stay present, null-valued,
            # on the stack rows that have no state.
            "state": opt_str(i.get("state"), 32),
            "requestState": opt_str(i.get("request_state"), 32),
        }
        for i in items
    ]
    services = [e for e in entries if e["type"] == "service"]
    result: dict = {"configured": bool(services), "entries": entries}
    if not services:
        result["message"] = (
            "Proxmox HA manages no resources here. The entries describe the HA "
            "stack itself (quorum/master/lrm), which every cluster reports. "
            "Define one with 'ha-manager add <sid>' before relying on HA."
        )
    return result


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
            "sid": opt_str(r.get("sid"), 128),
            "type": opt_str(r.get("type"), 32),
            "state": opt_str(r.get("state"), 32),
            "group": opt_str(r.get("group"), 64),
            "max_restart": r.get("max_restart"),
            "max_relocate": r.get("max_relocate"),
        }
        for r in items
    ]
