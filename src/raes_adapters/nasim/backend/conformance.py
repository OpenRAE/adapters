"""NASim conformance composition over published RAES report shapes."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from raes_backend_protocols.backend_manifest import (  # type: ignore[import-untyped]
    BackendManifest,
)
from raes_conformance.conformance import (  # type: ignore[import-untyped]
    BackendConformanceReport,
)
from raes_contracts.diagnostics import Diagnostic  # type: ignore[import-untyped]

from raes_adapters._gym_backend import conformance as gym
from raes_adapters._gym_backend.conformance import (
    GymConformanceConfig,
    standard_probe_requirements,
)
from raes_adapters.nasim import load_qualification
from raes_adapters.nasim.scenario_ledger import (
    NASIM_TINY,
    EvidenceSelection,
    load_loss_disclosures,
    validate_all,
)

from .driver import NasimDriverProtocol
from .manifest import create_nasim_manifest
from .target import create_nasim_target

_BACKEND_EVIDENCE = "evidence.nasim.backend-conformance"
_SOURCE_EVIDENCE = "evidence.nasim.source-protocol.validated"
_SOURCE_FAILED = "nasim.source-protocol.validation-failed"
_CONFIG = GymConformanceConfig(
    name="nasim",
    backend_evidence=_BACKEND_EVIDENCE,
    source_evidence=_SOURCE_EVIDENCE,
    source_validation_failed=_SOURCE_FAILED,
    probe_requirements=standard_probe_requirements(
        _BACKEND_EVIDENCE,
        _SOURCE_EVIDENCE,
        participant_dual=(
            "supported_behavior_features",
            "supported_interaction_features",
            "supported_participant_roles",
        ),
    ),
    default_selection=NASIM_TINY,
    create_target=create_nasim_target,
    create_manifest=create_nasim_manifest,
    load_qualification=load_qualification,
    validate_all=validate_all,
    load_loss_disclosures=load_loss_disclosures,
)


def run_nasim_conformance(
    *,
    driver: NasimDriverProtocol | None = None,
    seed: int | None = None,
) -> BackendConformanceReport:
    """Run the published RAES target conformance probe for NASim."""

    return gym.run_conformance(_CONFIG, driver, seed)


def nasim_backend_conformance_payload(
    report: BackendConformanceReport,
) -> dict[str, object]:
    """Serialize the canonical report through the published RAES projector."""

    return gym.conformance_payload(report)


def nasim_manifest_capability_evidence(
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


def nasim_manifest_capability_evidence_gaps(
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


def nasim_declared_weaknesses(
    selection: EvidenceSelection = NASIM_TINY,
) -> tuple[str, ...]:
    """Return declared source-protocol limitations and loss disclosures."""

    return gym.declared_weaknesses(_CONFIG, selection)


def nasim_source_protocol_diagnostics(
    selection: EvidenceSelection = NASIM_TINY,
) -> tuple[Diagnostic, ...]:
    """Validate source-protocol evidence and emit RAES diagnostics."""

    return gym.source_protocol_diagnostics(_CONFIG, selection)


__all__ = [
    "nasim_backend_conformance_payload",
    "nasim_declared_weaknesses",
    "nasim_manifest_capability_evidence",
    "nasim_manifest_capability_evidence_gaps",
    "nasim_source_protocol_diagnostics",
    "run_nasim_conformance",
]
