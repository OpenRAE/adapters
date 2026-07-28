"""Smoke tests for the cyborg_adapter skeleton (REP-002 standup)."""

from __future__ import annotations

import raes_adapter_cyborg
import sim_adapter_base


def test_package_imports_and_exposes_version() -> None:
    assert raes_adapter_cyborg.__version__ == "0.0.0"


def test_depends_on_shared_base() -> None:
    # The workspace-path dependency on sim_adapter_base resolves in this
    # adapter's isolated environment.
    assert sim_adapter_base.__version__ == "0.0.0"
