"""``proxmox-aiops ct ...`` sub-commands for LXC containers."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from mcp_server.tools import lxc as gov
from proxmox_aiops.cli._common import (
    DryRunOption,
    NodeOption,
    TargetOption,
    cli_errors,
    double_confirm,
    dry_run_print,
    get_connection,
)
from proxmox_aiops.ops import lxc

ct_app = typer.Typer(help="LXC container operations.", no_args_is_help=True)
console = Console()


@ct_app.command("list")
@cli_errors
def ct_list(target: TargetOption = None, node: NodeOption = None) -> None:
    """List LXC containers (name, vmid, status, cpu, mem)."""
    conn, _ = get_connection(target)
    table = Table(title="Proxmox Containers")
    for col in ("vmid", "name", "status", "cpu", "mem", "node"):
        table.add_column(col)
    for r in lxc.list_cts(conn, node=node):
        table.add_row(
            str(r["vmid"]), r["name"], r["status"],
            str(r.get("cpu")), str(r.get("mem")), r["node"],
        )
    console.print(table)


@ct_app.command("start")
@cli_errors
def ct_start(vmid: int, target: TargetOption = None, node: NodeOption = None) -> None:
    """Start an LXC container."""
    result = gov.ct_start(vmid=vmid, target=target, node=node)
    console.print(f"[green]Started container {vmid}[/] (task: {result['task']})")


@ct_app.command("stop")
@cli_errors
def ct_stop(
    vmid: int, target: TargetOption = None, node: NodeOption = None,
    dry_run: DryRunOption = False,
) -> None:
    """Stop an LXC container (destructive — double confirm)."""
    if dry_run:
        dry_run_print(operation="stop_ct", api_call=f"lxc({vmid}).status.stop.post()")
        return
    double_confirm("stop", f"container {vmid}")
    result = gov.ct_stop(vmid=vmid, target=target, node=node)
    console.print(f"[green]Stopped container {vmid}[/] (task: {result['task']})")
