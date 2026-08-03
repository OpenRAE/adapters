"""Runtime target composition for the PrimAITE backend."""

from __future__ import annotations

from raes_backend_protocols.backend_manifest import (  # type: ignore[import-untyped]
    BackendManifest,
)
from raes_runtime.registry import (  # type: ignore[import-untyped]
    RuntimeTarget,
    RuntimeTargetComponents,
)

from raes_adapters.base import build_runtime_target

from .driver import PrimaiteDriver, PrimaiteDriverProtocol
from .evaluator import PrimaiteEvaluator
from .manifest import PRIMAITE_BACKEND_NAME, create_primaite_manifest
from .orchestrator import PrimaiteOrchestrator
from .participant_runtime import PrimaiteParticipantRuntime
from .provisioner import PrimaiteProvisioner


def create_primaite_components(
    *,
    driver: PrimaiteDriverProtocol,
    manifest: BackendManifest,
    seed: int | None = None,
) -> RuntimeTargetComponents:
    """Create components sharing one driver-owned source lifecycle.

    The provisioner is bound to the manifest's realization envelope so it accepts
    only a plan that joins to the selected realization.
    """

    if manifest.realization_envelope is None:
        raise RuntimeError("PrimAITE manifest requires a realization envelope.")
    return RuntimeTargetComponents(
        provisioner=PrimaiteProvisioner(driver, manifest.realization_envelope.identity),
        orchestrator=PrimaiteOrchestrator(),
        evaluator=PrimaiteEvaluator(driver),
        participant_runtime=PrimaiteParticipantRuntime(driver, seed=seed),
    )


def create_primaite_target(
    *,
    driver: PrimaiteDriverProtocol | None = None,
    seed: int | None = None,
) -> RuntimeTarget:
    """Return a validated RAES target for the selected source profile."""

    selected_driver = driver if driver is not None else PrimaiteDriver()
    manifest = create_primaite_manifest()
    components = create_primaite_components(driver=selected_driver, manifest=manifest, seed=seed)
    return build_runtime_target(PRIMAITE_BACKEND_NAME, manifest, components)


__all__ = [
    "create_primaite_components",
    "create_primaite_target",
]
