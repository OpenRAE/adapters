"""Smoke tests for the always-available base plumbing module."""

from __future__ import annotations

import raes_adapters.base


def test_base_module_imports() -> None:
    assert raes_adapters.base.__all__ == [
        "apply_logical_clock_transition",
        "apply_seed_controls",
        "bounded_context_label",
        "build_runtime_target",
        "execute_cleanup",
        "project_action",
        "project_evaluation",
        "project_observation",
        "redact_native_value",
        "run_conformance_probe",
    ]
