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

from proxmox_aiops.governance import opt_str, sanitize


def list_nodes(conn: Any) -> list[dict]:
    """[READ] List cluster nodes with status, cpu load, and memory."""
    out: list[dict] = []
    for n in conn.nodes.get():
        out.append(
            {
                "node": opt_str(n.get("node"), 64),
                "status": opt_str(n.get("status"), 32),
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
                "type": opt_str(item.get("type"), 32),
                "name": opt_str(item.get("name"), 64),
                "online": item.get("online"),
                "quorate": item.get("quorate"),
                "nodes": item.get("nodes"),
                "level": opt_str(item.get("level"), 32),
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
        "type": opt_str(status.get("type"), 64),
        "status": opt_str(status.get("status"), 32),
        "exitstatus": opt_str(status.get("exitstatus"), 64),
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
                "id": opt_str(r.get("id"), 128),
                "type": opt_str(r.get("type"), 32),
                "name": opt_str(r.get("name"), 128),
                "node": opt_str(r.get("node"), 64),
                "status": opt_str(r.get("status"), 32),
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
        "pveversion": opt_str(st.get("pveversion"), 64),
    }


def task_log(
    conn: Any, upid: str, node: str | None = None, limit: int = 200
) -> dict:
    """[READ] Fetch the log lines of an async task by its UPID.

    The node is parsed from the UPID when not given. ``limit`` caps the number
    of lines returned (the runaway breaker also bounds repeated polling).

    Returns an envelope rather than a bare list::

        {"lines": [...], "returned": 200, "limit": 200, "truncated": true}

    so a truncated read announces itself. A bare list cannot say "there is
    more" — the consumer has to infer it from the length happening to equal the
    limit, and a smaller local model faced with a long result tends to report
    that nothing came back at all. One extra line is requested so ``truncated``
    is *measured* rather than guessed from a length coincidence.
    """
    host_node = node or _node_from_upid(upid)
    if not host_node:
        raise ValueError(
            f"Could not determine node from UPID {upid!r}; pass node=<name>."
        )
    requested = int(limit)
    raw = list(conn.nodes(host_node).tasks(upid).log.get(limit=requested + 1))
    truncated = len(raw) > requested
    lines = [
        {"n": ln.get("n"), "t": opt_str(ln.get("t"), 500)}
        for ln in raw[:requested]
    ]
    return {
        "lines": lines,
        "returned": len(lines),
        "limit": requested,
        "truncated": truncated,
    }


def next_vmid(conn: Any) -> dict:
    """[READ] Return a free VMID for a new guest (/cluster/nextid)."""
    vmid = conn.cluster.nextid.get()
    return {"vmid": int(vmid)}
