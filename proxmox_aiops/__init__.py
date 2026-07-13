"""proxmox-aiops — governed VM/container lifecycle operations for Proxmox VE.

Standalone and self-contained: the governance harness (audit, token budget,
undo-token recording, graduated risk tiers, output sanitize) is
bundled under ``proxmox_aiops.governance`` — this package has no external
skill-family dependency. Preview: not yet full-coverage.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("proxmox-aiops")
except PackageNotFoundError:  # running from an uninstalled source tree
    __version__ = "0.0.0+unknown"
