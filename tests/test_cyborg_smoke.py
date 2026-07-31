"""Smoke tests for the CybORG backend module (optional ``cyborg`` extra)."""

from __future__ import annotations

import sys

import raes_adapters.cyborg


def test_cyborg_module_imports_without_the_extra() -> None:
    assert {
        "CyborgProvisioner",
        "create_cyborg_manifest",
        "create_cyborg_target",
        "load_qualification",
        "read_compatibility_patch",
    } <= set(raes_adapters.cyborg.__all__)
    assert "CybORG" not in sys.modules
