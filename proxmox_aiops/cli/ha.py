"""``proxmox-aiops ha ...`` sub-commands (read-only HA status)."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from proxmox_aiops.cli._common import TargetOption, cli_errors, get_connection
from proxmox_aiops.ops import ha

ha_app = typer.Typer(help="High-Availability read operations.", no_args_is_help=True)
console = Console()


@ha_app.command("status")
@cli_errors
def ha_status(target: TargetOption = None) -> None:
    """Show HA status (or a not-configured notice)."""
    conn, _ = get_connection(target)
    result = ha.ha_status(conn)
    if not result["configured"]:
        console.print(f"[yellow]{result.get('message', 'HA not configured.')}[/]")
        return
    for e in result["entries"]:
        console.print(f"  [cyan]{e['type']}[/] {e['id']} node={e['node']} "
                      f"status={e['status']}")


@ha_app.command("resources")
@cli_errors
def ha_resources(target: TargetOption = None) -> None:
    """List HA-managed resources."""
    conn, _ = get_connection(target)
    rows = ha.ha_resource_list(conn)
    if not rows:
        console.print("[yellow]No HA resources (HA not configured or none defined).[/]")
        return
    table = Table(title="HA resources")
    for col in ("sid", "type", "state", "group"):
        table.add_column(col)
    for r in rows:
        table.add_row(r["sid"], r["type"], r["state"], r["group"])
    console.print(table)
