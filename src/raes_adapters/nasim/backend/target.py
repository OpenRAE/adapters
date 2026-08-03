"""Runtime target composition for the NASim backend."""

from __future__ import annotations

from raes_runtime.registry import (  # type: ignore[import-untyped]
    RuntimeTarget,
    RuntimeTargetComponents,
)

from raes_adapters.base import build_runtime_target

from .driver import NasimDriver, NasimDriverProtocol
from .evaluator import NasimEvaluator
from .manifest import NASIM_BACKEND_NAME, create_nasim_manifest
from .orchestrator import NasimOrchestrator
from .participant_runtime import NasimParticipantRuntime
from .provisioner import NasimProvisioner


def create_nasim_components(
    *,
    driver: NasimDriverProtocol,
    seed: int | None = None,
) -> RuntimeTargetComponents:
    """Create components sharing one driver-owned source lifecycle."""

    return RuntimeTargetComponents(
        provisioner=NasimProvisioner(driver),
        orchestrator=NasimOrchestrator(),
        evaluator=NasimEvaluator(driver),
        participant_runtime=NasimParticipantRuntime(
            driver,
            seed=seed,
        ),
    )


def create_nasim_target(
    *,
    driver: NasimDriverProtocol | None = None,
    seed: int | None = None,
) -> RuntimeTarget:
    """Return a validated RAES target for the selected NASim profile."""

    selected_driver = driver if driver is not None else NasimDriver()
    manifest = create_nasim_manifest()
    components = create_nasim_components(
        driver=selected_driver,
        seed=seed,
    )
    return build_runtime_target(
        NASIM_BACKEND_NAME,
        manifest,
        components,
    )


__all__ = [
    "create_nasim_components",
    "create_nasim_target",
]
