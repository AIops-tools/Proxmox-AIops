"""Doctor top-level command: environment and connectivity check."""

from __future__ import annotations

from typing import Annotated

import typer

from proxmox_aiops.cli._common import cli_errors


@cli_errors
def doctor_cmd(
    skip_auth: Annotated[
        bool, typer.Option("--skip-auth", help="Skip connectivity check (faster)")
    ] = False,
) -> None:
    """Check environment, config, secrets, and connectivity."""
    from proxmox_aiops.doctor import run_doctor

    raise typer.Exit(run_doctor(skip_auth=skip_auth))
