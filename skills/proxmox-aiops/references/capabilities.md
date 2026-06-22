# proxmox-aiops capabilities

23 MCP tools (8 read / 15 write). Every tool is wrapped with the bundled
`@governed_tool` harness (audit + budget + risk-tier + undo). Typical response
sizes are small high-signal summaries, not full API blobs.

## VM lifecycle (11)

| Tool | R/W | Inverse (undo) | Typical response |
|------|:---:|----------------|------------------|
| `vm_list` | R | — | ~50–500 tok (one row per VM) |
| `vm_get` | R | — | ~120 tok |
| `vm_config` | R | — | ~120 tok |
| `vm_start` | W | `vm_stop` | task UPID |
| `vm_stop` | W | `vm_start` | task UPID |
| `vm_shutdown` | W | `vm_start` | task UPID |
| `vm_reboot` | W | — (no inverse) | task UPID |
| `vm_reconfigure` | W | `vm_reconfigure` (prior cores/memory) | applied + previous |
| `vm_clone` | W | `vm_delete(newid)` | task UPID |
| `vm_delete` | W | — (irreversible, risk=high) | task UPID |
| `vm_migrate` | W | `vm_migrate` (back to source node) | task UPID |

## Snapshots (4)

| Tool | R/W | Inverse | Notes |
|------|:---:|---------|-------|
| `vm_list_snapshots` | R | — | name + description |
| `vm_snapshot_create` | W | `vm_snapshot_delete` | |
| `vm_snapshot_delete` | W | — | |
| `vm_snapshot_rollback` | W | — (irreversible, risk=high) | discards newer state |

## LXC containers (3)

| Tool | R/W | Inverse |
|------|:---:|---------|
| `ct_list` | R | — |
| `ct_start` | W | `ct_stop` |
| `ct_stop` | W | `ct_start` |

## Cluster / tasks (3)

| Tool | R/W | Notes |
|------|:---:|-------|
| `node_list` | R | status, cpu load, memory |
| `cluster_status` | R | membership + quorum |
| `task_status` | R | poll an async UPID (clone/migrate/backup) |

## Storage (2)

| Tool | R/W | Notes |
|------|:---:|-------|
| `storage_list` | R | pools: type, total/used/avail |
| `storage_content` | R | volumes: ISOs, disk images, backups, templates |

## Not yet covered (preview scope)

VM create-from-scratch / template instantiation, guest agent exec, backup
(vzdump) creation, container create/clone/destroy, pool & ACL management. These
are the natural next additions — each gets a matching `@governed_tool` wrapper
and an `undo=` declaration where a clean inverse exists.
