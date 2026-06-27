"""proxmox-aiops — governed VM/container lifecycle operations for Proxmox VE.

Standalone and self-contained: the governance harness (audit, token budget,
undo-token recording, graduated risk tiers, prompt-injection sanitize) is
bundled under ``proxmox_aiops.governance`` — this package has no external
skill-family dependency. Preview: not yet full-coverage.
"""

__version__ = "0.2.0"
