"""CLI package for proxmox-aiops.

Re-exports ``app`` so the pyproject entry point
``proxmox-aiops = "proxmox_aiops.cli:app"`` works unchanged.
"""

from proxmox_aiops.cli._root import app

__all__ = ["app"]
