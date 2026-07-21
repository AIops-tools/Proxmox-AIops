"""``proxmox-aiops vm ...`` sub-commands."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from mcp_server.tools import disk as gov_disk
from mcp_server.tools import vm as gov
from proxmox_aiops.cli._common import (
    DryRunOption,
    NodeOption,
    TargetOption,
    cli_errors,
    double_confirm,
    dry_run_preview,
    dry_run_print,
    get_connection,
)
from proxmox_aiops.ops import agent as ag
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
    result = gov.vm_start(vmid=vmid, target=target, node=node)
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
        dry_run_preview(
            gov.vm_stop(vmid=vmid, dry_run=True, target=target, node=node),
            operation="stop_vm", api_call=f"qemu({vmid}).status.stop.post()")
        return
    double_confirm("stop", f"VM {vmid}")
    result = gov.vm_stop(vmid=vmid, target=target, node=node)
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
    result = gov.vm_snapshot_create(vmid=vmid, name=name, target=target, node=node)
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
        dry_run_preview(
            gov.vm_snapshot_delete(vmid=vmid, name=name, dry_run=True, target=target, node=node),
            operation="snapshot_delete",
            api_call=f"qemu({vmid}).snapshot({name!r}).delete()",
        )
        return
    double_confirm("delete snapshot", f"{name} on VM {vmid}")
    result = gov.vm_snapshot_delete(vmid=vmid, name=name, target=target, node=node)
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
        dry_run_preview(
            gov.vm_shutdown(vmid=vmid, dry_run=True, target=target, node=node),
            operation="shutdown_vm", api_call=f"qemu({vmid}).status.shutdown.post()")
        return
    result = gov.vm_shutdown(vmid=vmid, target=target, node=node)
    console.print(f"[green]Shutdown requested for VM {vmid}[/] (task: {result['task']})")


@vm_app.command("reboot")
@cli_errors
def vm_reboot(vmid: int, target: TargetOption = None, node: NodeOption = None) -> None:
    """Reboot a VM (graceful)."""
    result = gov.vm_reboot(vmid=vmid, target=target, node=node)
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
        # NOT routed through the governed twin: vm_reconfigure takes no dry_run
        # parameter, so calling it would perform the write this branch exists to
        # avoid. Adding that parameter to the twin is the fix; until then this
        # preview is unguarded and unaudited. See vm_move_disk for the same case.
        dry_run_print(operation="reconfigure_vm", api_call=f"qemu({vmid}).config.post()",
                      parameters={"cores": cores, "memory": memory})
        return
    result = gov.vm_reconfigure(
        vmid=vmid, cores=cores, memory=memory, target=target, node=node
    )
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
    result = gov.vm_clone(vmid=vmid, newid=newid, name=name, target=target, node=node)
    console.print(f"[green]Clone {vmid} → {newid} started[/] (task: {result['task']})")


@vm_app.command("delete")
@cli_errors
def vm_delete(
    vmid: int, target: TargetOption = None, node: NodeOption = None,
    dry_run: DryRunOption = False,
) -> None:
    """Destroy a VM permanently (destructive — double confirm)."""
    if dry_run:
        dry_run_preview(
            gov.vm_delete(vmid=vmid, dry_run=True, target=target, node=node),
            operation="delete_vm", api_call=f"qemu({vmid}).delete()")
        return
    double_confirm("permanently destroy", f"VM {vmid}")
    result = gov.vm_delete(vmid=vmid, target=target, node=node)
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
        dry_run_preview(
            gov.vm_migrate(vmid=vmid, target_node=to_node, online=not offline,
                           dry_run=True, target=target, node=node),
            operation="migrate_vm", api_call=f"qemu({vmid}).migrate.post()",
            parameters={"target": to_node, "online": not offline})
        return
    result = gov.vm_migrate(
        vmid=vmid, target_node=to_node, online=not offline, target=target, node=node
    )
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
        dry_run_preview(
            gov.vm_snapshot_rollback(vmid=vmid, name=name, dry_run=True,
                                     target=target, node=node),
            operation="rollback_snapshot",
            api_call=f"qemu({vmid}).snapshot({name!r}).rollback.post()")
        return
    double_confirm("roll back (discards newer changes)", f"VM {vmid} → snapshot {name}")
    result = gov.vm_snapshot_rollback(vmid=vmid, name=name, target=target, node=node)
    console.print(f"[green]Rolled VM {vmid} back to '{name}'[/] (task: {result['task']})")


@vm_app.command("resize-disk")
@cli_errors
def vm_resize_disk(
    vmid: int,
    disk: str = typer.Option(..., "--disk", help="Disk key, e.g. scsi0"),
    size: str = typer.Option(..., "--size", help="'+10G' increment or larger absolute"),
    target: TargetOption = None,
    node: NodeOption = None,
    dry_run: DryRunOption = False,
) -> None:
    """Grow a VM disk (grow-only — shrink is refused)."""
    if dry_run:
        dry_run_preview(
            gov_disk.vm_resize_disk(vmid=vmid, disk=disk, size=size, dry_run=True,
                                    target=target, node=node),
            operation="resize_disk", api_call=f"qemu({vmid}).resize.put()",
            parameters={"disk": disk, "size": size})
        return
    gov_disk.vm_resize_disk(vmid=vmid, disk=disk, size=size, target=target, node=node)
    console.print(f"[green]Resized {disk} on VM {vmid}[/] to {size}")


@vm_app.command("move-disk")
@cli_errors
def vm_move_disk(
    vmid: int,
    disk: str = typer.Option(..., "--disk", help="Disk key, e.g. scsi0"),
    storage: str = typer.Option(..., "--storage", help="Destination storage id"),
    delete: bool = typer.Option(False, "--delete", help="Remove source copy after move"),
    target: TargetOption = None,
    node: NodeOption = None,
    dry_run: DryRunOption = False,
) -> None:
    """Move a VM disk to another storage (async — poll with 'cluster task-status')."""
    if dry_run:
        # NOT routed: gov_disk.vm_move_disk takes no dry_run parameter (see the
        # note on vm_reconfigure). Unguarded, unaudited preview until it does.
        dry_run_print(operation="move_disk", api_call=f"qemu({vmid}).move_disk.post()",
                      parameters={"disk": disk, "storage": storage, "delete": delete})
        return
    result = gov_disk.vm_move_disk(
        vmid=vmid, disk=disk, storage=storage, delete=delete, target=target, node=node
    )
    console.print(f"[green]Moving {disk} on VM {vmid} → {storage}[/] (task: {result['task']})")


@vm_app.command("agent-ping")
@cli_errors
def vm_agent_ping(vmid: int, target: TargetOption = None, node: NodeOption = None) -> None:
    """Ping a VM's QEMU guest agent (responsive / not)."""
    conn, _ = get_connection(target)
    result = ag.agent_ping(conn, vmid, node=node)
    state = "responsive" if result["responsive"] else "not responding"
    console.print(f"  [cyan]VM {vmid} guest agent:[/] {state}")
    if result.get("message"):
        console.print(f"  {result['message']}")
