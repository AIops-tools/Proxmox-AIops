"""Top-level Typer app: assembles sub-apps and top-level commands."""

from __future__ import annotations

import typer

from proxmox_aiops.cli._common import cli_errors
from proxmox_aiops.cli.backup import backup_app
from proxmox_aiops.cli.cluster import cluster_app
from proxmox_aiops.cli.doctor import doctor_cmd
from proxmox_aiops.cli.firewall import firewall_app
from proxmox_aiops.cli.ha import ha_app
from proxmox_aiops.cli.init import init_cmd
from proxmox_aiops.cli.lxc import ct_app
from proxmox_aiops.cli.pool import pool_app
from proxmox_aiops.cli.secret import secret_app
from proxmox_aiops.cli.storage import storage_app
from proxmox_aiops.cli.vm import vm_app

app = typer.Typer(
    name="proxmox-aiops",
    help="Proxmox VE AI-powered VM lifecycle operations.",
    no_args_is_help=True,
)

app.add_typer(vm_app, name="vm")
app.add_typer(ct_app, name="ct")
app.add_typer(cluster_app, name="cluster")
app.add_typer(storage_app, name="storage")
app.add_typer(backup_app, name="backup")
app.add_typer(ha_app, name="ha")
app.add_typer(pool_app, name="pool")
app.add_typer(firewall_app, name="firewall")
app.add_typer(secret_app, name="secret")
app.command("init")(init_cmd)
app.command("doctor")(doctor_cmd)


@app.command("mcp")
@cli_errors
def mcp_cmd() -> None:
    """Start the MCP server (stdio transport).

    Single-command entry point for MCP clients (踩坑 #25 — does not go through
    uvx/PyPI resolution at launch):
        proxmox-aiops mcp
    """
    import sys

    if sys.version_info < (3, 11):
        typer.echo(
            f"ERROR: proxmox-aiops requires Python >= 3.11 "
            f"(got {sys.version_info.major}.{sys.version_info.minor}).\n"
            f"Fix: uv python install 3.12 && "
            f"uv tool install --python 3.12 --force proxmox-aiops",
            err=True,
        )
        raise typer.Exit(2)

    from mcp_server.server import main as _mcp_main

    _mcp_main()


if __name__ == "__main__":
    app()
