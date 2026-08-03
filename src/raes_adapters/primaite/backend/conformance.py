"""PrimAITE conformance composition over published RAES report shapes."""

from __future__ import annotations

from collections.abc import Mapping
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

from raes_adapters._conformance_support import affirmative_capability_pointers
from raes_adapters.base import run_conformance_probe
from raes_adapters.primaite import load_qualification
from raes_adapters.primaite.scenario_ledger import (
    DATA_MANIPULATION,
    EvidenceSelection,
    load_loss_disclosures,
    validate_all,
)

from ._diagnostics import diagnostic_address
from .driver import PrimaiteDriverProtocol
from .manifest import create_primaite_manifest
from .target import create_primaite_target


def run_primaite_conformance(
    *,
    driver: PrimaiteDriverProtocol | None = None,
    seed: int | None = None,
) -> BackendConformanceReport:
    """Run the published RAES target conformance probe for PrimAITE."""

    return run_conformance_probe(create_primaite_target(driver=driver, seed=seed))


def primaite_backend_conformance_payload(
    report: BackendConformanceReport,
) -> dict[str, object]:
    """Serialize the canonical report through the published RAES projector."""

    return cast(dict[str, object], backend_conformance_report_payload(report))


def primaite_manifest_capability_evidence(
    manifest: BackendManifest | None = None,
    *,
    payload: Mapping[str, object] | None = None,
) -> dict[str, tuple[str, ...]]:
    """Return production capability evidence for the backend — deliberately none.

    No affirmative runtime capability is production-evidenced. The live
    ``PrimaiteDriver`` fails closed (it cannot execute in-process), so any passing
    target-conformance report necessarily came from an injected test double, and a
    fake driver cannot upgrade a live-runtime claim. Every declared capability is
    therefore reported as an open gap by
    :func:`primaite_manifest_capability_evidence_gaps` rather than certified here.
    """

    return {}


def primaite_manifest_capability_evidence_gaps(
    manifest: BackendManifest | None = None,
    *,
    payload: Mapping[str, object] | None = None,
) -> tuple[str, ...]:
    """Return every declared affirmative capability as an unevidenced gap.

    Because the production live target is not executable, no affirmative runtime
    capability has executable production evidence; each is disclosed as a gap until
    a qualified, isolated live driver can earn that evidence through the public
    path.
    """

    resolved = (
        payload
        if payload is not None
        else cast(
            Mapping[str, object],
            backend_manifest_payload(manifest or create_primaite_manifest()),
        )
    )
    return affirmative_capability_pointers(resolved)


def primaite_declared_weaknesses(
    selection: EvidenceSelection = DATA_MANIPULATION,
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


def primaite_source_protocol_diagnostics(
    selection: EvidenceSelection = DATA_MANIPULATION,
) -> tuple[Diagnostic, ...]:
    """Validate source-protocol evidence and emit RAES diagnostics."""

    diagnostics: list[Diagnostic] = []
    problems = validate_all(selection)
    if problems:
        diagnostics.extend(
            Diagnostic(
                code="primaite.source-protocol.validation-failed",
                domain="conformance",
                address=diagnostic_address(
                    f"primaite.source-protocol.{problem.row_id}.{problem.field}"
                ),
                message="The selected PrimAITE source-protocol evidence failed validation.",
            )
            for problem in problems
        )
    else:
        diagnostics.append(
            Diagnostic(
                code="primaite.source-protocol.validated",
                domain="conformance",
                address="/primaite/source-protocol",
                message="The selected PrimAITE source-protocol evidence validated.",
                severity=Severity.INFO,
            )
        )
    diagnostics.extend(
        Diagnostic(
            code="primaite.source-protocol.declared-weakness",
            domain="conformance",
            address=f"/primaite/source-protocol/weaknesses/{index}",
            message="A declared PrimAITE source-protocol weakness remains in force.",
            severity=Severity.WARNING,
        )
        for index, _weakness in enumerate(primaite_declared_weaknesses(selection))
    )
    return tuple(diagnostics)


__all__ = [
    "primaite_backend_conformance_payload",
    "primaite_declared_weaknesses",
    "primaite_manifest_capability_evidence",
    "primaite_manifest_capability_evidence_gaps",
    "primaite_source_protocol_diagnostics",
    "run_primaite_conformance",
]
