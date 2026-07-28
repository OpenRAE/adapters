"""Smoke tests for the CybORG backend module (optional ``cyborg`` extra)."""

from __future__ import annotations

import raes_adapters.cyborg


def test_cyborg_module_imports_without_the_extra() -> None:
    # The skeleton imports cleanly with only the base install; the heavy CybORG
    # dependency (guarded behind the ``cyborg`` extra) lands under REP-004.
    assert raes_adapters.cyborg.__all__ == []
