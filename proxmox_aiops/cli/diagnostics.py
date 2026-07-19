"""``proxmox-aiops diagnose ...`` sub-commands — read-only RCA over the cluster."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from proxmox_aiops.cli._common import TargetOption, cli_errors, get_connection
from proxmox_aiops.ops import cluster as cl
from proxmox_aiops.ops import diagnostics as diag

diagnose_app = typer.Typer(
    help="Read-only diagnostics / RCA over the cluster.", no_args_is_help=True
)
console = Console()

_SEVERITY_STYLE = {"critical": "red", "warning": "yellow", "info": "cyan"}
_GUEST_TYPES = {"qemu", "lxc"}


def _print_findings(findings: list[dict]) -> None:
    """Render worst-first findings as a table, or a green all-clear line."""
    if not findings:
        console.print("[green]No pressure findings — all measured values under threshold.[/]")
        return
    table = Table(title="Findings (worst first)")
    for col in ("severity", "node", "signal", "detail", "action"):
        table.add_column(col, overflow="fold")
    for f in findings:
        style = _SEVERITY_STYLE.get(f["severity"], "white")
        table.add_row(
            f"[{style}]{f['severity']}[/]", f.get("node", ""),
            f["signal"], f["detail"], f["action"],
        )
    console.print(table)


@diagnose_app.command("node-pressure")
@cli_errors
def diagnose_node_pressure(target: TargetOption = None) -> None:
    """Rank nodes by CPU / memory / root-fs pressure (worst first)."""
    conn, _ = get_connection(target)
    node_rows = cl.cluster_resources(conn, resource_type="node")
    result = diag.node_pressure_findings(node_rows)
    console.print(f"[bold]Analyzed {result['nodesAnalyzed']} node(s).[/]")
    _print_findings(result["findings"])


@diagnose_app.command("guest-health")
@cli_errors
def diagnose_guest_health(target: TargetOption = None) -> None:
    """Scan VMs/containers for stopped guests, memory saturation, disks near full."""
    conn, _ = get_connection(target)
    rows = cl.cluster_resources(conn)
    guest_rows = [r for r in rows if str(r.get("type")) in _GUEST_TYPES]
    result = diag.guest_health_findings(guest_rows)
    console.print(f"[bold]Analyzed {result['guestsAnalyzed']} guest(s).[/]")
    _print_findings(result["findings"])
    stopped = result["stopped"]
    if stopped:
        console.print(f"[dim]Stopped guests ({len(stopped)}): " +
                      ", ".join(f"{g['name']}({g['vmid']})" for g in stopped) + "[/]")
