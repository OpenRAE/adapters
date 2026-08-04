"""NASim conformance composition over published RAES report shapes."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from raes_backend_protocols.backend_manifest import (  # type: ignore[import-untyped]
    BackendManifest,
)
from raes_backend_protocols.manifest import (  # type: ignore[import-untyped]
    backend_manifest_payload,
)
from raes_conformance.conformance import (  # type: ignore[import-untyped]
    BackendConformanceReport,
)
from raes_contracts.diagnostics import (  # type: ignore[import-untyped]
    Diagnostic,
    diagnostic_payload,
)

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

# The single public seed for the deterministic PR conformance lane. The suite
# never derives seed or case order from time, PR number, hashing, environment,
# or global random state (see nasim-conformance-guardrails.md).
PR_CONFORMANCE_SEED = 20260802

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


def run_nasim_pr_conformance(
    *,
    driver: NasimDriverProtocol,
    seed: int = PR_CONFORMANCE_SEED,
) -> dict[str, object]:
    """Compose the deterministic PR conformance evidence bundle for one driver.

    Runs the published profile/corpus conformance for the profile inferred from
    the live manifest — which drives the supplied driver through the constructed
    ``RuntimeTarget``'s four surfaces on the published fixtures — then collects
    source-protocol diagnostics, closes manifest capability evidence, and gathers
    declared weaknesses into a single validated portable bundle. The three claims
    stay distinct: ``backend_conformance`` is the exact published report payload,
    ``source_diagnostics`` are RAES source evidence, and ``declared_weaknesses``
    bound the research/readiness claim.

    ``driver`` is required: the caller selects the lane explicitly (a
    deterministic injected driver for the PR/clean-install lane, a real
    ``NasimDriver`` for the manual-live lane). It fails closed by raising when a
    declared affirmative capability has no passing evidence, so a new surface can
    never ship without an evidence join.

    The hostile-failure and portable-output-leakage probes over the four
    surfaces are injected-driver constructs — they need drivers that raise on a
    chosen surface, which a real ``NasimDriver`` cannot do — so they live in the
    deterministic PR test suite (``tests/test_nasim_conformance.py``), not this
    callable. This bundle is the machine-readable success-path evidence both the
    clean-install proof and the manual-live gate run.
    """

    report = run_nasim_conformance(driver=driver, seed=seed)
    diagnostics = nasim_source_protocol_diagnostics()
    payload = backend_manifest_payload(create_nasim_manifest())
    evidence = nasim_manifest_capability_evidence(
        payload=payload,
        conformance_report=report,
        source_diagnostics=diagnostics,
    )
    gaps = nasim_manifest_capability_evidence_gaps(
        payload=payload,
        conformance_report=report,
        source_diagnostics=diagnostics,
    )
    if gaps:
        raise RuntimeError(
            "NASim manifest capability evidence is incomplete for surfaces: " + ", ".join(gaps)
        )
    return {
        "seed": seed,
        "native_conformance": report.native_conformance,
        "backend_conformance": nasim_backend_conformance_payload(report),
        "source_diagnostics": [diagnostic_payload(item) for item in diagnostics],
        "capability_evidence": {pointer: list(refs) for pointer, refs in sorted(evidence.items())},
        "declared_weaknesses": list(nasim_declared_weaknesses()),
    }


__all__ = [
    "PR_CONFORMANCE_SEED",
    "nasim_backend_conformance_payload",
    "nasim_declared_weaknesses",
    "nasim_manifest_capability_evidence",
    "nasim_manifest_capability_evidence_gaps",
    "nasim_source_protocol_diagnostics",
    "run_nasim_conformance",
    "run_nasim_pr_conformance",
]
