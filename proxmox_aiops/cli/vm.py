"""``proxmox-aiops vm ...`` sub-commands."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from proxmox_aiops.cli._common import (
    DryRunOption,
    NodeOption,
    TargetOption,
    cli_errors,
    double_confirm,
    dry_run_print,
    get_connection,
)
from proxmox_aiops.ops import vm_lifecycle as vl

vm_app = typer.Typer(help="QEMU VM lifecycle operations.", no_args_is_help=True)
console = Console()


@vm_app.command("list")
@cli_errors
def vm_list(target: TargetOption = None, node: NodeOption = None) -> None:
    """List VMs (name, vmid, status, cpu, mem)."""
    conn, _ = get_connection(target)
    rows = vl.list_vms(conn, node=node)
    table = Table(title="Proxmox VMs")
    for col in ("vmid", "name", "status", "cpu", "mem", "node"):
        table.add_column(col)
    for r in rows:
        table.add_row(
            str(r["vmid"]), r["name"], r["status"],
            str(r.get("cpu")), str(r.get("mem")), r["node"],
        )
    console.print(table)


@vm_app.command("get")
@cli_errors
def vm_get(vmid: int, target: TargetOption = None, node: NodeOption = None) -> None:
    """Show status detail for one VM."""
    conn, _ = get_connection(target)
    info = vl.get_vm(conn, vmid, node=node)
    for k, v in info.items():
        console.print(f"  [cyan]{k}:[/] {v}")


@vm_app.command("start")
@cli_errors
def vm_start(vmid: int, target: TargetOption = None, node: NodeOption = None) -> None:
    """Start a VM."""
    conn, _ = get_connection(target)
    result = vl.start_vm(conn, vmid, node=node)
    console.print(f"[green]Started VM {vmid}[/] (task: {result['task']})")


@vm_app.command("stop")
@cli_errors
def vm_stop(
    vmid: int,
    target: TargetOption = None,
    node: NodeOption = None,
    dry_run: DryRunOption = False,
) -> None:
    """Hard-stop a VM (destructive — double confirm)."""
    if dry_run:
        dry_run_print(operation="stop_vm", api_call=f"qemu({vmid}).status.stop.post()")
        return
    double_confirm("stop", f"VM {vmid}")
    conn, _ = get_connection(target)
    result = vl.stop_vm(conn, vmid, node=node)
    console.print(f"[green]Stopped VM {vmid}[/] (task: {result['task']})")


@vm_app.command("snapshot-create")
@cli_errors
def vm_snapshot_create(
    vmid: int,
    name: str = typer.Option(..., "--name", help="Snapshot name"),
    target: TargetOption = None,
    node: NodeOption = None,
) -> None:
    """Create a named snapshot."""
    conn, _ = get_connection(target)
    result = vl.snapshot_create(conn, vmid, name, node=node)
    console.print(f"[green]Created snapshot '{name}' on VM {vmid}[/] (task: {result['task']})")


@vm_app.command("snapshot-delete")
@cli_errors
def vm_snapshot_delete(
    vmid: int,
    name: str = typer.Option(..., "--name", help="Snapshot name"),
    target: TargetOption = None,
    node: NodeOption = None,
    dry_run: DryRunOption = False,
) -> None:
    """Delete a named snapshot (destructive — double confirm)."""
    if dry_run:
        dry_run_print(
            operation="snapshot_delete",
            api_call=f"qemu({vmid}).snapshot({name!r}).delete()",
        )
        return
    double_confirm("delete snapshot", f"{name} on VM {vmid}")
    conn, _ = get_connection(target)
    result = vl.snapshot_delete(conn, vmid, name, node=node)
    console.print(f"[green]Deleted snapshot '{name}' on VM {vmid}[/] (task: {result['task']})")


@vm_app.command("snapshot-list")
@cli_errors
def vm_snapshot_list(vmid: int, target: TargetOption = None, node: NodeOption = None) -> None:
    """List snapshots for a VM."""
    conn, _ = get_connection(target)
    snaps = vl.list_snapshots(conn, vmid, node=node)
    table = Table(title=f"Snapshots — VM {vmid}")
    table.add_column("name")
    table.add_column("description")
    for s in snaps:
        table.add_row(s["name"], s["description"])
    console.print(table)


@vm_app.command("config")
@cli_errors
def vm_config(vmid: int, target: TargetOption = None, node: NodeOption = None) -> None:
    """Show a VM's config (cores, memory, ostype, boot)."""
    conn, _ = get_connection(target)
    for k, v in vl.get_vm_config(conn, vmid, node=node).items():
        console.print(f"  [cyan]{k}:[/] {v}")


