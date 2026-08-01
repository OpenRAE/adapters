"""CyberBattleSim conformance composition over published RAES report shapes."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
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
    diagnostic_model,
)

from raes_adapters.base import run_conformance_probe
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
_NON_CAPABILITY_KEYS = frozenset({"constraints", "name"})


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

    return cast(dict[str, object], backend_conformance_report_payload(report))


def cyberbattlesim_manifest_capability_evidence(
    manifest: BackendManifest | None = None,
    *,
    payload: Mapping[str, object] | None = None,
    conformance_report: BackendConformanceReport | None = None,
    source_diagnostics: Iterable[Diagnostic] = (),
) -> dict[str, tuple[str, ...]]:
    """Return evidence references for declared affirmative manifest surfaces."""

    passed_evidence_refs = set(
        _passed_probe_evidence_refs(
            conformance_report,
            source_diagnostics,
        )
    )
    evidence: dict[str, tuple[str, ...]] = {}
    for pointer in _affirmative_capability_pointers(_manifest_payload(manifest, payload)):
        requirements = _CAPABILITY_PROBE_REQUIREMENTS.get(pointer)
        if requirements is not None and set(requirements) <= passed_evidence_refs:
            evidence[pointer] = requirements
    return evidence


def cyberbattlesim_manifest_capability_evidence_gaps(
    manifest: BackendManifest | None = None,
    *,
    payload: Mapping[str, object] | None = None,
    conformance_report: BackendConformanceReport | None = None,
    source_diagnostics: Iterable[Diagnostic] = (),
) -> tuple[str, ...]:
    """Return declared affirmative capability surfaces with no probe evidence."""

    evidence = cyberbattlesim_manifest_capability_evidence(
        manifest,
        payload=payload,
        conformance_report=conformance_report,
        source_diagnostics=source_diagnostics,
    )
    return tuple(
        pointer
        for pointer in _affirmative_capability_pointers(_manifest_payload(manifest, payload))
        if pointer not in evidence
    )


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


def _manifest_payload(
    manifest: BackendManifest | None,
    payload: Mapping[str, object] | None,
) -> Mapping[str, object]:
    """Resolve an explicit payload or serialize a manifest."""

    if payload is not None:
        return payload
    return cast(
        Mapping[str, object],
        backend_manifest_payload(manifest or create_cyberbattlesim_manifest()),
    )


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


def _affirmative_capability_pointers(payload: Mapping[str, object]) -> tuple[str, ...]:
    """Return JSON pointers for manifest capability values that declare support."""

    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, Mapping):
        return ()
    pointers: list[str] = []
    for name, value in sorted(capabilities.items(), key=lambda item: str(item[0])):
        if not _is_affirmative_capability_value(value):
            continue
        surface = f"/capabilities/{_escape_pointer_token(str(name))}"
        if isinstance(value, Mapping):
            nested = tuple(
                _iter_affirmative_capability_pointers(
                    cast(Mapping[object, object], value),
                    surface,
                )
            )
            pointers.extend(nested or (surface,))
        else:
            pointers.append(surface)
    return tuple(pointers)


def _iter_affirmative_capability_pointers(
    value: Mapping[object, object],
    base_pointer: str,
) -> Iterable[str]:
    """Yield nested affirmative capability pointers below a manifest surface."""

    for key, child in sorted(value.items(), key=lambda item: str(item[0])):
        if key in _NON_CAPABILITY_KEYS or not _is_affirmative_capability_value(child):
            continue
        pointer = f"{base_pointer}/{_escape_pointer_token(str(key))}"
        if isinstance(child, Mapping):
            nested = tuple(
                _iter_affirmative_capability_pointers(
                    cast(Mapping[object, object], child),
                    pointer,
                )
            )
            yield from nested or (pointer,)
        else:
            yield pointer


def _is_affirmative_capability_value(value: object) -> bool:
    """Return whether a manifest capability value makes an affirmative claim."""

    if value in (None, False):
        affirmative = False
    elif value is True:
        affirmative = True
    elif isinstance(value, str | int | float):
        affirmative = bool(value)
    elif isinstance(value, list | tuple | set | frozenset):
        affirmative = any(_is_affirmative_capability_value(item) for item in value)
    elif isinstance(value, Mapping):
        affirmative = any(
            _is_affirmative_capability_value(child)
            for key, child in cast(Mapping[object, object], value).items()
            if key not in _NON_CAPABILITY_KEYS
        )
    else:
        affirmative = False
    return affirmative


def _escape_pointer_token(token: str) -> str:
    """Escape one token for inclusion in a JSON Pointer."""

    return token.replace("~", "~0").replace("/", "~1")


__all__ = [
    "cyberbattlesim_backend_conformance_payload",
    "cyberbattlesim_declared_weaknesses",
    "cyberbattlesim_manifest_capability_evidence",
    "cyberbattlesim_manifest_capability_evidence_gaps",
    "cyberbattlesim_source_protocol_diagnostics",
    "run_cyberbattlesim_conformance",
]
