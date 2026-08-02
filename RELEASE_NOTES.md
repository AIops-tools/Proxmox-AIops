# Release notes — proxmox-aiops 0.10.0

Previous release: 0.9.0.

## What a real cluster showed that a single node could not

0.9.0 was verified against one Proxmox node. Five surfaces cannot exist on one
node, so they had never been exercised: quorum, HA with real resources, live
migration, `move-disk`, and a backup that actually succeeds. A second node was
built, joined into a real cluster with NFS shared storage, and all five were
driven through the governed CLI. One of them was wrong.

### `ha_status` reported HA as configured on every cluster

`configured` was a truthiness test on the entries list. On a real cluster that
is always true: with **zero HA resources defined**, Proxmox still answers
`/cluster/ha/status/current` with a synthetic `quorum` row, and keeps `master`
and per-node `lrm` rows once the HA stack has ever run. So `ha status` claimed
HA was configured while `ha resources` returned an empty list in the same
breath — the payload contradicting itself, and an agent asking "is this guest
protected?" getting yes.

`configured` is now the presence of `service` entries, which exist only when a
resource does. When it is false the entries are still returned, with a message
explaining that they describe the HA stack rather than any managed resource —
"no quorum on node X" arrives on the quorum row, and losing it would be worse
than the bug.

The carefully written not-configured branch was not dead code; it only ever
fired on a **single node with no cluster**, which is exactly what the previous
round tested.

### HA service state is a field again

A service row carries `state` and `request_state`. Both were dropped, so a
consumer could only learn whether `vm:900` was started by parsing the human
sentence `"vm:900 (pve1, started)"`. Both are fields now, present and
null-valued on the stack rows that have no state.

## The four surfaces that were already correct

Recorded because "we checked and found nothing" is worth as much as a fix:

- **quorum** — `quorate` flips correctly, and a downed node's `cpu`/`mem`/
  `uptime` come back **null, not 0**.
- **live migration** — the task resolves to `OK`, the guest runs on the target,
  and `undo apply` migrates it back; the reverse task's UPID belongs to the
  other node and is polled there. Proxmox's own log: `downtime 143 ms`.
- **`move-disk`** — between directory storages with the guest running, and onto
  NFS with `--delete`; `undo apply` moves it back. The dry-run runs the guards
  and lands an audit row with **no** undo token.
- **backup and restore** — a real 294 MiB archive with `exitstatus OK`; a
  restore into a free vmid creates a real VM whose undo deletes it; restoring
  **over** an existing vmid without `--force` is refused with exit 1.

## Upgrading

`ha_status`'s `configured` will now read `false` on clusters where it previously
read `true` — that is the fix, not a regression. Anything keying off it as
"does this cluster have HA machinery running" should read the `entries` list
instead, which is unchanged.
