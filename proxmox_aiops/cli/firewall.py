"""``proxmox-aiops firewall ...`` sub-commands (read-only inspection)."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from proxmox_aiops.cli._common import NodeOption, TargetOption, cli_errors, get_connection
from proxmox_aiops.ops import firewall as fw

firewall_app = typer.Typer(help="Firewall read operations.", no_args_is_help=True)
console = Console()


@firewall_app.command("vm-rules")
@cli_errors
def vm_rules(vmid: int, target: TargetOption = None, node: NodeOption = None) -> None:
    """List the firewall rules attached to a VM."""
    conn, _ = get_connection(target)
    rows = fw.vm_firewall_rules(conn, vmid, node=node)
    table = Table(title=f"Firewall rules — VM {vmid}")
    for col in ("pos", "type", "action", "proto", "dport", "source", "dest", "enable"):
        table.add_column(col)
    for r in rows:
        table.add_row(
            str(r.get("pos")), r["type"], r["action"], r["proto"],
            r["dport"], r["source"], r["dest"], str(r.get("enable")),
        )
    console.print(table)


@firewall_app.command("cluster-status")
@cli_errors
def cluster_status(target: TargetOption = None) -> None:
    """Show cluster-wide firewall options (enabled, default policies)."""
    conn, _ = get_connection(target)
    for k, v in fw.cluster_firewall_status(conn).items():
        console.print(f"  [cyan]{k}:[/] {v}")
