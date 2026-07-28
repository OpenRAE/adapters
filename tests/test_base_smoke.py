"""Smoke tests for the always-available base plumbing module (REP-002 standup)."""

from __future__ import annotations

import raes_adapters.base


def test_base_module_imports() -> None:
    assert raes_adapters.base.__all__ == []
