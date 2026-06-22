# Release notes

## v0.1.0 (2026-06-22) — first release (preview)

First public release of **proxmox-aiops** — governed Proxmox VE VM and container
lifecycle operations for AI agents. Standalone and self-contained.

### Highlights
- **23 MCP tools** (8 read / 15 write):
  - VM lifecycle: list/get/config, start/stop/shutdown/reboot, reconfigure,
    clone, delete, migrate
  - Snapshots: create/delete/list/rollback
  - LXC containers: list/start/stop
  - Cluster/tasks: node list, cluster status, async task (UPID) polling
  - Storage: pool list, content list
- **CLI + MCP server** (`proxmox-aiops` and `proxmox-aiops mcp`).
- **Built-in governance harness** (`proxmox_aiops.governance`, no external
  dependency): unified audit log under `~/.proxmox-aiops/`, policy engine,
  token/runaway budget guard, undo-token recording, and graduated-autonomy
  risk tiers. State dir relocatable via `PROXMOX_AIOPS_HOME`.
- **Reversibility**: write ops with a clean inverse (start/stop/shutdown/
  reconfigure/clone/migrate/snapshot-create, container start/stop) record an
  undo descriptor; irreversible ops (delete, snapshot-rollback) declare none
  and are tagged `high` risk.
- **Safety**: destructive CLI commands require double confirmation + `--dry-run`;
  all API text is sanitized; TLS verification on by default.

### Notes
- Preview (0.x): broad coverage of common operations, not yet exhaustive — see
  `references/capabilities.md` for the "not yet covered" list.
- Proxmox writes are asynchronous; poll completion with `cluster task-status`.
- Verified with a mocked Proxmox API (9 smoke tests); not yet exercised against
  a live PVE cluster.
