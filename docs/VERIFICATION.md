# Live verification — proxmox-aiops

## 🔴 Round 2 — the QEMU write surface (2026-08-02): two real bugs

The first round (below) exercised one LXC container and found nothing. This one
drove a **real KVM guest** through the whole `vm.*` write surface — 14 of the
tool's 18 write tools had never touched one — and found two defects, both of
which the mock suite structurally could not see.

### 1. A UPID is not an outcome (all 15 async writes)

Proxmox VE's mutating endpoints are **asynchronous**: `POST .../status/start`
answers 200 with a task UPID *before* the operation runs. The tool treated that
200 as success. In one live session three operations that **failed on the node**
were each reported green and recorded `status=ok`:

| what the CLI printed | audit row | what PVE actually did |
|---|---|---|
| `Started VM 900` | `ok`, undo `effect_verified=1` | `start failed: QEMU exited with code 1` |
| `Shutdown requested for VM 900` | `ok` | `VM quit/powerdown failed - got timeout` |
| `Backup of 900 → local started` | `ok` | `job errors` (zero backups on the storage) |

Matched by UPID, **3 of 14 audit rows claimed success for a server-side
failure**. The damage is not cosmetic: the audit — this tool's central promise —
recorded state changes that never happened, and `undo_list` advertised them as
`effectVerified: true`, so `undo_apply` would have replayed an inverse for a
change that never occurred.

**Fixed** by `proxmox_aiops/ops/_task.py`: every write now resolves its task's
real `exitstatus` and maps it onto the harness's existing three-way outcome
model — `OK` → confirmed, non-OK → raise (audit `error`, **no** undo token),
still-running/unreadable → `mark_unknown` (audit `unknown`, undo
`effect_verified=0`). Bounded by `PROXMOX_TASK_WAIT_SECONDS` (default 20s, `0`
disables waiting). An unreadable task status is **undetermined, never OK**.

This also exposed a harness gap fixed line-wide: `is_unknown()` was only
consulted for payloads that *also* carried an `error`, so an undetermined
outcome that looked successful was audited `ok`.

### 2. The CLI swallowed governance errors and exited 0 (17 sites)

`vm resize-disk --size -1G` was correctly refused by `_reject_shrink`, but the
CLI printed `Resized scsi0 on VM 900 to -1G` in green and **exited 0** —
`@tool_errors` flattens the exception into `{"error": ...}` and *returns* it, and
no CLI command inspected the result. Only 1 of 17 success prints checked
anything. Same defect class already fixed in xcpng-aiops and veeam-aiops; this
repo was never swept.

**Fixed** by `cli/_common.checked()`, which every governed-twin call now passes
through: error → red line + exit 1; `outcomeUnknown` → yellow line + exit 2
(`EXIT_UNDETERMINED`), never green.

### Re-verified live after the fix

- failing start → red error carrying PVE's own reason, exit 1, audit `error`,
  **undo.db never created**
- refused shrink → red error, exit 1, no green line
- successful start → exit 0, server reports `running`, undo `effectVerified:
  true` → `undo apply` → `taskStatus: ok` → server reports `stopped`

### Corrections to earlier notes

- "the firewall/pool/storage **write** paths are untested" was wrong: those
  three surfaces are **read-only by design** in this tool — there are no write
  paths to test. The real gap was the QEMU write surface.
- `ha resources` returning "HA not configured or none defined" rather than a
  bare empty list is now confirmed against a real node.
- `firewall cluster-status` correctly distinguishes `enable: 0` (disabled) from
  `policy_out: null` (PVE returned no such key) — the null-vs-empty contract
  holds on real data.
- PVE itself returns `memory` as a **string** (`'512'`) while `cores` is an
  `int`; the tool passes both through faithfully. Upstream inconsistency, not a
  tool defect, but worth knowing before doing arithmetic on `memory`.

Still untested after this round: multi-node cluster/quorum, HA with real
resources, live migration (needs a second node), `move-disk` (needs a second
storage), and a backup that actually succeeds.

## ✅ Live-verified against real Proxmox VE 8.4.19 (2026-08-01)

Verified end-to-end against a real Proxmox VE 8.4.19 node (`pve1`, installed on
Debian 12 in a nested-KVM lab), driven through the real governed CLI + API-token
path. **No bugs found — the tool works correctly against a real Proxmox API.**

- **doctor** connected via an `root@pam!aiops` API token over the real
  `/api2/json` HTTPS endpoint (8006).
- **Reads matched ground truth exactly** (cross-checked with `pct list` /
  `pvesh` / `pvesm status`): `ct list` (ct100 running, 256 MB, node pve1),
  `cluster nodes` (pve1 online, 2 cpu, mem/maxmem), `storage list` (local dir).
- **Full write → audit → undo → verified restore** on a real container:
  `ct stop 100` → server reports `stopped`, audit row `ct_stop|ok` → `undo apply`
  → `ct_start`, `effectVerified: true`, server reports `running`. Both the CLI
  write and the undo landed audit rows in the same `audit.db` (unbypassable-audit
  claim holds).
- **Bug class #11 (undeclared `requests` transport dep) confirmed FIXED**: a clean
  `uv sync` + proxmoxer https connect succeeded, i.e. `requests` is present.

Not covered by this run: multi-node cluster/quorum, HA, live VM (KVM guest) boot,
backup jobs, and the firewall/pool/storage *write* paths — the node was a
single-node nested lab with one LXC container. The checklist below still stands
for those.

> **Lab recipe (for re-runs):** Debian 12 cloud image → `virt-customize`
> (root pw + ssh key + `systemctl mask cloud-init` + networkd DHCP) →
> `apt install proxmox-ve` on top → **disable IPv6 on the VM** before
> `pvecm updatecerts` (Proxmox puts the interface's `fe80::…%enp1s0` link-local in
> the cert SAN, which openssl rejects → `pve-ssl.pem` never generates → pveproxy
> hangs every 8006 request with `http=000`). Reach it from a workstation via an
> SSH port-forward of 8006 through the KVM host.

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

### 5. Governance records, it does not gate
- [ ] The harness authorizes nothing — there is no read-only, deny-rule, or
      approver gate to test. A `high`-risk op (e.g. `vm delete --dry-run` then
      real) runs on the agent's/account's authority and lands an audit row tagged
      `review`; `PROXMOX_AUDIT_APPROVED_BY`, if set, is recorded as an optional
      annotation, never as a requirement.
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
