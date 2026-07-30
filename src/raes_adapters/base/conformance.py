"""Thin target-conformance composition over the published RAES runner."""

from __future__ import annotations

from pathlib import Path
from typing import NotRequired, TypedDict, Unpack

from raes_conformance.conformance import (  # type: ignore[import-untyped]
    BackendConformanceReport,
    run_target_conformance,
)
from raes_conformance.conformance.profiles import (  # type: ignore[import-untyped]
    BackendProfileSelector,
)
from raes_conformance.realization import (  # type: ignore[import-untyped]
    ExecutionBasis,
    RealizationConformanceHarness,
)
from raes_contracts.realization_envelope import (  # type: ignore[import-untyped]
    BackendRealizationEnvelopeModel,
)
from raes_processor.reference import ScenarioInput  # type: ignore[import-untyped]
from raes_runtime.registry import RuntimeTarget  # type: ignore[import-untyped]


class _ConformanceProbeOptions(TypedDict):
    profile: NotRequired[BackendProfileSelector | None]
    fixture_root_for_tests: NotRequired[Path | None]
    profiles_root_for_tests: NotRequired[Path | None]
    reference_scenario: NotRequired[ScenarioInput | None]
    realization_harness: NotRequired[RealizationConformanceHarness | None]
    execution_basis: NotRequired[ExecutionBasis]
    realization_envelope: NotRequired[BackendRealizationEnvelopeModel | None]
    observer_version: NotRequired[str]
    native_conformance: NotRequired[bool]


def run_conformance_probe(
    target: RuntimeTarget,
    **options: Unpack[_ConformanceProbeOptions],
) -> BackendConformanceReport:
    """Return the exact report produced by ``run_target_conformance``.

    Fixture/profile-root overrides are named as test injection deliberately;
    the published RAES corpus roots remain the production defaults. This helper
    does not infer a local profile, add cases, or strengthen the runner's
    bounded claim.
    """

    return run_target_conformance(
        target,
        profile=options.get("profile"),
        root=options.get("fixture_root_for_tests"),
        profiles_root=options.get("profiles_root_for_tests"),
        reference_scenario=options.get("reference_scenario"),
        realization_harness=options.get("realization_harness"),
        execution_basis=options.get("execution_basis", ExecutionBasis.HERMETIC_LIVE),
        realization_envelope=options.get("realization_envelope"),
        observer_version=options.get(
            "observer_version",
            "raes-realization-observer/v1",
        ),
        native_conformance=options.get("native_conformance", False),
    )


__all__ = ["run_conformance_probe"]