@vm_app.command("shutdown")
@cli_errors
def vm_shutdown(
    vmid: int, target: TargetOption = None, node: NodeOption = None,
    dry_run: DryRunOption = False,
) -> None:
    """Graceful shutdown (vs hard stop)."""
    if dry_run:
        dry_run_print(operation="shutdown_vm", api_call=f"qemu({vmid}).status.shutdown.post()")
        return
    conn, _ = get_connection(target)
    result = vl.shutdown_vm(conn, vmid, node=node)
    console.print(f"[green]Shutdown requested for VM {vmid}[/] (task: {result['task']})")


@vm_app.command("reboot")
@cli_errors
def vm_reboot(vmid: int, target: TargetOption = None, node: NodeOption = None) -> None:
    """Reboot a VM (graceful)."""
    conn, _ = get_connection(target)
    result = vl.reboot_vm(conn, vmid, node=node)
    console.print(f"[green]Reboot requested for VM {vmid}[/] (task: {result['task']})")


@vm_app.command("reconfigure")
@cli_errors
def vm_reconfigure(
    vmid: int,
    cores: int = typer.Option(None, "--cores", help="New vCPU core count"),
    memory: int = typer.Option(None, "--memory", help="New memory (MiB)"),
    target: TargetOption = None,
    node: NodeOption = None,
    dry_run: DryRunOption = False,
) -> None:
    """Change a VM's cores and/or memory."""
    if dry_run:
        dry_run_print(operation="reconfigure_vm", api_call=f"qemu({vmid}).config.post()",
                      parameters={"cores": cores, "memory": memory})
        return
    conn, _ = get_connection(target)
    result = vl.reconfigure_vm(conn, vmid, cores=cores, memory=memory, node=node)
    console.print(f"[green]Reconfigured VM {vmid}[/] applied={result['applied']} "
                  f"(was {result['previous']})")


@vm_app.command("clone")
@cli_errors
def vm_clone(
    vmid: int,
    newid: int = typer.Option(..., "--newid", help="New VM id for the clone"),
    name: str = typer.Option(None, "--name", help="Name for the clone"),
    target: TargetOption = None,
    node: NodeOption = None,
) -> None:
    """Clone a VM to a new vmid (async — poll with 'cluster task-status')."""
    conn, _ = get_connection(target)
    result = vl.clone_vm(conn, vmid, newid, name=name, node=node)
    console.print(f"[green]Clone {vmid} → {newid} started[/] (task: {result['task']})")


@vm_app.command("delete")
@cli_errors
def vm_delete(
    vmid: int, target: TargetOption = None, node: NodeOption = None,
    dry_run: DryRunOption = False,
) -> None:
    """Destroy a VM permanently (destructive — double confirm)."""
    if dry_run:
        dry_run_print(operation="delete_vm", api_call=f"qemu({vmid}).delete()")
        return
    double_confirm("permanently destroy", f"VM {vmid}")
    conn, _ = get_connection(target)
    result = vl.delete_vm(conn, vmid, node=node)
    console.print(f"[green]Destroyed VM {vmid}[/] (task: {result['task']})")


@vm_app.command("migrate")
@cli_errors
def vm_migrate(
    vmid: int,
    to_node: str = typer.Option(..., "--to-node", help="Destination node"),
    offline: bool = typer.Option(False, "--offline", help="Migrate while stopped"),
    target: TargetOption = None,
    node: NodeOption = None,
    dry_run: DryRunOption = False,
) -> None:
    """Migrate a VM to another node (async — poll with 'cluster task-status')."""
    if dry_run:
        dry_run_print(operation="migrate_vm", api_call=f"qemu({vmid}).migrate.post()",
                      parameters={"target": to_node, "online": not offline})
        return
    conn, _ = get_connection(target)
    result = vl.migrate_vm(conn, vmid, to_node, node=node, online=not offline)
    console.print(f"[green]Migrating VM {vmid} → {to_node}[/] (task: {result['task']})")


@vm_app.command("snapshot-rollback")
@cli_errors
def vm_snapshot_rollback(
    vmid: int,
    name: str = typer.Option(..., "--name", help="Snapshot to roll back to"),
    target: TargetOption = None,
    node: NodeOption = None,
    dry_run: DryRunOption = False,
) -> None:
    """Roll a VM back to a snapshot (destructive — double confirm)."""
    if dry_run:
        dry_run_print(operation="rollback_snapshot",
                      api_call=f"qemu({vmid}).snapshot({name!r}).rollback.post()")
        return
    double_confirm("roll back (discards newer changes)", f"VM {vmid} → snapshot {name}")
    conn, _ = get_connection(target)
    result = vl.rollback_snapshot(conn, vmid, name, node=node)
    console.print(f"[green]Rolled VM {vmid} back to '{name}'[/] (task: {result['task']})")
