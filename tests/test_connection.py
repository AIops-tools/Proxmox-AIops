"""Tests for ConnectionManager (proxmox_aiops/connection.py).

``proxmoxer.ProxmoxAPI`` is patched so no HTTP happens; secret resolution is
patched to a constant so no encrypted store / env var is needed. Assertions
cover session reuse, the default-node side table, token vs password auth wiring,
the malformed-token guard, and the disconnect bookkeeping.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import proxmox_aiops.config as config_mod
import proxmox_aiops.connection as conn_mod
from proxmox_aiops.config import AppConfig, TargetConfig
from proxmox_aiops.connection import ConnectionManager, get_default_node


@pytest.fixture(autouse=True)
def _fake_secret(monkeypatch):
    monkeypatch.setattr(config_mod, "_resolve_secret", lambda name: "SECRET-VALUE")


@pytest.fixture
def fake_proxmoxapi(monkeypatch):
    calls: list[dict] = []

    def _factory(host, **kwargs):
        calls.append({"host": host, **kwargs})
        return MagicMock(name=f"ProxmoxAPI({host})")

    monkeypatch.setattr(conn_mod, "ProxmoxAPI", _factory)
    return calls


def _cfg(**overrides) -> AppConfig:
    base = dict(name="pve-lab", host="10.0.0.1", user="root@pam!tok", node="pve1")
    base.update(overrides)
    return AppConfig(targets=(TargetConfig(**base),))


@pytest.mark.unit
def test_connect_default_target_and_default_node(fake_proxmoxapi):
    mgr = ConnectionManager(_cfg())
    conn = mgr.connect()
    assert get_default_node(conn) == "pve1"
    assert fake_proxmoxapi[0]["host"] == "10.0.0.1:8006"
    assert fake_proxmoxapi[0]["token_name"] == "tok"
    assert fake_proxmoxapi[0]["token_value"] == "SECRET-VALUE"


@pytest.mark.unit
def test_connect_reuses_session(fake_proxmoxapi):
    mgr = ConnectionManager(_cfg())
    first = mgr.connect("pve-lab")
    second = mgr.connect("pve-lab")
    assert first is second
    assert len(fake_proxmoxapi) == 1  # ProxmoxAPI built once


@pytest.mark.unit
def test_password_auth_passes_password(fake_proxmoxapi):
    mgr = ConnectionManager(_cfg(auth_kind="password", user="root@pam"))
    mgr.connect()
    kw = fake_proxmoxapi[0]
    assert kw["password"] == "SECRET-VALUE"
    assert "token_name" not in kw


@pytest.mark.unit
def test_token_auth_without_bang_raises(fake_proxmoxapi):
    mgr = ConnectionManager(_cfg(user="root@pam"))  # no '!tokenid'
    with pytest.raises(ValueError, match="user@realm!tokenid"):
        mgr.connect()


@pytest.mark.unit
def test_disconnect_clears_node_table(fake_proxmoxapi):
    mgr = ConnectionManager(_cfg())
    conn = mgr.connect("pve-lab")
    assert mgr.list_connected() == ["pve-lab"]
    mgr.disconnect("pve-lab")
    assert mgr.list_connected() == []
    assert get_default_node(conn) == ""  # side table entry removed


@pytest.mark.unit
def test_disconnect_all_and_list_targets(fake_proxmoxapi):
    mgr = ConnectionManager(_cfg())
    mgr.connect("pve-lab")
    assert mgr.list_targets() == ["pve-lab"]
    mgr.disconnect_all()
    assert mgr.list_connected() == []


@pytest.mark.unit
def test_from_config_uses_passed_config(fake_proxmoxapi):
    mgr = ConnectionManager.from_config(_cfg())
    assert mgr.list_targets() == ["pve-lab"]
