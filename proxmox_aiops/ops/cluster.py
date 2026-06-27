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


def cluster_resources(conn: Any, resource_type: str | None = None) -> list[dict]:
    """[READ] Aggregate /cluster/resources view of VMs, nodes, and storage.

    ``resource_type`` optionally filters by 'vm', 'node', or 'storage'. This is
    the single-call inventory across the whole cluster.
    """
    endpoint = conn.cluster.resources
    items = endpoint.get(type=resource_type) if resource_type else endpoint.get()
    out: list[dict] = []
    for r in items:
        out.append(
            {
                "id": sanitize(str(r.get("id", "")), 128),
                "type": sanitize(str(r.get("type", "")), 32),
                "name": sanitize(str(r.get("name", "")), 128),
                "node": sanitize(str(r.get("node", "")), 64),
                "status": sanitize(str(r.get("status", "")), 32),
                "vmid": r.get("vmid"),
                "cpu": r.get("cpu"),
                "mem": r.get("mem"),
                "maxmem": r.get("maxmem"),
                "disk": r.get("disk"),
                "maxdisk": r.get("maxdisk"),
            }
        )
    return out


def node_status(conn: Any, node: str) -> dict:
    """[READ] Detailed status for one node: cpu, load average, memory, uptime."""
    if not node:
        raise ValueError("node_status requires a node name. Pass node=<name>.")
    st = conn.nodes(node).status.get()
    mem = st.get("memory", {}) or {}
    return {
        "node": sanitize(str(node), 64),
        "uptime": st.get("uptime"),
        "cpu": st.get("cpu"),
        "loadavg": st.get("loadavg"),
        "mem_total": mem.get("total"),
        "mem_used": mem.get("used"),
        "mem_free": mem.get("free"),
        "pveversion": sanitize(str(st.get("pveversion", "")), 64),
    }


def task_log(
    conn: Any, upid: str, node: str | None = None, limit: int = 200
) -> list[dict]:
    """[READ] Fetch the log lines of an async task by its UPID.

    The node is parsed from the UPID when not given. ``limit`` caps the number
    of lines returned (the runaway breaker also bounds repeated polling).
    """
    host_node = node or _node_from_upid(upid)
    if not host_node:
        raise ValueError(
            f"Could not determine node from UPID {upid!r}; pass node=<name>."
        )
    lines = conn.nodes(host_node).tasks(upid).log.get(limit=int(limit))
    return [
        {"n": ln.get("n"), "t": sanitize(str(ln.get("t", "")), 500)}
        for ln in lines
    ]


def next_vmid(conn: Any) -> dict:
    """[READ] Return a free VMID for a new guest (/cluster/nextid)."""
    vmid = conn.cluster.nextid.get()
    return {"vmid": int(vmid)}
