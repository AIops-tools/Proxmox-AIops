"""``proxmox-aiops cluster ...`` sub-commands (read-only)."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from proxmox_aiops.cli._common import NodeOption, TargetOption, cli_errors, get_connection
from proxmox_aiops.ops import cluster as cl

cluster_app = typer.Typer(help="Cluster, node, and task operations.", no_args_is_help=True)
console = Console()


@cluster_app.command("nodes")
@cli_errors
def node_list(target: TargetOption = None) -> None:
    """List cluster nodes (status, cpu, mem, uptime)."""
    conn, _ = get_connection(target)
    table = Table(title="Proxmox Nodes")
    for col in ("node", "status", "cpu", "maxcpu", "mem", "maxmem", "uptime"):
        table.add_column(col)
    for n in cl.list_nodes(conn):
        table.add_row(
            n["node"], n["status"], str(n.get("cpu")), str(n.get("maxcpu")),
            str(n.get("mem")), str(n.get("maxmem")), str(n.get("uptime")),
        )
    console.print(table)


@cluster_app.command("status")
@cli_errors
def cluster_status(target: TargetOption = None) -> None:
    """Show cluster membership + quorum."""
    conn, _ = get_connection(target)
    for item in cl.cluster_status(conn):
        console.print(f"  [cyan]{item['type']}[/] {item['name']} "
                      f"online={item.get('online')} quorate={item.get('quorate')}")


@cluster_app.command("task-status")
@cli_errors
def task_status(upid: str, target: TargetOption = None, node: NodeOption = None) -> None:
    """Poll an async task (clone/migrate/backup) by its UPID."""
    conn, _ = get_connection(target)
    info = cl.get_task_status(conn, upid, node=node)
    for k, v in info.items():
        console.print(f"  [cyan]{k}:[/] {v}")


@cluster_app.command("resources")
@cli_errors
def cluster_resources(
    resource_type: str = typer.Option(
        None, "--type", help="Filter: vm/node/storage"
    ),
    target: TargetOption = None,
) -> None:
    """Aggregate /cluster/resources view (VMs, nodes, storage)."""
    conn, _ = get_connection(target)
    rows = cl.cluster_resources(conn, resource_type=resource_type)
    table = Table(title="Cluster resources")
    for col in ("type", "id", "name", "node", "status", "vmid"):
        table.add_column(col)
    for r in rows:
        table.add_row(
            r["type"], r["id"], r["name"], r["node"], r["status"], str(r.get("vmid")),
        )
    console.print(table)


@cluster_app.command("node-status")
@cli_errors
def node_status(node: str, target: TargetOption = None) -> None:
    """Show detailed status for one node (cpu, load, memory, uptime)."""
    conn, _ = get_connection(target)
    for k, v in cl.node_status(conn, node).items():
        console.print(f"  [cyan]{k}:[/] {v}")


@cluster_app.command("task-log")
@cli_errors
def task_log(
    upid: str,
    limit: int = typer.Option(200, "--limit", help="Max log lines"),
    target: TargetOption = None,
    node: NodeOption = None,
) -> None:
    """Fetch the log of an async task by its UPID."""
    conn, _ = get_connection(target)
    result = cl.task_log(conn, upid, node=node, limit=limit)
    for ln in result["lines"]:
        console.print(f"  {ln.get('n')}: {ln.get('t')}")
    if result["truncated"]:
        console.print(
            f"[yellow]… truncated at {result['returned']} lines — "
            f"re-run with --limit above {result['limit']} for more.[/]"
        )
    elif not result["lines"]:
        console.print("[dim]Task log is empty.[/]")


@cluster_app.command("next-vmid")
@cli_errors
def next_vmid(target: TargetOption = None) -> None:
    """Get a free VMID for a new guest."""
    conn, _ = get_connection(target)
    console.print(f"  [cyan]next free vmid:[/] {cl.next_vmid(conn)['vmid']}")
