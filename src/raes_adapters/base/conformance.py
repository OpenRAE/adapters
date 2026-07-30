"""Thin target-conformance composition over the published RAES runner."""

from __future__ import annotations

from pathlib import Path

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


def run_conformance_probe(
    target: RuntimeTarget,
    *,
    profile: BackendProfileSelector | None = None,
    fixture_root_for_tests: Path | None = None,
    profiles_root_for_tests: Path | None = None,
    reference_scenario: ScenarioInput | None = None,
    realization_harness: RealizationConformanceHarness | None = None,
    execution_basis: ExecutionBasis = ExecutionBasis.HERMETIC_LIVE,
    realization_envelope: BackendRealizationEnvelopeModel | None = None,
    observer_version: str = "raes-realization-observer/v1",
    native_conformance: bool = False,
) -> BackendConformanceReport:
    """Return the exact report produced by ``run_target_conformance``.

    Fixture/profile-root overrides are named as test injection deliberately;
    the published RAES corpus roots remain the production defaults. This helper
    does not infer a local profile, add cases, or strengthen the runner's
    bounded claim.
    """

    return run_target_conformance(
        target,
        profile=profile,
        root=fixture_root_for_tests,
        profiles_root=profiles_root_for_tests,
        reference_scenario=reference_scenario,
        realization_harness=realization_harness,
        execution_basis=execution_basis,
        realization_envelope=realization_envelope,
        observer_version=observer_version,
        native_conformance=native_conformance,
    )


__all__ = ["run_conformance_probe"]
