# Changelog

## v0.3.1 — 2026-07-16

### Fixed
- **`secrets.enc` now follows `PROXMOX_AIOPS_HOME`** (secretstore hardcoded the real
  home directory; config/audit/undo already relocated — found in live verification).
- **Audit fidelity**: failures sanitized into `{"error": ...}` results by the MCP error
  layer are now audited as `status=error` (they previously read as `ok`, hiding failed
  attempts from exception reports), and no undo is recorded for a call that failed.

### Tests
- `doctor` and the `init` wizard are now fully covered (previously ~10–20%); plus a
  regression test for the sanitized-failure audit status.

## v0.3.0 — 2026-07-13

Security-hardening release from a line-wide code review.

### Changed (behavior)
- **Secure by default**: with no `rules.yaml`, high/critical operations now require a
  named approver (`PROXMOX_AUDIT_APPROVED_BY`). A fresh install no longer allows
  destructive writes unattended; `init` seeds a starter `rules.yaml` you can edit,
  and an operator-authored rules file is honoured as-is.
- `__version__` is now single-sourced from package metadata (the previous release
  self-reported a stale version string).
- Sanitize docs no longer overstate scope: it strips control/format characters and
  truncates; semantic prompt-injection resistance must come from the consuming agent.

### Fixed
- CLI exception handling: `storage list/content` without a node and unknown LXC ids now print a one-line error instead of a traceback (duplicate `NodeRequiredError` class removed; `ContainerNotFoundError` handled).
- `vm_snapshot_delete` risk tier raised medium → high (destroys a rollback point; line consistency).
- API connections now carry a 30s timeout.
- All lifecycle write tools accept `dry_run=True` previews.

### Tests
- Governance persistence is now tested against REAL `audit.db`/`undo.db` files
  (write → audit row + inverse undo row with captured prior state).
- The CLI confirmed-write path (dry-run / double-confirm / governed execution) is
  covered end-to-end.
- `pytest-cov` added to the dev dependencies.

## v0.2.1

- Fix: `PROXMOX_AIOPS_HOME` now also relocates `config.yaml` (was hardcoded to `~/.proxmox-aiops`).
- Fix: **CLI writes are now audited + undo-recorded** via the governance path — previously only the MCP tools recorded audit/undo; CLI `manage`/`remediate`/etc. writes now go through the same `@governed_tool` layer (they keep their dry-run + double-confirm). CLI write output is now the governed JSON result. No API/tool changes.


All notable changes to **proxmox-aiops** are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — 2026-06-27

Encrypted credentials, a friendly onboarding wizard, and MCP tools expanded from
**23 → 39**.

### Added
- **Encrypted credential store** — secrets now live in `~/.proxmox-aiops/secrets.enc`
  (Fernet/AES + HMAC, key derived from a master password via scrypt). Nothing is
  written to disk in plaintext; the file is `chmod 600`.
- **Onboarding wizard** — `proxmox-aiops init` collects connection details and your
  API token/password (stored encrypted), then offers a connectivity check.
- **Secret management** — `proxmox-aiops secret set/list/rm/migrate/rotate-password`.
  `migrate` imports a legacy plaintext `.env` and renames it `.env.migrated`.
- **Backups (vzdump)** — `vm_backup`, `backup_list`, `backup_restore`
  (high risk; dry-run + double-confirm; undo-aware).
- **Disk ops** — `vm_resize_disk` (grow-only; refuses shrink), `vm_move_disk`.
- **Cluster** — `cluster_resources`, `node_status`, `task_log`, `next_vmid`.
- **HA** — `ha_status`, `ha_resource_list` (clean "HA not configured" signal).
- **Pools** — `pool_list`, `pool_members`.
- **Firewall (read-only)** — `vm_firewall_rules_list`, `cluster_firewall_status`.
- **Guest agent** — `vm_agent_ping`.

### Changed
- `config.py` resolves secrets from the encrypted store first, then a legacy
  `PROXMOX_<TARGET>_SECRET` env var (with a deprecation warning).
- `doctor` reports encrypted-store presence/permissions and nudges to `init`.
- Dropped the "SKELETON / preview" label from the CLI help.

### Security
- Master password is supplied via `PROXMOX_AIOPS_MASTER_PASSWORD` for the MCP server
  / non-interactive use, or prompted interactively. No tool returns credentials.
  Destructive operations keep dry-run + double-confirm and correct risk tiers.

### Notes
- Still preview/mock-validated — `vm_backup`/`backup_restore` model the documented
  PVE API2 paths; verify against a live cluster. Restore is modeled for QEMU VMs.

## [0.1.0] — 2026-06-22

Initial preview release: QEMU VM lifecycle, snapshots, LXC, cluster/nodes, storage
(23 MCP tools), with the vendored governance harness.

[0.2.0]: https://github.com/AIops-tools/Proxmox-AIops/releases/tag/v0.2.0
[0.1.0]: https://github.com/AIops-tools/Proxmox-AIops/releases/tag/v0.1.0
