"""Typed, simulator-neutral plumbing over published RAES contracts.

The module is always installed and has no simulator dependency. It provides
small mechanics for target construction, explicit clock transitions, ordered
seed application, cleanup execution, direction-specific projection, bounded
redaction, and conformance-runner composition. RAES continues to own every
portable model, protocol, validation rule, diagnostic/result shape, profile,
fixture, and conformance claim.
"""

from __future__ import annotations

from .clock import apply_logical_clock_transition
from .conformance import run_conformance_probe
from .lifecycle import execute_cleanup
from .projection import project_action, project_evaluation, project_observation
from .redaction import bounded_context_label, redact_native_value
from .seeding import apply_seed_controls
from .targets import build_runtime_target

__all__ = [
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
