# Live verification — proxmox-aiops

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
