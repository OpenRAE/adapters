"""CyberBattleSim conformance composition over published RAES report shapes."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from raes_backend_protocols.backend_manifest import (  # type: ignore[import-untyped]
    BackendManifest,
)
from raes_conformance.conformance import (  # type: ignore[import-untyped]
    BackendConformanceReport,
)
from raes_contracts.contracts import (  # type: ignore[import-untyped]
    ParticipantConfigurationResultModel,
    ParticipantImplementationManifestModel,
    ParticipantImplementationSelectionModel,
)
from raes_contracts.diagnostics import Diagnostic  # type: ignore[import-untyped]

from raes_adapters._gym_backend import conformance as gym
from raes_adapters._gym_backend.conformance import (
    GymConformanceConfig,
    standard_probe_requirements,
)
from raes_adapters.base import run_conformance_probe
from raes_adapters.cyberbattlesim import load_qualification
from raes_adapters.cyberbattlesim.scenario_ledger import (
    CYBERBATTLE_CHAIN,
    EvidenceSelection,
    load_loss_disclosures,
    validate_all,
)

from .driver import CyberBattleSimDriverProtocol
from .manifest import create_cyberbattlesim_manifest
from .target import create_cyberbattlesim_target

_BACKEND_EVIDENCE = "evidence.cyberbattlesim.backend-conformance"
_SOURCE_EVIDENCE = "evidence.cyberbattlesim.source-protocol.validated"
_SOURCE_FAILED = "cyberbattlesim.source-protocol.validation-failed"
_CONFIG = GymConformanceConfig(
    name="cyberbattlesim",
    backend_evidence=_BACKEND_EVIDENCE,
    source_evidence=_SOURCE_EVIDENCE,
    source_validation_failed=_SOURCE_FAILED,
    probe_requirements=standard_probe_requirements(
        _BACKEND_EVIDENCE,
        _SOURCE_EVIDENCE,
        participant_dual=(
            "execution_bindings",
            "feature_support",
            "max_autonomous_action_attempts",
            "max_autonomous_burst_size",
            "max_autonomous_in_flight",
            "max_autonomous_occurrences",
            "max_autonomous_participants",
            "max_autonomous_retries_per_occurrence",
            "max_concurrent_actions",
            "max_execution_services",
            "supported_autonomous_action_contracts",
            "supported_autonomous_observation_boundaries",
            "supported_autonomous_policy_profiles",
            "supported_autonomous_selection_strategies",
            "supported_autonomous_target_addresses",
            "supported_behavior_features",
            "supported_execution_control_actions",
            "supported_interaction_features",
            "supported_participant_roles",
            "supports_autonomous_execution",
            "supports_bounded_concurrency",
            "supports_execution_control",
        ),
    ),
    default_selection=CYBERBATTLE_CHAIN,
    create_target=create_cyberbattlesim_target,
    create_manifest=create_cyberbattlesim_manifest,
    load_qualification=load_qualification,
    validate_all=validate_all,
    load_loss_disclosures=load_loss_disclosures,
)


def run_cyberbattlesim_conformance(
    *,
    driver: CyberBattleSimDriverProtocol | None = None,
    seed: int | None = None,
    participant_manifest: ParticipantImplementationManifestModel | None = None,
    participant_selection: ParticipantImplementationSelectionModel | None = None,
    participant_configuration: ParticipantConfigurationResultModel | None = None,
) -> BackendConformanceReport:
    """Run the published RAES target conformance probe for CyberBattleSim."""

    if participant_manifest is not None:
        return run_conformance_probe(
            create_cyberbattlesim_target(
                driver=driver,
                seed=seed,
                participant_manifest=participant_manifest,
                participant_selection=participant_selection,
                participant_configuration=participant_configuration,
                conformance_mode=True,
            )
        )
    return gym.run_conformance(_CONFIG, driver, seed)


def cyberbattlesim_backend_conformance_payload(
    report: BackendConformanceReport,
) -> dict[str, object]:
    """Serialize the canonical report through the published RAES projector."""

    return gym.conformance_payload(report)


def cyberbattlesim_manifest_capability_evidence(
    manifest: BackendManifest | None = None,
    *,
    payload: Mapping[str, object] | None = None,
    conformance_report: BackendConformanceReport | None = None,
    source_diagnostics: Iterable[Diagnostic] = (),
) -> dict[str, tuple[str, ...]]:
    """Return evidence references for declared affirmative manifest surfaces."""

    return gym.capability_evidence(
        _CONFIG, manifest, payload, conformance_report, source_diagnostics
    )


def cyberbattlesim_manifest_capability_evidence_gaps(
    manifest: BackendManifest | None = None,
    *,
    payload: Mapping[str, object] | None = None,
    conformance_report: BackendConformanceReport | None = None,
    source_diagnostics: Iterable[Diagnostic] = (),
) -> tuple[str, ...]:
    """Return declared affirmative capability surfaces with no probe evidence."""

    return gym.capability_evidence_gaps(
        _CONFIG, manifest, payload, conformance_report, source_diagnostics
    )


def cyberbattlesim_declared_weaknesses(
    selection: EvidenceSelection = CYBERBATTLE_CHAIN,
) -> tuple[str, ...]:
    """Return declared source-protocol limitations and loss disclosures."""

    return gym.declared_weaknesses(_CONFIG, selection)


def cyberbattlesim_source_protocol_diagnostics(
    selection: EvidenceSelection = CYBERBATTLE_CHAIN,
) -> tuple[Diagnostic, ...]:
    """Validate source-protocol evidence and emit RAES diagnostics."""

    return gym.source_protocol_diagnostics(_CONFIG, selection)


__all__ = [
    "cyberbattlesim_backend_conformance_payload",
    "cyberbattlesim_declared_weaknesses",
    "cyberbattlesim_manifest_capability_evidence",
    "cyberbattlesim_manifest_capability_evidence_gaps",
    "cyberbattlesim_source_protocol_diagnostics",
    "run_cyberbattlesim_conformance",
]
