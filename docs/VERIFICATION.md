# Live verification — dropping the `preview` label

`proxmox-aiops` ships marked **(preview)**. Preview does **not** mean unreleased —
the package is on PyPI, the MCP Registry, and ClawHub. It means one specific
thing:

> The code is exercised by a mock-only test suite (`uv run pytest`, no real
> Proxmox). It has **not** yet been validated end-to-end against a live Proxmox VE
> cluster. Until it has, we do not claim it works against a real API.

This document defines exactly what a live verification run must cover, and the
criteria for removing the `preview` label. It is deliberately checklist-shaped so
the result is reproducible and auditable — not a subjective "seems fine".

## What preview already guarantees (mock baseline)

- Every module imports; the CLI builds; every MCP tool carries the
  `@governed_tool` harness marker (`tests/test_smoke.py`).
- Pure analyses (diagnostics/RCA thresholds) are unit-tested against synthetic
  telemetry.
- Write tools record the correct inverse undo descriptor (tested with a mocked
  connection).

What it does **not** guarantee: that the proxmoxer call shapes, field names, and
async task semantics match a real Proxmox VE build.

## Prerequisites for a live run

A reachable Proxmox VE (a single self-hosted node is enough — the community
self-test path). Create an **API token with least privilege** and a
**throwaway/test VM** you are willing to stop, snapshot, reconfigure, and destroy.
Never verify against production guests.

```bash
uv tool install proxmox-aiops
proxmox-aiops init            # encrypted secret store, TLS verify on by default
```

## Verification checklist

Tick every box. A box that cannot be ticked is a verification gap — record it,
do not silently pass.

### 1. Connectivity (the fastest live gate)
- [ ] `proxmox-aiops doctor` → all green (config, secret store, and a real
      `version.get()` against the node).

### 2. Reads return real, well-shaped data
- [ ] `proxmox-aiops vm list` → the actual VMs, with populated vmid/name/status.
- [ ] `proxmox-aiops cluster resources` → node/vm/storage rows are present.
- [ ] `proxmox-aiops diagnose node-pressure` → percentages match what the PVE UI
      shows for the node; no crash on missing fields.
- [ ] `proxmox-aiops diagnose guest-health` → stopped guests listed correctly;
      any saturated guest is flagged with the right measured number.

### 3. A reversible write + its undo (governance closes the loop)
- [ ] `proxmox-aiops vm stop <test-vmid> --dry-run` → prints the API call, changes
      nothing.
- [ ] `proxmox-aiops vm stop <test-vmid>` → the VM actually stops; the result
      carries an `_undo_id`; a row lands in `~/.proxmox-aiops/audit.db`.
- [ ] `proxmox-aiops undo apply <id>` → the recorded inverse (`vm_start`) runs and
      the VM comes back up.
- [ ] `proxmox-aiops vm reconfigure <test-vmid> --cores N` then `undo apply` →
      the **prior** core count is restored (proves undo captured pre-state, not a
      guess).

### 4. An async task is polled, not re-issued
- [ ] `proxmox-aiops vm clone <src> --newid <free>` → returns a task UPID;
      `cluster task-status <upid>` reaches `stopped/OK` without re-issuing the clone.

### 5. Governance actually gates
- [ ] With no `rules.yaml`, a `high`-risk op (e.g. `vm delete --dry-run` then real)
      is refused unless `PROXMOX_AUDIT_APPROVED_BY` is set (secure-by-default).
- [ ] A tight poll loop trips the runaway budget guard rather than hammering the API.

### 6. Cleanup
- [ ] Destroy the test VM; confirm the destroy is audited and tagged `high`.

## Criteria to drop `preview`

Remove `(preview)` from the README title, SKILL.md description/title, and the
`mcp`/FastMCP instructions **only when all of the following hold**:

1. Every checklist box above is ticked against at least one real Proxmox VE
   version, and the PVE version is recorded (e.g. "verified on PVE 8.2").
2. Any field-shape mismatch found during the run is fixed and covered by a test.
3. The run is written up in this repo's memory / release notes with the date and
   version, matching how the line records its other live-verified tools.

Until then the label stays — it is a promise about what we have and have not
checked, and dropping it early would break that promise.

## Notes for maintainers

- `doctor` is the single fastest live entry point; start there.
- The verification story for the whole product line is tracked centrally; add
  this tool's result there once green so the "verification debt" ledger stays
  accurate.
