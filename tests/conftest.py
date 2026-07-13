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
