# Security Policy

## Disclaimer

Community-maintained open-source project. **Not affiliated with, endorsed by, or
sponsored by Proxmox Server Solutions GmbH.** "Proxmox" is a trademark of its
owner. Source is publicly auditable under the MIT license.

## Reporting Vulnerabilities

Report privately via a GitHub Security Advisory on
[github.com/AIops-tools/Proxmox-AIops](https://github.com/AIops-tools/Proxmox-AIops/security/advisories)
or email zhouwei008@gmail.com. Please do not open public issues for security
reports.

## Security Design

### Credential Management
- Per-target secrets live in `~/.proxmox-aiops/.env` (chmod 600), never in
  `config.yaml` and never in source. Variable pattern:
  `PROXMOX_<TARGET_NAME_UPPER>_SECRET` (API token UUID, or login password).
- Secrets are never logged or echoed; the config file holds only host, user,
  node, and TLS settings.

### Governed Operations
Every MCP tool runs through the bundled `@governed_tool` harness
(`proxmox_aiops.governance`):
- **Audit** — every call logged to a local SQLite DB under `~/.proxmox-aiops/`
  (relocatable via `PROXMOX_AIOPS_HOME`), agent-attributed, secret-redacted.
- **Token/runaway budget** — hard ceilings (`PROXMOX_MAX_TOOL_CALLS` /
  `PROXMOX_MAX_TOOL_SECONDS`) plus an on-by-default guard that trips a tight
  poll/retry loop, preventing unbounded API consumption.
- **Risk tiers** — each tool's `risk_level` is recorded on the audit row as a
  descriptive tier (none/confirm/review). It is a label for reviewers, not a
  gate: whether a write is permitted is the connecting account's privileges or
  the agent's judgement, not the skill's. `PROXMOX_AUDIT_APPROVED_BY` /
  `PROXMOX_AUDIT_RATIONALE` are optional annotations, never required.
- **Undo-token recording** — reversible writes record an inverse descriptor so
  a change can be rolled back.

### Destructive Operations
`vm stop`, `vm delete`, `vm snapshot-delete`, `vm snapshot-rollback`, and
`ct stop` require double confirmation at the CLI layer and support `--dry-run`.

### SSL/TLS Verification
`verify_ssl` defaults to true; disable only for self-signed lab certificates.

### Prompt-Injection Protection
All Proxmox-API-returned text (names, UPIDs, descriptions) is passed through a
`sanitize()` truncate + control-character strip before reaching the agent.

### Network Scope
No webhooks, no telemetry, no outbound calls beyond the configured Proxmox API
endpoint. No post-install scripts or background services.

## Static Analysis

```bash
uvx bandit -r proxmox_aiops/ mcp_server/
uv run ruff check .
```

## Supported Versions

The latest released version receives security fixes. This is a preview (0.x);
pin a version in production.
