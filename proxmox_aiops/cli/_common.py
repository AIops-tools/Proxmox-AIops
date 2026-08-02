"""Shared helpers for proxmox-aiops CLI sub-modules."""

from __future__ import annotations

import functools
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console

console = Console()

# ─── Shared Option types ───────────────────────────────────────────────────

TargetOption = Annotated[
    str | None, typer.Option("--target", "-t", help="Target name from config")
]
NodeOption = Annotated[
    str | None, typer.Option("--node", "-n", help="Proxmox node name")
]
DryRunOption = Annotated[
    bool, typer.Option("--dry-run", help="Print the API call without executing")
]


def _cli_error_types() -> tuple[type[BaseException], ...]:
    """Exceptions translated to a one-line teaching error instead of a traceback.

    Governance refusals belong here: in this repo ``@tool_errors`` sits *inside*
    ``@governed_tool``, so a guard that fires (a budget/runaway trip) RAISES past
    the sanitiser instead of returning an ``{"error": ...}`` dict. Without these
    two entries a refused write — or a refused preview — reached the operator as a
    traceback rather than as the remediation sentence the harness wrote for
    exactly that purpose.
    """
    from proxmox_aiops.governance import PolicyDenied
    from proxmox_aiops.governance.budget import BudgetExceeded
    from proxmox_aiops.ops._task import TaskFailed
    from proxmox_aiops.ops.lxc import ContainerNotFoundError
    from proxmox_aiops.ops.vm_lifecycle import NodeRequiredError, VMNotFoundError

    return (
        PolicyDenied,
        BudgetExceeded,
        VMNotFoundError,
        ContainerNotFoundError,
        NodeRequiredError,
        TaskFailed,
        KeyError,
        OSError,
        ValueError,
    )


#: Exit code for an operation whose outcome could not be determined. Distinct
#: from 0 (confirmed) and 1 (failed) on purpose: a long clone that is still
#: running is not a failure, but it is emphatically not a success either, and a
#: script must be able to tell all three apart.
EXIT_UNDETERMINED = 2


def checked(result: Any) -> Any:
    """Return ``result``, or abort when it reports a failed/undetermined write.

    Every CLI command that calls a governed twin MUST pass the result through
    here before printing its success line.

    Governed twins are wrapped in ``@tool_errors``, which flattens any exception
    into ``{"error": ...}`` and **returns** it. The CLI therefore never sees the
    exception, so a command that prints ``[green]Done[/]`` unconditionally
    reports a refused or failed operation as done — and exits 0, so a script
    cannot tell either. Live-verified on Proxmox VE 8.4.19 (2026-08-02): a
    refused disk shrink printed "Resized scsi0 on VM 900 to -1G" and exited 0.
    (Same defect class already fixed in two sibling tools; this repo was never
    swept.)

    ``outcomeUnknown`` is neither success nor failure — the write may still land
    (see :mod:`proxmox_aiops.ops._task`). It gets its own yellow line and
    :data:`EXIT_UNDETERMINED`, never a green one.
    """
    if not isinstance(result, dict):
        return result
    error = result.get("error")
    if error:
        console.print(f"[red]Error: {error}[/]")
        hint = result.get("hint")
        if hint:
            console.print(f"[dim]{hint}[/]")
        raise typer.Exit(1)
    if result.get("outcomeUnknown"):
        detail = result.get("taskDetail") or result.get("note") or ""
        console.print(f"[yellow]Outcome undetermined: {detail}[/]")
        task = result.get("task")
        if task:
            console.print(f"[dim]Poll it with: cluster task-status {task}[/]")
        raise typer.Exit(EXIT_UNDETERMINED)
    return result


def cli_errors(fn: Callable) -> Callable:
    """Translate known exceptions into one red line + exit code 1."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except (typer.Exit, typer.Abort):
            raise
        except _cli_error_types() as e:
            message = str(e)
            if isinstance(e, KeyError):
                message = f"Missing required key or environment variable: {message}"
            console.print(f"[red]Error: {message}[/]")
            raise typer.Exit(1) from e

    return wrapper


def get_connection(target: str | None, config_path: Path | None = None) -> tuple[Any, Any]:
    """Return a (conn, config) tuple for the given target."""
    from proxmox_aiops.config import load_config
    from proxmox_aiops.connection import ConnectionManager

    cfg = load_config(config_path)
    mgr = ConnectionManager(cfg)
    return mgr.connect(target), cfg


def dry_run_print(*, operation: str, api_call: str, parameters: dict | None = None) -> None:
    """Print a dry-run preview of the API call that would be made."""
    console.print("\n[bold magenta][DRY-RUN] No changes will be made.[/]")
    console.print(f"[magenta]  Operation: {operation}[/]")
    console.print(f"[magenta]  API Call:  {api_call}[/]")
    for k, v in (parameters or {}).items():
        console.print(f"[magenta]  Param:     {k} = {v}[/]")
    console.print("[magenta]  Run without --dry-run to execute.[/]\n")


def dry_run_preview(
    preview: Any, *, operation: str, api_call: str, parameters: dict | None = None
) -> None:
    """Render a GOVERNED dry-run result as the human-readable DRY-RUN banner.

    ``preview`` must come from calling the governed tool with ``dry_run=True``,
    so every guard it carries has already run against the real target. A refusal
    arrives as ``{"error": ...}`` (``tool_errors`` flattens the exception) — it is
    printed like any other CLI error and exits non-zero, exactly as the real
    write would. Printing a green banner for a call that is about to be refused
    is the preview being wrong, not merely incomplete.

    On the allowed path the banner is byte-for-byte what it always was: routing
    through the governed call buys the guard and the audit row, not a new
    serialization.
    """
    if isinstance(preview, dict) and preview.get("error"):
        console.print(f"[red]Error: {preview['error']}[/]")
        raise typer.Exit(1)
    dry_run_print(operation=operation, api_call=api_call, parameters=parameters)


def double_confirm(action: str, resource: str) -> None:
    """Require two confirmations for a destructive operation."""
    console.print(f"[bold yellow]⚠️  About to: {action} '{resource}'[/]")
    typer.confirm(f"Confirm 1/2: {action} '{resource}'?", abort=True)
    typer.confirm(
        f"Confirm 2/2: really {action} '{resource}'? This may be irreversible.",
        abort=True,
    )
