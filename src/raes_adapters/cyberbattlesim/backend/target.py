"""Runtime target composition for the CyberBattleSim backend."""

from __future__ import annotations

from raes_contracts.contracts import (  # type: ignore[import-untyped]
    ParticipantConfigurationResultModel,
    ParticipantImplementationManifestModel,
    ParticipantImplementationSelectionModel,
)
from raes_runtime.registry import (  # type: ignore[import-untyped]
    RuntimeTarget,
    RuntimeTargetComponents,
)

from raes_adapters.base import build_runtime_target

from .driver import CyberBattleSimDriver, CyberBattleSimDriverProtocol
from .evaluator import CyberBattleSimEvaluator
from .manifest import (
    CYBERBATTLESIM_BACKEND_NAME,
    create_cyberbattlesim_manifest,
)
from .orchestrator import CyberBattleSimOrchestrator
from .participant_runtime import CyberBattleSimParticipantRuntime
from .provisioner import CyberBattleSimProvisioner


def create_cyberbattlesim_components(
    *,
    driver: CyberBattleSimDriverProtocol,
    seed: int | None = None,
    participant_manifest: ParticipantImplementationManifestModel | None = None,
    participant_selection: ParticipantImplementationSelectionModel | None = None,
    participant_configuration: ParticipantConfigurationResultModel | None = None,
    conformance_mode: bool = False,
) -> RuntimeTargetComponents:
    """Create components sharing one driver-owned source lifecycle."""

    return RuntimeTargetComponents(
        provisioner=CyberBattleSimProvisioner(driver),
        orchestrator=CyberBattleSimOrchestrator(),
        evaluator=CyberBattleSimEvaluator(driver),
        participant_runtime=CyberBattleSimParticipantRuntime(
            driver,
            seed=seed,
            participant_manifest=participant_manifest,
            participant_selection=participant_selection,
            participant_configuration=participant_configuration,
            conformance_mode=conformance_mode,
        ),
    )


def create_cyberbattlesim_target(
    *,
    driver: CyberBattleSimDriverProtocol | None = None,
    seed: int | None = None,
    participant_manifest: ParticipantImplementationManifestModel | None = None,
    participant_selection: ParticipantImplementationSelectionModel | None = None,
    participant_configuration: ParticipantConfigurationResultModel | None = None,
    conformance_mode: bool = False,
) -> RuntimeTarget:
    """Return a validated RAES target for the selected source profile."""

    selected_driver = driver if driver is not None else CyberBattleSimDriver()
    manifest = create_cyberbattlesim_manifest()
    components = create_cyberbattlesim_components(
        driver=selected_driver,
        seed=seed,
        participant_manifest=participant_manifest,
        participant_selection=participant_selection,
        participant_configuration=participant_configuration,
        conformance_mode=conformance_mode,
    )
    return build_runtime_target(
        CYBERBATTLESIM_BACKEND_NAME,
        manifest,
        components,
    )


__all__ = [
    "create_cyberbattlesim_components",
    "create_cyberbattlesim_target",
]
