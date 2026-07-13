"""Connection management for Proxmox VE hosts.

Thin wrapper around the ``proxmoxer`` library with per-target session reuse.

Per-connection metadata (the default node) is kept in a module-level dict
keyed by ``id(conn)`` rather than set as an attribute on the ProxmoxAPI
object. Third-party SDK proxy objects must not be monkey-patched — same
discipline as 踩坑 #32 (pyVmomi 8.x ManagedObject rejects setattr); we apply
it pre-emptively to proxmoxer to keep the harness pattern consistent.
"""

from __future__ import annotations

from typing import Any

from proxmoxer import ProxmoxAPI

from proxmox_aiops.config import AppConfig, TargetConfig, load_config

# Side-stored per-connection metadata, keyed by id(conn). See module docstring.
_CONN_NODE: dict[int, str] = {}

# HTTP timeout (seconds) for every proxmoxer API call — without it a hung PVE
# endpoint blocks the tool call indefinitely.
_TIMEOUT = 30


def get_default_node(conn: Any) -> str:
    """Return the default node stashed for ``conn`` (empty if none)."""
    return _CONN_NODE.get(id(conn), "")


class ConnectionManager:
    """Manages connections to multiple Proxmox VE targets with session reuse."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._connections: dict[str, Any] = {}

    @classmethod
    def from_config(cls, config: AppConfig | None = None) -> ConnectionManager:
        cfg = config or load_config()
        return cls(cfg)

    def connect(self, target_name: str | None = None) -> Any:
        """Connect to a target by name, or the default target."""
        target = (
            self._config.get_target(target_name)
            if target_name
            else self._config.default_target
        )

        cached = self._connections.get(target.name)
        if cached is not None:
            return cached

        conn = self._create_connection(target)
        self._connections[target.name] = conn
        _CONN_NODE[id(conn)] = target.node
        return conn

    def disconnect(self, target_name: str) -> None:
        """Forget a connection (proxmoxer is stateless HTTP; just drop it)."""
        conn = self._connections.pop(target_name, None)
        if conn is not None:
            _CONN_NODE.pop(id(conn), None)

    def disconnect_all(self) -> None:
        for name in list(self._connections):
            self.disconnect(name)

    def list_targets(self) -> list[str]:
        return [t.name for t in self._config.targets]

    def list_connected(self) -> list[str]:
        return list(self._connections.keys())

    @staticmethod
    def _create_connection(target: TargetConfig) -> Any:
        """Create a new proxmoxer ProxmoxAPI session.

        Token auth splits ``user@realm!tokenid`` into the user portion and the
        token name expected by proxmoxer's ``token_name`` / ``token_value``.
        """
        host = f"{target.host}:{target.port}"
        if target.auth_kind == "token":
            user, _, token_name = target.user.partition("!")
            if not token_name:
                raise ValueError(
                    "Token auth requires user in the form "
                    "'user@realm!tokenid' (got no '!' separator)."
                )
            return ProxmoxAPI(
                host,
                user=user,
                token_name=token_name,
                token_value=target.secret,
                verify_ssl=target.verify_ssl,
                timeout=_TIMEOUT,
            )
        return ProxmoxAPI(
            host,
            user=target.user,
            password=target.secret,
            verify_ssl=target.verify_ssl,
            timeout=_TIMEOUT,
        )
