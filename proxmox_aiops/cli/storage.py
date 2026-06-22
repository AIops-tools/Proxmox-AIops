"""``proxmox-aiops storage ...`` sub-commands."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from proxmox_aiops.cli._common import NodeOption, TargetOption, cli_errors, get_connection
from proxmox_aiops.ops import storage as st

storage_app = typer.Typer(help="Storage read operations.", no_args_is_help=True)
console = Console()


@storage_app.command("list")
@cli_errors
def storage_list(target: TargetOption = None, node: NodeOption = None) -> None:
    """List storage pools visible on a node."""
    conn, _ = get_connection(target)
    rows = st.list_storage(conn, node=node)
    table = Table(title="Proxmox Storage")
    for col in ("storage", "type", "active", "total", "used", "avail"):
        table.add_column(col)
    for r in rows:
        table.add_row(
            r["storage"], r["type"], str(r.get("active")),
            str(r.get("total")), str(r.get("used")), str(r.get("avail")),
        )
    console.print(table)


@storage_app.command("content")
@cli_errors
def storage_content(
    storage: str,
    content: str = typer.Option(None, "--content", help="Filter: iso/images/backup/vztmpl"),
    target: TargetOption = None,
    node: NodeOption = None,
) -> None:
    """List volumes on a storage pool (ISOs, disk images, backups, templates)."""
    conn, _ = get_connection(target)
    rows = st.list_storage_content(conn, storage, node=node, content=content)
    table = Table(title=f"Storage content — {storage}")
    for col in ("volid", "content", "format", "size", "vmid"):
        table.add_column(col)
    for r in rows:
        table.add_row(
            r["volid"], r["content"], r["format"], str(r.get("size")), str(r.get("vmid")),
        )
    console.print(table)
