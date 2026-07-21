"""Shared fixtures for the proxmox-aiops test suite (no live Proxmox VE)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

#: proxmoxer resource-proxy methods that change server state. A dry-run may walk
#: the resource path and may GET (locating a VM across nodes is a read), but it
#: must never reach one of these.
MUTATING_VERBS = frozenset({"post", "put", "delete", "create", "set"})


def assert_no_mutating_call(conn: MagicMock) -> None:
    """Assert a mocked proxmoxer connection was never asked to change anything.

    The invariant a dry-run must satisfy is *not* 'made no call' — previews are
    allowed to read, and routing them through the governed twin means they also
    write an audit row. It is 'issued no mutating verb'. Checking the whole
    ``mock_calls`` tree catches a mutation reached by any path, which a targeted
    ``some.specific.post.assert_not_called()`` would miss.
    """
    offenders = [
        name for name, _args, _kwargs in conn.mock_calls
        if name.rsplit(".", 1)[-1] in MUTATING_VERBS
    ]
    assert offenders == [], f"dry-run issued mutating call(s): {offenders}"


@pytest.fixture(autouse=True)
def _isolate_ops_home(tmp_path, monkeypatch):
    """Keep every governed call the suite makes out of the developer's real home.

    ``@governed_tool`` audits unconditionally, so any test that reaches a
    governed twin — including a ``dry_run=True`` preview, which is audited by
    design — appends to ``~/.proxmox-aiops/audit.db`` unless PROXMOX_AIOPS_HOME
    is redirected. Modules with their own ``gov_home`` fixture still override
    this (they resolve after autouse fixtures); this is the floor for the ones
    that do not.

    Resetting the harness singletons is what makes the redirect real. They cache
    a path resolved at first use, so without this the FIRST test to touch the
    audit engine pins every later test's rows to its own tmp_path — which reads
    as "no audit row was written" everywhere else: exactly the false negative
    the audit assertions in this suite exist to catch.
    """
    monkeypatch.setenv("PROXMOX_AIOPS_HOME", str(tmp_path))
    _reset_harness_singletons()
    yield
    _reset_harness_singletons()


def _reset_harness_singletons() -> None:
    """Drop every cached governance singleton so the next call re-resolves paths."""
    import proxmox_aiops.governance.audit as audit_mod
    import proxmox_aiops.governance.budget as budget_mod
    import proxmox_aiops.governance.patterns as patterns_mod
    import proxmox_aiops.governance.policy as policy_mod
    import proxmox_aiops.governance.undo as undo_mod

    audit_mod.reset_engine()
    policy_mod.reset_policy_engine()
    undo_mod.reset_undo_store()
    budget_mod.reset_budget()
    patterns_mod.reset_pattern_engine()


@pytest.fixture(autouse=True)
def _default_approver(monkeypatch):
    """Record a synthetic approver annotation globally.

    The harness authorizes nothing, so this gates nothing; it only ensures the
    optional ``approved_by`` audit field is populated for tests that do not set
    their own. The governance-persistence tests clear it to show the annotation
    is genuinely optional."""
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
