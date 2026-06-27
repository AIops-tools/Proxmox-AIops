"""``proxmox-aiops backup ...`` sub-commands (vzdump create/list/restore)."""

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
from proxmox_aiops.ops import backup as bk

backup_app = typer.Typer(help="Backup (vzdump) operations.", no_args_is_help=True)
console = Console()


@backup_app.command("create")
@cli_errors
def backup_create(
    vmid: int,
    storage: str = typer.Option(..., "--storage", help="Backup-capable storage id"),
    mode: str = typer.Option("snapshot", "--mode", help="snapshot/suspend/stop"),
    target: TargetOption = None,
    node: NodeOption = None,
) -> None:
    """Create a vzdump backup of a VM/CT (async — poll with 'cluster task-status')."""
    conn, _ = get_connection(target)
    result = bk.vm_backup(conn, vmid, storage, node=node, mode=mode)
    console.print(f"[green]Backup of {vmid} → {storage} started[/] (task: {result['task']})")


@backup_app.command("list")
@cli_errors
def backup_list(
    storage: str,
    vmid: int = typer.Option(None, "--vmid", help="Filter by guest id"),
    target: TargetOption = None,
    node: NodeOption = None,
) -> None:
    """List backup archives on a storage."""
    conn, _ = get_connection(target)
    rows = bk.list_backups(conn, storage, node=node, vmid=vmid)
    table = Table(title=f"Backups — {storage}")
    for col in ("volid", "vmid", "size", "format", "ctime"):
        table.add_column(col)
    for r in rows:
        table.add_row(
            r["volid"], str(r.get("vmid")), str(r.get("size")),
            r["format"], str(r.get("ctime")),
        )
    console.print(table)


@backup_app.command("restore")
@cli_errors
def backup_restore(
    vmid: int,
    archive: str = typer.Option(..., "--archive", help="Backup volid / archive"),
    storage: str = typer.Option(..., "--storage", help="Storage for restored disks"),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing vmid"),
    target: TargetOption = None,
    node: NodeOption = None,
    dry_run: DryRunOption = False,
) -> None:
    """Restore a VM from a backup (HIGH RISK — double confirm)."""
    if dry_run:
        dry_run_print(operation="restore_backup", api_call=f"qemu.post(vmid={vmid})",
                      parameters={"archive": archive, "storage": storage, "force": force})
        return
    double_confirm("restore (may overwrite)", f"VM {vmid} from {archive}")
    conn, _ = get_connection(target)
    result = bk.restore_backup(conn, vmid, archive, storage, node=node, force=force)
    console.print(f"[green]Restoring VM {vmid} from backup[/] (task: {result['task']})")
