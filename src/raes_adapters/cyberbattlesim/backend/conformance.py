"""CyberBattleSim conformance composition over published RAES report shapes."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from raes_backend_protocols.backend_manifest import (  # type: ignore[import-untyped]
    BackendManifest,
)
from raes_conformance.conformance import (  # type: ignore[import-untyped]
    BackendConformanceReport,
)
from raes_contracts.diagnostics import (  # type: ignore[import-untyped]
    Diagnostic,
    Severity,
    diagnostic_model,
)

from raes_adapters.base import run_conformance_probe
from raes_adapters.base.manifest_evidence import (
    backend_conformance_payload,
    declared_capability_evidence,
    manifest_payload,
)
from raes_adapters.cyberbattlesim import load_qualification
from raes_adapters.cyberbattlesim.scenario_ledger import (
    CYBERBATTLE_CHAIN,
    EvidenceSelection,
    load_loss_disclosures,
    validate_all,
)

from ._diagnostics import diagnostic_address
from .driver import CyberBattleSimDriverProtocol
from .manifest import create_cyberbattlesim_manifest
from .target import create_cyberbattlesim_target

_BACKEND_CONFORMANCE_EVIDENCE = "evidence.cyberbattlesim.backend-conformance"
_SOURCE_PROTOCOL_EVIDENCE = "evidence.cyberbattlesim.source-protocol.validated"
_CAPABILITY_PROBE_REQUIREMENTS: Mapping[str, tuple[str, ...]] = {
    "/capabilities/cleanup/supported_action_kinds": (_BACKEND_CONFORMANCE_EVIDENCE,),
    "/capabilities/cleanup/supported_contract_versions": (_BACKEND_CONFORMANCE_EVIDENCE,),
    "/capabilities/cleanup/supported_verification_methods": (_BACKEND_CONFORMANCE_EVIDENCE,),
    "/capabilities/cleanup/supports_residual_state_disclosure": (_BACKEND_CONFORMANCE_EVIDENCE,),
    "/capabilities/cleanup/supports_reusable_state": (_BACKEND_CONFORMANCE_EVIDENCE,),
    "/capabilities/evaluator/preserves_binding_provenance": (_BACKEND_CONFORMANCE_EVIDENCE,),
    "/capabilities/evaluator/supported_evidence_channels": (_BACKEND_CONFORMANCE_EVIDENCE,),
    "/capabilities/evaluator/supported_predicate_families": (_BACKEND_CONFORMANCE_EVIDENCE,),
    "/capabilities/evaluator/supported_quantifiers": (_BACKEND_CONFORMANCE_EVIDENCE,),
    "/capabilities/evaluator/supported_sections": (_BACKEND_CONFORMANCE_EVIDENCE,),
    "/capabilities/evaluator/supported_time_domains": (_BACKEND_CONFORMANCE_EVIDENCE,),
    "/capabilities/evaluator/supported_truth_outcomes": (_BACKEND_CONFORMANCE_EVIDENCE,),
    "/capabilities/evaluator/supports_objectives": (_BACKEND_CONFORMANCE_EVIDENCE,),
    "/capabilities/evaluator/supports_scoring": (_BACKEND_CONFORMANCE_EVIDENCE,),
    "/capabilities/orchestrator/supported_sections": (_BACKEND_CONFORMANCE_EVIDENCE,),
    "/capabilities/orchestrator/supported_workflow_features": (_BACKEND_CONFORMANCE_EVIDENCE,),
    "/capabilities/orchestrator/supports_workflows": (_BACKEND_CONFORMANCE_EVIDENCE,),
    "/capabilities/participant_runtime/feature_support": (
        _BACKEND_CONFORMANCE_EVIDENCE,
        _SOURCE_PROTOCOL_EVIDENCE,
    ),
    "/capabilities/participant_runtime/supported_behavior_features": (
        _BACKEND_CONFORMANCE_EVIDENCE,
        _SOURCE_PROTOCOL_EVIDENCE,
    ),
    "/capabilities/participant_runtime/supported_interaction_features": (
        _BACKEND_CONFORMANCE_EVIDENCE,
        _SOURCE_PROTOCOL_EVIDENCE,
    ),
    "/capabilities/participant_runtime/supported_participant_roles": (
        _BACKEND_CONFORMANCE_EVIDENCE,
        _SOURCE_PROTOCOL_EVIDENCE,
    ),
    "/capabilities/provisioner/max_total_nodes": (
        _BACKEND_CONFORMANCE_EVIDENCE,
        _SOURCE_PROTOCOL_EVIDENCE,
    ),
    "/capabilities/provisioner/supported_account_features": (
        _BACKEND_CONFORMANCE_EVIDENCE,
        _SOURCE_PROTOCOL_EVIDENCE,
    ),
    "/capabilities/provisioner/supported_node_types": (
        _BACKEND_CONFORMANCE_EVIDENCE,
        _SOURCE_PROTOCOL_EVIDENCE,
    ),
    "/capabilities/provisioner/supported_os_families": (
        _BACKEND_CONFORMANCE_EVIDENCE,
        _SOURCE_PROTOCOL_EVIDENCE,
    ),
    "/capabilities/provisioner/supports_accounts": (
        _BACKEND_CONFORMANCE_EVIDENCE,
        _SOURCE_PROTOCOL_EVIDENCE,
    ),
}


def run_cyberbattlesim_conformance(
    *,
    driver: CyberBattleSimDriverProtocol | None = None,
    seed: int | None = None,
) -> BackendConformanceReport:
    """Run the published RAES target conformance probe for CyberBattleSim."""

    return run_conformance_probe(
        create_cyberbattlesim_target(
            driver=driver,
            seed=seed,
        )
    )


def cyberbattlesim_backend_conformance_payload(
    report: BackendConformanceReport,
) -> dict[str, object]:
    """Serialize the canonical report through the published RAES projector."""

    return backend_conformance_payload(report)


def cyberbattlesim_manifest_capability_evidence(
    manifest: BackendManifest | None = None,
    *,
    payload: Mapping[str, object] | None = None,
    conformance_report: BackendConformanceReport | None = None,
    source_diagnostics: Iterable[Diagnostic] = (),
) -> dict[str, tuple[str, ...]]:
    """Return evidence references for declared affirmative manifest surfaces."""

    evidence, _gaps = declared_capability_evidence(
        manifest_payload(manifest, payload, create_cyberbattlesim_manifest),
        _CAPABILITY_PROBE_REQUIREMENTS,
        _passed_probe_evidence_refs(conformance_report, source_diagnostics),
    )
    return evidence


def cyberbattlesim_manifest_capability_evidence_gaps(
    manifest: BackendManifest | None = None,
    *,
    payload: Mapping[str, object] | None = None,
    conformance_report: BackendConformanceReport | None = None,
    source_diagnostics: Iterable[Diagnostic] = (),
) -> tuple[str, ...]:
    """Return declared affirmative capability surfaces with no probe evidence."""

    _evidence, gaps = declared_capability_evidence(
        manifest_payload(manifest, payload, create_cyberbattlesim_manifest),
        _CAPABILITY_PROBE_REQUIREMENTS,
        _passed_probe_evidence_refs(conformance_report, source_diagnostics),
    )
    return gaps


def cyberbattlesim_declared_weaknesses(
    selection: EvidenceSelection = CYBERBATTLE_CHAIN,
) -> tuple[str, ...]:
    """Return declared source-protocol limitations and loss disclosures."""

    qualification = load_qualification()
    admission = qualification.get("admission")
    limitations: list[str] = []
    if isinstance(admission, dict):
        raw_limitations = admission.get("limitations")
        if isinstance(raw_limitations, list):
            limitations = [
                f"limitation:{value}" for value in raw_limitations if isinstance(value, str)
            ]
    losses = [
        f"loss:{loss_id}:{tier}"
        for loss_id, tier in sorted(load_loss_disclosures(selection).items())
    ]
    return tuple(sorted([*limitations, *losses]))


def cyberbattlesim_source_protocol_diagnostics(
    selection: EvidenceSelection = CYBERBATTLE_CHAIN,
) -> tuple[Diagnostic, ...]:
    """Validate source-protocol evidence and emit RAES diagnostics."""

    diagnostics: list[Diagnostic] = []
    problems = validate_all(selection)
    if problems:
        diagnostics.extend(
            Diagnostic(
                code="cyberbattlesim.source-protocol.validation-failed",
                domain="conformance",
                address=diagnostic_address(
                    f"cyberbattlesim.source-protocol.{problem.row_id}.{problem.field}"
                ),
                message=("The selected CyberBattleSim source-protocol evidence failed validation."),
            )
            for problem in problems
        )
    else:
        diagnostics.append(
            Diagnostic(
                code="cyberbattlesim.source-protocol.validated",
                domain="conformance",
                address="/cyberbattlesim/source-protocol",
                message=("The selected CyberBattleSim source-protocol evidence validated."),
                severity=Severity.INFO,
            )
        )
    diagnostics.extend(
        Diagnostic(
            code="cyberbattlesim.source-protocol.declared-weakness",
            domain="conformance",
            address=f"/cyberbattlesim/source-protocol/weaknesses/{index}",
            message=("A declared CyberBattleSim source-protocol weakness remains in force."),
            severity=Severity.WARNING,
        )
        for index, _weakness in enumerate(cyberbattlesim_declared_weaknesses(selection))
    )
    return tuple(diagnostics)


def _passed_probe_evidence_refs(
    conformance_report: BackendConformanceReport | None,
    source_diagnostics: Iterable[Diagnostic],
) -> tuple[str, ...]:
    """Return evidence refs only for executable probes that passed."""

    refs: list[str] = []
    if (
        conformance_report is not None
        and conformance_report.passed
        and not conformance_report.unsupported_contract_gaps
        and not conformance_report.unsupported_capability_gaps
        and all(case.passed for case in conformance_report.cases)
    ):
        refs.append(_BACKEND_CONFORMANCE_EVIDENCE)
    source_models = [diagnostic_model(diagnostic) for diagnostic in source_diagnostics]
    if source_models and all(
        model.code != "cyberbattlesim.source-protocol.validation-failed" for model in source_models
    ):
        refs.append(_SOURCE_PROTOCOL_EVIDENCE)
    return tuple(refs)


__all__ = [
    "cyberbattlesim_backend_conformance_payload",
    "cyberbattlesim_declared_weaknesses",
    "cyberbattlesim_manifest_capability_evidence",
    "cyberbattlesim_manifest_capability_evidence_gaps",
    "cyberbattlesim_source_protocol_diagnostics",
    "run_cyberbattlesim_conformance",
]
