"""Flagship signature analyses over Proxmox cluster telemetry (pure analysis).

Proxmox-AIops was born read-heavy (inventory + power ops); these two analyses
bring it to parity with the newer tools in the line, whose differentiator is a
*transparent* RCA: every finding is reported with the measured number that
tripped it, so an operator sees **why** something was flagged — never a
black-box verdict.

  1. ``node_pressure_findings`` — rank cluster nodes by CPU / memory / root-fs
     pressure, each flag citing the measured percentage and a concrete action.
  2. ``guest_health_findings`` — scan VMs and containers for stopped guests,
     memory saturation, and disks near full, each with cause + action.

Both are pure functions (no I/O): pass them the normalized rows from
``ops.cluster.cluster_resources`` (and ``list_nodes``) and they return the
analysis. The MCP / CLI layers do the collection; keeping the heuristics pure
makes them trivially unit-testable without a live cluster.
"""

from __future__ import annotations

from typing import Any

# Thresholds that flip a signal on. Each is surfaced in the finding text next to
# the measured value so the ranking is auditable, not opaque.
CPU_HIGH_PCT = 85.0
MEM_HIGH_PCT = 90.0
DISK_HIGH_PCT = 85.0

# Severity ordering used to rank findings most-urgent first.
_SEVERITY_RANK = {"critical": 0, "warning": 1, "info": 2}


def _pct(used: Any, total: Any) -> float | None:
    """Percentage used, or None when the total is missing / zero."""
    try:
        u = float(used)
        t = float(total)
    except (TypeError, ValueError):
        return None
    if t <= 0:
        return None
    return round(u / t * 100.0, 1)


def _finding(
    severity: str, node: str, signal: str, detail: str, cause: str, action: str
) -> dict:
    """Build one cited finding (immutable dict — callers never mutate it)."""
    return {
        "severity": severity,
        "node": node,
        "signal": signal,
        "detail": detail,
        "cause": cause,
        "action": action,
    }


def _rank(findings: list[dict]) -> list[dict]:
    """Return findings most-urgent first, each carrying its explicit 1-based rank.

    The priority is stated in the payload rather than left implicit in list
    order: a consumer — notably a smaller local model summarising the result —
    should never have to infer urgency from position. Returns new dicts; the
    inputs are not mutated.
    """
    ordered = sorted(findings, key=lambda f: _SEVERITY_RANK.get(f["severity"], 9))
    return [{**finding, "rank": i} for i, finding in enumerate(ordered, 1)]


def node_pressure_findings(node_rows: list[dict]) -> dict:
    """[ANALYSIS] Rank nodes by CPU / memory / root-fs pressure.

    Args:
        node_rows: ``type=node`` rows from ``cluster_resources`` (or ``list_nodes``),
            each with ``node``, ``cpu`` (0-1 fraction), ``mem``/``maxmem``,
            ``disk``/``maxdisk``.

    Returns a dict with the worst-first ``findings`` list and a per-node
    ``summary`` of the measured percentages.
    """
    findings: list[dict] = []
    summary: list[dict] = []
    for r in node_rows:
        node = str(r.get("node") or r.get("name") or "?")
        if str(r.get("status") or "online") == "offline":
            findings.append(_finding(
                "critical", node, "node offline",
                "cluster/resources reports this node offline",
                "The node is down or partitioned from the cluster.",
                "Check the node's power/network; guests on it are unreachable.",
            ))
        cpu_pct = _pct(r.get("cpu"), 1.0) if r.get("cpu") is not None else None
        mem_pct = _pct(r.get("mem"), r.get("maxmem"))
        disk_pct = _pct(r.get("disk"), r.get("maxdisk"))
        summary.append({"node": node, "cpuPct": cpu_pct, "memPct": mem_pct,
                        "diskPct": disk_pct})
        if cpu_pct is not None and cpu_pct >= CPU_HIGH_PCT:
            findings.append(_finding(
                "warning", node, "high CPU",
                f"cpu {cpu_pct}% >= {CPU_HIGH_PCT}%",
                "The node is CPU-saturated; guests may see scheduling latency.",
                "Migrate a busy VM off this node, or investigate a runaway guest.",
            ))
        if mem_pct is not None and mem_pct >= MEM_HIGH_PCT:
            findings.append(_finding(
                "critical" if mem_pct >= 97.0 else "warning", node, "high memory",
                f"mem {mem_pct}% >= {MEM_HIGH_PCT}%",
                "Memory pressure risks ballooning/OOM and blocks new guests.",
                "Migrate a VM off, reduce a guest's assigned RAM, or add memory.",
            ))
        if disk_pct is not None and disk_pct >= DISK_HIGH_PCT:
            findings.append(_finding(
                "critical" if disk_pct >= 95.0 else "warning", node, "root fs near full",
                f"disk {disk_pct}% >= {DISK_HIGH_PCT}%",
                "A full node root filesystem breaks logging, tasks, and backups.",
                "Prune old backups/ISOs/logs on this node or expand its storage.",
            ))
    return {"findings": _rank(findings), "summary": summary,
            "nodesAnalyzed": len(node_rows)}


def guest_health_findings(guest_rows: list[dict]) -> dict:
    """[ANALYSIS] Scan VMs and containers for stopped guests, memory saturation,
    and disks near full.

    Args:
        guest_rows: ``type in {qemu, lxc}`` rows from ``cluster_resources``, each
            with ``name``, ``vmid``, ``node``, ``status``, ``mem``/``maxmem``,
            ``disk``/``maxdisk``.
    """
    findings: list[dict] = []
    stopped: list[dict] = []
    for r in guest_rows:
        name = str(r.get("name") or r.get("id") or "?")
        node = str(r.get("node") or "?")
        vmid = r.get("vmid")
        status = str(r.get("status") or "")
        if status and status != "running":
            stopped.append({"vmid": vmid, "name": name, "node": node, "status": status})
            continue  # a stopped guest has no live mem/disk pressure to rank
        mem_pct = _pct(r.get("mem"), r.get("maxmem"))
        disk_pct = _pct(r.get("disk"), r.get("maxdisk"))
        if mem_pct is not None and mem_pct >= MEM_HIGH_PCT:
            findings.append(_finding(
                "warning", node, "guest memory saturated",
                f"{name} (vmid {vmid}) mem {mem_pct}% >= {MEM_HIGH_PCT}%",
                "The guest is near its assigned RAM ceiling; app latency/OOM risk.",
                f"Raise this guest's memory (vm reconfigure {vmid} --memory ...) "
                f"or investigate a leak inside it.",
            ))
        if disk_pct is not None and disk_pct >= DISK_HIGH_PCT:
            findings.append(_finding(
                "critical" if disk_pct >= 95.0 else "warning", node,
                "guest disk near full",
                f"{name} (vmid {vmid}) disk {disk_pct}% >= {DISK_HIGH_PCT}%",
                "A full guest disk causes write failures inside the guest OS.",
                f"Grow the disk (vm resize-disk {vmid} --disk <k> --size +NG) "
                f"then extend the filesystem inside the guest.",
            ))
    return {"findings": _rank(findings), "stopped": stopped,
            "guestsAnalyzed": len(guest_rows)}
