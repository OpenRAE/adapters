"""Neutral gym-backend conformance composition over published RAES reports."""

from __future__ import annotations

from collections.abc import Callable, Mapping
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
    manifest_capability_gaps,
)
from raes_adapters._scenario_ledger import EvidenceSelection, LedgerProblem
from raes_adapters.base import run_conformance_probe


@dataclass(frozen=True)
class GymConformanceConfig(object):
    """Backend-local identities and bindings for conformance composition."""

    name: str
    source_validation_failed: str
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


def capability_gaps(
    config: GymConformanceConfig,
    manifest: BackendManifest | None,
    payload: Mapping[str, object] | None,
) -> tuple[str, ...]:
    """Return every affirmative manifest leaf as unresolved inventory."""

    return manifest_capability_gaps(_manifest_payload(config, manifest, payload))


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


__all__ = [
    "GymConformanceConfig",
    "capability_gaps",
    "conformance_payload",
    "declared_weaknesses",
    "run_conformance",
    "source_protocol_diagnostics",
]
