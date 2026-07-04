"""Smoke tests for the sim_adapter_base skeleton (REP-002 standup)."""

from __future__ import annotations

import sim_adapter_base


def test_package_imports_and_exposes_version() -> None:
    assert sim_adapter_base.__version__ == "0.0.0"


def test_public_api_is_explicit() -> None:
    assert "__version__" in sim_adapter_base.__all__
