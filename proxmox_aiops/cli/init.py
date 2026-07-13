"""``proxmox-aiops init`` — a friendly, interactive onboarding wizard.

Walks a new user through connecting their first Proxmox target: collects the
non-secret connection details into ``config.yaml`` and the API token / password
into the *encrypted* store (never plaintext on disk). Designed to be run on a
terminal; everything it needs is prompted with sensible defaults.
"""

from __future__ import annotations

import getpass

import typer
import yaml

from proxmox_aiops.cli._common import cli_errors, console
from proxmox_aiops.config import CONFIG_DIR, CONFIG_FILE
from proxmox_aiops.governance.paths import ops_path
from proxmox_aiops.secretstore import SecretStore, resolve_master_password

# Starter policy: keeps the secure-by-default gate (high/critical writes need a
# named approver) explicit and editable, and shows the other rule kinds.
DEFAULT_RULES_YAML = """\
# proxmox-aiops policy rules — hot-reloaded on change (no restart needed).
# Kinds: deny rules, maintenance_window, risk_tiers (graduated autonomy).

risk_tiers:
  - name: high-risk-requires-approver
    tier: dual
    min_risk_level: high
    reason: >-
      High/critical writes need a named human approver — set
      PROXMOX_AUDIT_APPROVED_BY (and PROXMOX_AUDIT_RATIONALE) before the call.

# deny:
#   - name: no-prod-deletes
#     operations: ["vm_delete", "vm_snapshot_rollback"]
#     environments: ["production"]
#     reason: "Destroying VMs in production goes through change management."

# maintenance_window:
#   start: "22:00"
#   end: "06:00"
"""


def _write_default_rules() -> None:
    """Seed a starter rules.yaml (only when none exists) so the policy layer
    is explicit from day one; never overwrites an operator-authored file."""
    rules_path = ops_path("rules.yaml")
    if rules_path.exists():
        return
    rules_path.parent.mkdir(parents=True, exist_ok=True)
    rules_path.write_text(DEFAULT_RULES_YAML, "utf-8")
    console.print(f"[green]✓ Wrote default policy rules:[/] {rules_path}")


def _load_existing_targets() -> list[dict]:
    if not CONFIG_FILE.exists():
        return []
    raw = yaml.safe_load(CONFIG_FILE.read_text("utf-8")) or {}
    return list(raw.get("targets", []))


def _write_targets(targets: list[dict]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        CONFIG_DIR.chmod(0o700)
    except OSError:
        pass
    CONFIG_FILE.write_text(yaml.safe_dump({"targets": targets}, sort_keys=False), "utf-8")


@cli_errors
def init_cmd() -> None:
    """Interactively set up your first Proxmox connection."""
    console.print("[bold cyan]Proxmox AIops — setup wizard[/]")
    console.print(
        "This collects connection details (saved to config.yaml) and your API "
        "token/password (saved [bold]encrypted[/] to secrets.enc).\n"
    )

    console.print("[bold]Step 1 — master password[/]")
    console.print(
        "[dim]Encrypts secrets.enc. You'll set it via the "
        "PROXMOX_AIOPS_MASTER_PASSWORD env var for non-interactive/MCP use.[/]"
    )
    password = resolve_master_password(confirm_if_new=True)
    store = SecretStore.unlock(password)

    targets = _load_existing_targets()
    existing_names = {t.get("name") for t in targets}

    while True:
        console.print("\n[bold]Step 2 — add a target[/]")
        name = typer.prompt("Target name (e.g. pve-lab)").strip()
        if name in existing_names:
            if not typer.confirm(f"'{name}' already exists — overwrite?", default=False):
                continue
            targets = [t for t in targets if t.get("name") != name]

        host = typer.prompt("Host (IP or FQDN of the PVE node/cluster)").strip()
        auth_kind = typer.prompt(
            "Auth kind: 'token' (recommended) or 'password'", default="token"
        ).strip()
        if auth_kind not in ("token", "password"):
            console.print("[yellow]Unknown auth kind; defaulting to 'token'.[/]")
            auth_kind = "token"

        if auth_kind == "token":
            console.print("[dim]User format: user@realm!tokenid  e.g. root@pam!aiops[/]")
        else:
            console.print("[dim]User format: user@realm  e.g. root@pam[/]")
        user = typer.prompt("User").strip()
        node = typer.prompt("Default node (optional, Enter to skip)", default="").strip()
        port = typer.prompt("Port", default=8006, type=int)
        console.print("[dim]Lab/self-signed setups can answer No here.[/]")
        verify_ssl = typer.confirm("Verify TLS certificate?", default=True)

        secret_label = "API token secret" if auth_kind == "token" else "login password"
        secret = getpass.getpass(f"{secret_label} for '{name}' (hidden): ")
        store = store.set(name, secret)

        entry = {
            "name": name,
            "host": host,
            "user": user,
            "auth_kind": auth_kind,
            "port": port,
            "verify_ssl": verify_ssl,
        }
        if node:
            entry["node"] = node
        targets.append(entry)
        existing_names.add(name)
        _write_targets(targets)
        console.print(f"[green]✓ Saved target '{name}' (secret stored encrypted).[/]")

        if not typer.confirm("\nAdd another target?", default=False):
            break

    _write_default_rules()
    console.print(f"\n[green]✓ Setup complete.[/] Config: {CONFIG_FILE}")
    console.print(
        "[dim]Tip: export PROXMOX_AIOPS_MASTER_PASSWORD=... in your shell profile "
        "so the MCP server and CLI can unlock secrets non-interactively.[/]"
    )
    if typer.confirm("Run a connectivity check now (proxmox-aiops doctor)?", default=True):
        from proxmox_aiops.doctor import run_doctor

        raise typer.Exit(run_doctor())
