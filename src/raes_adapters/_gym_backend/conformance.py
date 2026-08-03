"""Neutral gym-backend conformance composition over published RAES reports."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import cast

from raes_backend_protocols.backend_manifest import (  # type: ignore[import-untyped]
    BackendManifest,
)
from raes_backend_protocols.manifest import (  # type: ignore[import-untyped]
    backend_manifest_payload,
)
from raes_conformance.conformance import (  # type: ignore[import-untyped]
    BackendConformanceReport,
)
from raes_conformance.conformance.report import (  # type: ignore[import-untyped]
    backend_conformance_report_payload,
)
from raes_contracts.diagnostics import (  # type: ignore[import-untyped]
    Diagnostic,
    Severity,
)
from raes_runtime.registry import RuntimeTarget  # type: ignore[import-untyped]

from raes_adapters._conformance_support import (
    manifest_capability_evidence,
    manifest_capability_evidence_gaps,
    passed_probe_evidence_refs,
)
from raes_adapters._scenario_ledger import EvidenceSelection, LedgerProblem
from raes_adapters.base import run_conformance_probe

# Capability surfaces every gym backend declares affirmatively. Backend
# conformance alone backs the control-plane surfaces; the provisioner and
# participant surfaces additionally require validated source-protocol evidence.
_BACKEND_ONLY_POINTERS = (
    "cleanup/supported_action_kinds",
    "cleanup/supported_contract_versions",
    "cleanup/supported_verification_methods",
    "cleanup/supports_residual_state_disclosure",
    "cleanup/supports_reusable_state",
    "evaluator/preserves_binding_provenance",
    "evaluator/supported_evidence_channels",
    "evaluator/supported_predicate_families",
    "evaluator/supported_quantifiers",
    "evaluator/supported_sections",
    "evaluator/supported_time_domains",
    "evaluator/supported_truth_outcomes",
    "evaluator/supports_objectives",
    "evaluator/supports_scoring",
    "orchestrator/supported_sections",
    "orchestrator/supported_workflow_features",
    "orchestrator/supports_workflows",
)
_PROVISIONER_DUAL_POINTERS = (
    "provisioner/max_total_nodes",
    "provisioner/supported_account_features",
    "provisioner/supported_node_types",
    "provisioner/supported_os_families",
    "provisioner/supports_accounts",
)


def standard_probe_requirements(
    backend_evidence: str,
    source_evidence: str,
    *,
    participant_dual: Iterable[str],
) -> dict[str, tuple[str, ...]]:
    """Build the standard capability probe-requirement map for a gym backend.

    ``participant_dual`` names the participant-runtime capability sub-fields the
    backend declares (each requires both backend and source evidence).
    """

    requirements: dict[str, tuple[str, ...]] = {
        f"/capabilities/{pointer}": (backend_evidence,) for pointer in _BACKEND_ONLY_POINTERS
    }
    for pointer in _PROVISIONER_DUAL_POINTERS:
        requirements[f"/capabilities/{pointer}"] = (backend_evidence, source_evidence)
    for field in participant_dual:
        requirements[f"/capabilities/participant_runtime/{field}"] = (
            backend_evidence,
            source_evidence,
        )
    return requirements


@dataclass(frozen=True)
class GymConformanceConfig(object):
    """Backend-local identities and bindings for conformance composition."""

    name: str
    backend_evidence: str
    source_evidence: str
    source_validation_failed: str
    probe_requirements: Mapping[str, tuple[str, ...]]
    default_selection: EvidenceSelection
    create_target: Callable[..., RuntimeTarget]
    create_manifest: Callable[[], BackendManifest]
    load_qualification: Callable[[], dict[str, object]]
    validate_all: Callable[[EvidenceSelection], list[LedgerProblem]]
    load_loss_disclosures: Callable[[EvidenceSelection], dict[str, str]]


def run_conformance(
    config: GymConformanceConfig,
    driver: object | None,
    seed: int | None,
) -> BackendConformanceReport:
    """Run the published RAES target conformance probe for the backend."""

    return run_conformance_probe(config.create_target(driver=driver, seed=seed))


def conformance_payload(report: BackendConformanceReport) -> dict[str, object]:
    """Serialize the canonical report through the published RAES projector."""

    return cast(dict[str, object], backend_conformance_report_payload(report))


def capability_evidence(
    config: GymConformanceConfig,
    manifest: BackendManifest | None,
    payload: Mapping[str, object] | None,
    conformance_report: BackendConformanceReport | None,
    source_diagnostics: Iterable[Diagnostic],
) -> dict[str, tuple[str, ...]]:
    """Return evidence references for declared affirmative manifest surfaces."""

    return manifest_capability_evidence(
        _manifest_payload(config, manifest, payload),
        probe_requirements=config.probe_requirements,
        passed_evidence_refs=_passed_refs(config, conformance_report, source_diagnostics),
    )


def capability_evidence_gaps(
    config: GymConformanceConfig,
    manifest: BackendManifest | None,
    payload: Mapping[str, object] | None,
    conformance_report: BackendConformanceReport | None,
    source_diagnostics: Iterable[Diagnostic],
) -> tuple[str, ...]:
    """Return declared affirmative capability surfaces with no probe evidence."""

    return manifest_capability_evidence_gaps(
        _manifest_payload(config, manifest, payload),
        probe_requirements=config.probe_requirements,
        passed_evidence_refs=_passed_refs(config, conformance_report, source_diagnostics),
    )


def declared_weaknesses(
    config: GymConformanceConfig,
    selection: EvidenceSelection,
) -> tuple[str, ...]:
    """Return declared source-protocol limitations and loss disclosures."""

    qualification = config.load_qualification()
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
        for loss_id, tier in sorted(config.load_loss_disclosures(selection).items())
    ]
    return tuple(sorted([*limitations, *losses]))


def source_protocol_diagnostics(
    config: GymConformanceConfig,
    selection: EvidenceSelection,
) -> tuple[Diagnostic, ...]:
    """Validate source-protocol evidence and emit RAES diagnostics."""

    name = config.name
    diagnostics: list[Diagnostic] = []
    problems = config.validate_all(selection)
    if problems:
        diagnostics.extend(
            Diagnostic(
                code=config.source_validation_failed,
                domain="conformance",
                address=f"/{name}/source-protocol/{problem.row_id}/{problem.field}",
                message=("The selected source-protocol evidence failed validation."),
            )
            for problem in problems
        )
    else:
        diagnostics.append(
            Diagnostic(
                code=f"{name}.source-protocol.validated",
                domain="conformance",
                address=f"/{name}/source-protocol",
                message=("The selected source-protocol evidence validated."),
                severity=Severity.INFO,
            )
        )
    diagnostics.extend(
        Diagnostic(
            code=f"{name}.source-protocol.declared-weakness",
            domain="conformance",
            address=f"/{name}/source-protocol/weaknesses/{index}",
            message=("A declared source-protocol weakness remains in force."),
            severity=Severity.WARNING,
        )
        for index, _weakness in enumerate(declared_weaknesses(config, selection))
    )
    return tuple(diagnostics)


def _manifest_payload(
    config: GymConformanceConfig,
    manifest: BackendManifest | None,
    payload: Mapping[str, object] | None,
) -> Mapping[str, object]:
    """Resolve an explicit payload or serialize a manifest."""

    if payload is not None:
        return payload
    return cast(
        Mapping[str, object],
        backend_manifest_payload(manifest or config.create_manifest()),
    )


def _passed_refs(
    config: GymConformanceConfig,
    conformance_report: BackendConformanceReport | None,
    source_diagnostics: Iterable[Diagnostic],
) -> tuple[str, ...]:
    """Resolve passed-probe evidence refs under the backend's identities."""

    return passed_probe_evidence_refs(
        conformance_report,
        source_diagnostics,
        backend_conformance_evidence=config.backend_evidence,
        source_protocol_evidence=config.source_evidence,
        source_validation_failed_code=config.source_validation_failed,
    )


__all__ = [
    "GymConformanceConfig",
    "capability_evidence",
    "capability_evidence_gaps",
    "conformance_payload",
    "declared_weaknesses",
    "run_conformance",
    "source_protocol_diagnostics",
    "standard_probe_requirements",
]
