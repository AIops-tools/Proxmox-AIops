<!-- mcp-name: io.github.AIops-tools/proxmox-aiops -->

# Proxmox AIops (preview)

> **Disclaimer**: Community-maintained open-source project. **Not affiliated with, endorsed by, or sponsored by Proxmox Server Solutions GmbH.** "Proxmox" is a trademark of its owner. MIT licensed.

AI-powered Proxmox VE VM and container lifecycle operations with a **built-in
governance harness** — unified audit log, policy engine, token/runaway budget
guard, undo-token recording, and graduated-autonomy risk tiers. Self-contained:
no external dependencies beyond `proxmoxer` and the MCP SDK. Preview — not yet
full coverage of every Proxmox operation.

## What works

- **CLI** (`proxmox-aiops ...`): `vm list/get/config/start/stop/shutdown/reboot/reconfigure/clone/delete/migrate`, `vm resize-disk/move-disk/agent-ping`, `vm snapshot-create/snapshot-delete/snapshot-list/snapshot-rollback`, `backup create/list/restore`, `ct list/start/stop`, `cluster nodes/status/task-status/resources/node-status/task-log/next-vmid`, `ha status/resources`, `pool list/members`, `firewall vm-rules/cluster-status`, `storage list/content`, `init`, `secret set/list/rm/migrate/rotate-password`, `doctor`, `mcp`.
- **MCP server** (`proxmox-aiops mcp` or `proxmox-aiops-mcp`): **39 tools**, every one wrapped with the bundled `@governed_tool` harness.
- **Credentials**: `proxmox-aiops init` (onboarding wizard) and `proxmox-aiops secret ...` manage an encrypted secret store — no plaintext passwords in `config.yaml`.
- **Reversibility**: write ops with a clean inverse (start/stop/shutdown/reconfigure/clone/migrate/snapshot-create/move-disk, container start/stop, and restore-into-a-free-vmid) record an inverse undo descriptor; irreversible ops (delete, snapshot-rollback, forced restore) declare none and are tagged `high` risk. Disk resize is grow-only (shrink refused).
- **Async tasks**: Proxmox writes return a task UPID — poll completion with `cluster task-status` / read lines with `cluster task-log` (the runaway budget guard prevents poll loops from running away).

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
double confirmation and support `--dry-run` (notably `backup restore`, which is
`high` risk). API-returned text is run through a prompt-injection sanitizer.

## Contributing & feature requests

This is a preview — coverage is intentionally focused. **Missing a device, action, or feature you need?** Open an issue or pull request at [github.com/AIops-tools/Proxmox-AIops](https://github.com/AIops-tools/Proxmox-AIops/issues) — feature requests, contributions, and comments are all welcome.

License: MIT.
