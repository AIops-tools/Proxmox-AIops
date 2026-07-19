"""Firewall read operations for Proxmox VE (inspection only).

Intentionally read-only: listing per-VM rules and the cluster firewall enable
state lets an agent audit posture without the risk of editing firewall rules
(which can lock out a node). Rule mutation is deliberately out of scope.
"""

from __future__ import annotations

from typing import Any

from proxmox_aiops.governance import opt_str
from proxmox_aiops.ops.vm_lifecycle import _find_node_for_vmid


def vm_firewall_rules(conn: Any, vmid: int, node: str | None = None) -> list[dict]:
    """[READ] List the firewall rules attached to a VM."""
    host_node = _find_node_for_vmid(conn, vmid, node)
    rules = conn.nodes(host_node).qemu(vmid).firewall.rules.get()
    return [
        {
            "pos": r.get("pos"),
            "type": opt_str(r.get("type"), 16),
            "action": opt_str(r.get("action"), 32),
            "proto": opt_str(r.get("proto"), 16),
            "dport": opt_str(r.get("dport"), 32),
            "source": opt_str(r.get("source"), 64),
            "dest": opt_str(r.get("dest"), 64),
            "enable": r.get("enable"),
            "comment": opt_str(r.get("comment"), 200),
        }
        for r in rules
    ]


def cluster_firewall_status(conn: Any) -> dict:
    """[READ] Cluster-wide firewall options (notably whether it is enabled)."""
    opts = conn.cluster.firewall.options.get()
    return {
        "enable": opts.get("enable"),
        "policy_in": opt_str(opts.get("policy_in"), 32),
        "policy_out": opt_str(opts.get("policy_out"), 32),
        "log_ratelimit": opt_str(opts.get("log_ratelimit"), 64),
    }
