"""Shared fixtures for the proxmox-aiops test suite (no live Proxmox VE)."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _default_approver(monkeypatch):
    """The policy layer is secure-by-default: with no rules.yaml, high/critical
    governed calls require a named approver. Tests exercising tool behavior
    are not about that gate, so record a synthetic approver globally; the
    governance-persistence tests remove it to test the gate itself."""
    monkeypatch.setenv("PROXMOX_AUDIT_APPROVED_BY", "pytest")


@pytest.fixture(autouse=True)
def _clear_conn_node_cache():
    """Isolate the id()-keyed connection→node cache between tests.

    ``ConnectionManager.connect`` records ``_CONN_NODE[id(conn)] = node`` for the
    lifetime of a connection. In tests, MagicMock connections are short-lived and
    Python reuses ``id()`` values after GC, so a stale entry could match a fresh
    mock and make a "no node configured" assertion spuriously resolve a node.
    Clearing the cache around every test makes ordering irrelevant."""
    from proxmox_aiops.connection import _CONN_NODE

    _CONN_NODE.clear()
    yield
    _CONN_NODE.clear()
