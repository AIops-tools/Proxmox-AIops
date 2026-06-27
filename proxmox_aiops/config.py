"""Configuration management for Proxmox AIops.

Loads connection targets and settings from a YAML config file. Secrets (API
token secret / login password) are NEVER stored in the config file and never
on disk in plaintext: they live in the encrypted store
``~/.proxmox-aiops/secrets.enc`` (see :mod:`proxmox_aiops.secretstore`). For
backward compatibility a legacy plaintext env var
(``PROXMOX_<TARGET>_SECRET``) is still honoured as a fallback, with a warning
nudging migration to the encrypted store.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

from proxmox_aiops.secretstore import SecretStoreError, get_secret, has_store

CONFIG_DIR = Path.home() / ".proxmox-aiops"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
ENV_FILE = CONFIG_DIR / ".env"

# Legacy env-var prefix/suffix; also used by the migration helper.
SECRET_ENV_PREFIX = "PROXMOX_"
SECRET_ENV_SUFFIX = "_SECRET"

_log = logging.getLogger("proxmox-aiops.config")


def _secret_env_key(name: str) -> str:
    """Legacy per-target secret env var name, e.g. PROXMOX_PVE_LAB_SECRET."""
    return f"{SECRET_ENV_PREFIX}{name.upper().replace('-', '_')}{SECRET_ENV_SUFFIX}"


def _resolve_secret(name: str) -> str:
    """Return a target's secret: encrypted store first, then legacy env var."""
    if has_store():
        try:
            return get_secret(name)
        except SecretStoreError:
            pass  # fall through to legacy env var
    legacy = os.environ.get(_secret_env_key(name))
    if legacy:
        _log.warning(
            "Using plaintext env var %s. Migrate to the encrypted store with "
            "'proxmox-aiops secret migrate'.",
            _secret_env_key(name),
        )
        return legacy
    raise OSError(
        f"No secret for target '{name}'. Add one with "
        f"'proxmox-aiops secret set {name}' (stored encrypted), or run "
        f"'proxmox-aiops init'."
    )


@dataclass(frozen=True)
class TargetConfig:
    """A Proxmox VE connection target.

    auth_kind:
      * ``token``    — API token; user is ``user@realm!tokenid`` and the
        secret env var holds the token UUID (recommended, least privilege).
      * ``password`` — user is ``user@realm`` and the secret env var holds
        the login password.
    """

    name: str
    host: str
    user: str
    node: str = ""
    auth_kind: Literal["token", "password"] = "token"
    port: int = 8006
    verify_ssl: bool = True

    @property
    def secret(self) -> str:
        return _resolve_secret(self.name)


@dataclass(frozen=True)
class AppConfig:
    """Top-level application config."""

    targets: tuple[TargetConfig, ...] = ()

    def get_target(self, name: str) -> TargetConfig:
        for t in self.targets:
            if t.name == name:
                return t
        available = ", ".join(t.name for t in self.targets) or "(none)"
        raise KeyError(f"Target '{name}' not found. Available: {available}")

    @property
    def default_target(self) -> TargetConfig:
        if not self.targets:
            raise ValueError("No targets configured. Check config.yaml")
        return self.targets[0]


def load_config(config_path: Path | None = None) -> AppConfig:
    """Load config from YAML; secrets come from env, never the file."""
    path = config_path or CONFIG_FILE
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {path}\n"
            f"Create {CONFIG_FILE} with a 'targets' list and put secrets in "
            f"{ENV_FILE} (chmod 600)."
        )

    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    targets = tuple(
        TargetConfig(
            name=t["name"],
            host=t["host"],
            user=t["user"],
            node=t.get("node", ""),
            auth_kind=t.get("auth_kind", "token"),
            port=t.get("port", 8006),
            verify_ssl=t.get("verify_ssl", True),
        )
        for t in raw.get("targets", [])
    )

    return AppConfig(targets=targets)
