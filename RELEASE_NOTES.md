# Release notes — proxmox-aiops 0.8.0

Previous release: 0.7.0.

## Preview fidelity

A `--dry-run` should run the same guards as the real call and leave an audit row — the line's invariant is "a dry_run MAY read; it must never write." A few write commands still showed a hand-written banner that ran no guard and audited nothing. Those are now routed through the governed twin. The real writes were always guarded and audited; only the previews were blind.


### In this tool

- **`backup restore --dry-run` now runs its guard and audits.** The only high-risk write whose CLI preview couldn't see its own guards: the preview now reads whether the target vmid exists and reports would-overwrite vs would-create (refusing an overwrite-without-force), instead of a static unaudited banner.
- `vm reconfigure` / `vm move-disk` dry-runs route through the governed twin too — they read the current config/placement and audit, rather than printing a hand-written preview.
