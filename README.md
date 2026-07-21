<!-- mcp-name: io.github.AIops-tools/proxmox-aiops -->

# Proxmox AIops

> **Disclaimer**: Community-maintained open-source project. **Not affiliated with, endorsed by, or sponsored by Proxmox Server Solutions GmbH.** "Proxmox" is a trademark of its owner. MIT licensed.

AI-powered Proxmox VE VM and container lifecycle operations with a **built-in
governance harness** — unified audit log, token/runaway budget
guard, undo-token recording, and descriptive risk-tier labels. Self-contained:
no external dependencies beyond `proxmoxer` and the MCP SDK. Coverage is not
yet exhaustive across every Proxmox operation.

> **Verification status**: the test suite is mock-based; this package has not
> yet been validated end-to-end against a live Proxmox VE cluster. See
> [docs/VERIFICATION.md](docs/VERIFICATION.md) for the live-verification checklist.

## What works

- **CLI** (`proxmox-aiops ...`): `vm list/get/config/start/stop/shutdown/reboot/reconfigure/clone/delete/migrate`, `vm resize-disk/move-disk/agent-ping`, `vm snapshot-create/snapshot-delete/snapshot-list/snapshot-rollback`, `backup create/list/restore`, `ct list/start/stop`, `cluster nodes/status/task-status/resources/node-status/task-log/next-vmid`, `ha status/resources`, `pool list/members`, `firewall vm-rules/cluster-status`, `storage list/content`, `diagnose node-pressure/guest-health`, `undo list/apply`, `init`, `secret set/list/rm/migrate/rotate-password`, `doctor`, `mcp`.
- **MCP server** (`proxmox-aiops mcp` or `proxmox-aiops-mcp`): **43 tools**, every one wrapped with the bundled `@governed_tool` harness.
- **Diagnostics / RCA** (read-only): `diagnose node-pressure` ranks cluster nodes by CPU/memory/root-fs pressure; `diagnose guest-health` scans VMs/containers for stopped guests, memory saturation, and disks near full. Every finding cites the measured number that tripped it and a concrete action — transparent heuristics, not a black-box verdict.
- **Credentials**: `proxmox-aiops init` (onboarding wizard) and `proxmox-aiops secret ...` manage an encrypted secret store — no plaintext passwords in `config.yaml`.
- **Reversibility**: write ops with a clean inverse (start/stop/shutdown/reconfigure/clone/migrate/snapshot-create/move-disk, container start/stop, and restore-into-a-free-vmid) record an inverse undo descriptor; irreversible ops (delete, snapshot-rollback, forced restore) declare none and are tagged `high` risk. Disk resize is grow-only (shrink refused).
- **Async tasks**: Proxmox writes return a task UPID — poll completion with `cluster task-status` / read lines with `cluster task-log` (the runaway budget guard prevents poll loops from running away).

## What this tool does, and does not, decide

It delivers Proxmox VE operations — reads and writes — accurately and
efficiently, and records every one of them. It does **not** decide whether a write is allowed to
happen. That is the agent's judgement, or the permission of the account you connect it with:
use a Proxmox VE user or API token granted only read privileges (no VM.*/Datastore.* write roles),
and the writes fail at the server — the place that actually owns the permission.

So there is no read-only switch, no policy file, no approval gate to configure. The one thing the
tool guarantees is that nothing is silent: **every call, over MCP and over the CLI alike, lands an
audit row** in `~/.proxmox-aiops/audit.db`, and destructive writes still capture their before-state
and record an inverse where one exists.

> Each tool declares a `risk_level`, carried into the audit row as a descriptive tier
> (none/confirm/review) — so a reviewer can see at a glance that a row was a high-risk delete. It
> is a label, not a gate.

Running a smaller / local model? See
[agent-guardrails.md](skills/proxmox-aiops/references/agent-guardrails.md) — it lists
the guardrails this tool now enforces for you (so you don't spend prompt budget
restating them) and gives a ready-made system prompt for what's left.

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
governance harness: token/runaway budget guard, risk-tier tagging, and audit
logging. Destructive CLI commands (`vm stop`,
`vm delete`, `vm snapshot-delete`, `vm snapshot-rollback`, `ct stop`) require
double confirmation and support `--dry-run` (notably `backup restore`, which is
`high` risk). API-returned text is run through a prompt-injection sanitizer.

## Contributing & feature requests

Coverage is intentionally focused. **Missing a device, action, or feature you need?** Open an issue or pull request at [github.com/AIops-tools/Proxmox-AIops](https://github.com/AIops-tools/Proxmox-AIops/issues) — feature requests, contributions, and comments are all welcome.

License: MIT.
