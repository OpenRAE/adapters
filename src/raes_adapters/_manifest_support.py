"""Backend-neutral manifest helpers over published RAES capability models.

Every backend derives its adapter version, resolves published model contract
identities, and composes its supported-contract set from RAES-owned profiles
and its own declared capabilities the same way. This module is the single shared
implementation of those mechanics; the capability values themselves stay
backend-local. RAES continues to own the profiles, capability models, and
contract catalogue.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version

from raes_backend_protocols.backend_manifest import (  # type: ignore[import-untyped]
    BackendManifest,
)
from raes_backend_protocols.capabilities import (  # type: ignore[import-untyped]
    CLEANUP_CAPABILITY_REQUIRED_CONTRACTS,
    PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS,
    BackendCapabilitySet,
)
from raes_contracts.apparatus import (  # type: ignore[import-untyped]
    ConceptBinding,
    RealizationSupportDeclaration,
)
from raes_contracts.backend_profiles import (  # type: ignore[import-untyped]
    load_backend_profile,
)
from raes_contracts.contracts import (  # type: ignore[import-untyped]
    ExperimentCaptureSpecModel,
    ExperimentDerivedMeasureModel,
    ExperimentEvidenceRecordModel,
    PropositionTruthResultModel,
)
from raes_contracts.contracts.base import (  # type: ignore[import-untyped]
    ContractModel,
)

_EXPERIMENT_MODELS = (
    PropositionTruthResultModel,
    ExperimentCaptureSpecModel,
    ExperimentEvidenceRecordModel,
    ExperimentDerivedMeasureModel,
)


def adapter_version() -> str:
    """Return the installed adapter version or a local-development marker."""

    try:
        return distribution_version("raes-adapters")
    except PackageNotFoundError:
        return "0.0.0+unknown"


def model_contract_id(model: type[ContractModel]) -> str:
    """Resolve a published RAES model's contract identity."""

    schema_version = model.model_fields["schema_version"].default
    if not isinstance(schema_version, str):
        schema_property = model.model_json_schema()["properties"]["schema_version"]
        schema_version = schema_property.get("const")
    if not isinstance(schema_version, str):
        raise RuntimeError("published RAES contract model has no schema identity")
    return schema_version.replace("/", "-")


def supported_contracts(capabilities: BackendCapabilitySet) -> frozenset[str]:
    """Compose a declaration from RAES-owned profiles and model identities."""

    supported = set(load_backend_profile("full-remote-control-plane").required_contracts)
    supported.update(CLEANUP_CAPABILITY_REQUIRED_CONTRACTS)
    participant = capabilities.participant_runtime
    if participant is not None:
        declared_terms = (
            participant.supported_participant_roles
            | participant.supported_behavior_features
            | participant.supported_interaction_features
        )
        for required_by_term in PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS.values():
            for term in declared_terms:
                supported.update(required_by_term.get(term, ()))
    supported.update(model_contract_id(model) for model in _EXPERIMENT_MODELS)
    return frozenset(supported)


def concept_bindings() -> tuple[ConceptBinding, ...]:
    """Bind the declared capability scopes to RAES-owned concept families.

    The scope paths and target families are the same for any backend that
    declares the standard provisioner/orchestrator/evaluator/participant
    capability surfaces; only the values a backend fills into those scopes
    differ.
    """

    return (
        ConceptBinding(scope="capabilities.provisioner.supported_node_types", family="assets"),
        ConceptBinding(scope="capabilities.provisioner.supported_os_families", family="assets"),
        ConceptBinding(
            scope="capabilities.provisioner.supported_content_types",
            family="tools-and-artifacts",
        ),
        ConceptBinding(
            scope="capabilities.provisioner.supported_account_features",
            family="identities",
        ),
        ConceptBinding(
            scope="capabilities.provisioner.supported_domain_profiles",
            family="identities",
        ),
        ConceptBinding(
            scope="capabilities.provisioner.supported_service_materialization_profiles",
            family="tools-and-artifacts",
        ),
        ConceptBinding(
            scope="capabilities.orchestrator.supported_sections",
            family="actions-and-events",
        ),
        ConceptBinding(scope="capabilities.evaluator.supported_sections", family="observables"),
        ConceptBinding(
            scope="capabilities.participant_runtime.supported_participant_roles",
            family="identities",
        ),
        ConceptBinding(
            scope="capabilities.participant_runtime.supported_behavior_features",
            family="actions-and-events",
        ),
        ConceptBinding(
            scope="capabilities.participant_runtime.supported_interaction_features",
            family="relationships",
        ),
    )


def read_source_revision(load_qualification: Callable[[], Mapping[str, object]]) -> str:
    """Read the selected source revision from a backend qualification record."""

    qualification = load_qualification()
    source = qualification.get("source")
    revision = source.get("commit") if isinstance(source, dict) else None
    if not isinstance(revision, str):
        raise RuntimeError("selected simulator qualification is invalid")
    return revision


def assemble_manifest(
    name: str,
    capabilities: BackendCapabilitySet,
    realization_support: tuple[RealizationSupportDeclaration, ...],
    constraints: Mapping[str, str],
) -> BackendManifest:
    """Assemble the published manifest from a backend's declared surfaces."""

    return BackendManifest(
        name=name,
        version=adapter_version(),
        supported_contract_versions=supported_contracts(capabilities),
        compatible_processors=frozenset({"raes-reference-processor"}),
        concept_bindings=concept_bindings(),
        realization_support=realization_support,
        constraints=dict(constraints),
        capabilities=capabilities,
    )


__all__ = [
    "adapter_version",
    "assemble_manifest",
    "concept_bindings",
    "model_contract_id",
    "read_source_revision",
    "supported_contracts",
]
