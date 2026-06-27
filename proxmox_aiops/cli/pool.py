"""``proxmox-aiops pool ...`` sub-commands (read-only resource pools)."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from proxmox_aiops.cli._common import TargetOption, cli_errors, get_connection
from proxmox_aiops.ops import pool

pool_app = typer.Typer(help="Resource-pool read operations.", no_args_is_help=True)
console = Console()


@pool_app.command("list")
@cli_errors
def pool_list(target: TargetOption = None) -> None:
    """List resource pools."""
    conn, _ = get_connection(target)
    table = Table(title="Resource pools")
    table.add_column("poolid")
    table.add_column("comment")
    for p in pool.pool_list(conn):
        table.add_row(p["poolid"], p["comment"])
    console.print(table)


@pool_app.command("members")
@cli_errors
def pool_members(poolid: str, target: TargetOption = None) -> None:
    """List members of a pool."""
    conn, _ = get_connection(target)
    data = pool.pool_members(conn, poolid)
    console.print(f"[cyan]Pool {data['poolid']}[/] {data['comment']}")
    table = Table(title=f"Members — {poolid}")
    for col in ("type", "id", "node", "vmid", "status"):
        table.add_column(col)
    for m in data["members"]:
        table.add_row(m["type"], m["id"], m["node"], str(m.get("vmid")), m["status"])
    console.print(table)
