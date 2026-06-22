<!-- mcp-name: io.github.AIops-tools/proxmox-aiops -->

# Proxmox AIops (preview)

> **Disclaimer**: Community-maintained open-source project. **Not affiliated with, endorsed by, or sponsored by Proxmox Server Solutions GmbH.** "Proxmox" is a trademark of its owner. MIT licensed.

AI-powered Proxmox VE VM and container lifecycle operations with a **built-in
governance harness** — unified audit log, policy engine, token/runaway budget
guard, undo-token recording, and graduated-autonomy risk tiers. Self-contained:
no external dependencies beyond `proxmoxer` and the MCP SDK. Preview — not yet
full coverage of every Proxmox operation.

## What works

- **CLI** (`proxmox-aiops ...`): `vm list/get/config/start/stop/shutdown/reboot/reconfigure/clone/delete/migrate`, `vm snapshot-create/snapshot-delete/snapshot-list/snapshot-rollback`, `ct list/start/stop`, `cluster nodes/status/task-status`, `storage list/content`, `doctor`, `mcp`.
- **MCP server** (`proxmox-aiops mcp` or `proxmox-aiops-mcp`): **23 tools**, every one wrapped with the bundled `@governed_tool` harness.
- **Reversibility**: write ops with a clean inverse (start/stop/shutdown/reconfigure/clone/migrate/snapshot-create, container start/stop) record an inverse undo descriptor; irreversible ops (delete, snapshot-rollback) declare none and are tagged `high` risk.
- **Async tasks**: Proxmox writes return a task UPID — poll completion with `cluster task-status` (the runaway budget guard prevents poll loops from running away).

## Quick start

```bash
uv tool install proxmox-aiops
mkdir -p ~/.proxmox-aiops
# create ~/.proxmox-aiops/config.yaml with a targets: list
# put secrets in ~/.proxmox-aiops/.env  (chmod 600)
proxmox-aiops doctor
```

Example `~/.proxmox-aiops/config.yaml`:

```yaml
targets:
  - name: pve-lab
    host: 10.0.0.10
    user: "root@pam!claude"   # API token: user@realm!tokenid
    node: pve1
    auth_kind: token
    verify_ssl: false          # self-signed lab certs only
```

`~/.proxmox-aiops/.env` (chmod 600): `PROXMOX_PVE_LAB_SECRET=<token-uuid>`

## Audit & safety

All operations are logged to a local SQLite audit DB under `~/.proxmox-aiops/`
(relocatable via `PROXMOX_AIOPS_HOME`). Every write tool passes through the
governance harness: policy pre-check, token/runaway budget guard, graduated
risk-tier gate, and audit logging. Destructive CLI commands (`vm stop`,
`vm delete`, `vm snapshot-delete`, `vm snapshot-rollback`, `ct stop`) require
double confirmation and support `--dry-run`. API-returned text is run through a
prompt-injection sanitizer.

License: MIT.
