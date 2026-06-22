"""Cluster, node, and async-task operations for Proxmox VE.

Proxmox write operations (clone, migrate, backup, snapshot) are asynchronous:
they return a UPID task id that you poll. ``get_task_status`` is the Proxmox
the task-poll primitive — it lets an agent check a
long-running task once instead of looping (which, combined with the
proxmox-aiops runaway breaker, is the structural answer to the "poll a slow op,
burn tokens" failure mode).
"""

from __future__ import annotations

from typing import Any

from proxmox_aiops.governance import sanitize


def list_nodes(conn: Any) -> list[dict]:
    """[READ] List cluster nodes with status, cpu load, and memory."""
    out: list[dict] = []
    for n in conn.nodes.get():
        out.append(
            {
                "node": sanitize(str(n.get("node", "")), 64),
                "status": sanitize(str(n.get("status", "")), 32),
                "cpu": n.get("cpu"),
                "maxcpu": n.get("maxcpu"),
                "mem": n.get("mem"),
                "maxmem": n.get("maxmem"),
                "uptime": n.get("uptime"),
            }
        )
    return out


def cluster_status(conn: Any) -> list[dict]:
    """[READ] Return cluster membership + quorum status.

    Each entry is a cluster or node record; the ``quorate`` field on the
    ``type=cluster`` row tells you whether the cluster currently has quorum.
    """
    out: list[dict] = []
    for item in conn.cluster.status.get():
        out.append(
            {
                "type": sanitize(str(item.get("type", "")), 32),
                "name": sanitize(str(item.get("name", "")), 64),
                "online": item.get("online"),
                "quorate": item.get("quorate"),
                "nodes": item.get("nodes"),
                "level": sanitize(str(item.get("level", "")), 32),
            }
        )
    return out


def _node_from_upid(upid: str) -> str | None:
    """Extract the node name from a UPID (``UPID:<node>:...``)."""
    parts = str(upid).split(":")
    return parts[1] if len(parts) > 2 and parts[0] == "UPID" else None


def get_task_status(conn: Any, upid: str, node: str | None = None) -> dict:
    """[READ] Poll a Proxmox async task by its UPID.

    Use after a clone / migrate / backup / snapshot call returns a task id to
    check whether it has finished, instead of re-issuing the operation. The
    node is parsed from the UPID when not given.
    """
    host_node = node or _node_from_upid(upid)
    if not host_node:
        raise ValueError(
            f"Could not determine node from UPID {upid!r}; pass node=<name>."
        )
    status = conn.nodes(host_node).tasks(upid).status.get()
    return {
        "upid": sanitize(str(upid), 256),
        "node": sanitize(str(host_node), 64),
        "type": sanitize(str(status.get("type", "")), 64),
        "status": sanitize(str(status.get("status", "")), 32),
        "exitstatus": sanitize(str(status.get("exitstatus", "")), 64),
    }
