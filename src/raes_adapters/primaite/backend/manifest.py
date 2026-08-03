"""Evidence-bounded PrimAITE backend manifest and realization envelope."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version
from typing import Any

from raes_backend_protocols.backend_manifest import (  # type: ignore[import-untyped]
    BackendManifest,
)
from raes_backend_protocols.capabilities import (  # type: ignore[import-untyped]
    CLEANUP_CAPABILITY_REQUIRED_CONTRACTS,
    PARTICIPANT_RUNTIME_CAPABILITY_REQUIRED_CONTRACTS,
    BackendCapabilitySet,
    CleanupCapabilities,
    EvaluatorCapabilities,
    OrchestratorCapabilities,
    ParticipantFeatureSupport,
    ParticipantRuntimeCapabilities,
    ProvisionerCapabilities,
    WorkflowFeature,
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
from raes_contracts.realization_envelope import (  # type: ignore[import-untyped]
    BackendRealizationEnvelopeModel,
    realization_envelope_digest,
    realizer_configuration_digest,
    validate_backend_realization_envelope,
)
from raes_contracts.vocabulary import (  # type: ignore[import-untyped]
    ParticipantFeatureSupportLevel,
    RealizationSupportMode,
)

from raes_adapters.primaite import load_qualification

PRIMAITE_BACKEND_NAME = "primaite"
_GUARDRAILS_DISCLOSURE = "docs/decisions/primaite-backend-guardrails.md"


def _adapter_version() -> str:
    """Return the installed adapter version or a local-development marker."""

    try:
        return distribution_version("raes-adapters")
    except PackageNotFoundError:
        return "0.0.0+unknown"


def _source_revision() -> str:
    """Return the selected PrimAITE source commit."""

    source = load_qualification().get("source")
    revision = source.get("commit") if isinstance(source, dict) else None
    if not isinstance(revision, str):
        raise RuntimeError("selected simulator qualification is invalid")
    return revision


def _model_contract_id(model: type[ContractModel]) -> str:
    """Resolve a published RAES model's contract identity."""

    schema_version = model.model_fields["schema_version"].default
    if not isinstance(schema_version, str):
        schema_property = model.model_json_schema()["properties"]["schema_version"]
        schema_version = schema_property.get("const")
    if not isinstance(schema_version, str):
        raise RuntimeError("published RAES contract model has no schema identity")
    return schema_version.replace("/", "-")


def _supported_contracts(capabilities: BackendCapabilitySet) -> frozenset[str]:
    """Compose this declaration from RAES-owned profiles and model identities."""

    supported = set(load_backend_profile("full-remote-control-plane").required_contracts)
    supported.update(CLEANUP_CAPABILITY_REQUIRED_CONTRACTS)
    supported.add("realization-envelope-v1")
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
    supported.update(
        _model_contract_id(model)
        for model in (
            PropositionTruthResultModel,
            ExperimentCaptureSpecModel,
            ExperimentEvidenceRecordModel,
            ExperimentDerivedMeasureModel,
        )
    )
    return frozenset(supported)


def create_primaite_realization_envelope() -> BackendRealizationEnvelopeModel:
    """Return the validated disclosure for the selected fixed-source realization.

    PrimAITE does not project arbitrary SDL into a generated topology: the native
    scenario is the fixed, pinned ``data_manipulation`` case, and the portable
    model only describes it. Every concrete network control, the native action
    interface, and stochastic control are disclosed as lossy or unsupported here.
    """

    revision = _source_revision()[:7]
    configuration: dict[str, Any] = {
        "mode": "selected-fixed-source-scenario",
        "architecture": "linux",
        "image_policy": f"primaite-data-manipulation:{revision}:fixed-package-data",
        "network_policy": (
            "primaite-data-manipulation-fixed-addressing;seed=descriptive-only-broken-light-route"
        ),
        "supported_node_types": ["switch", "vm"],
        "supported_os_families": ["linux"],
        "supported_content_types": [],
        "supported_account_features": [],
        "supported_domain_profiles": [],
        "supports_acls": False,
        "memory_mib": {"minimum": 1, "maximum": None},
        "vcpus": {"minimum": 1, "maximum": None},
    }
    configuration["configuration_digest"] = realizer_configuration_digest(configuration)
    unsupported: dict[str, Any] = {
        "disposition": "unsupported",
        "observation_strength": "none",
        "mechanism": None,
        "transformations": [],
    }
    descriptor: dict[str, Any] = {
        "disposition": "descriptor-only",
        "observation_strength": "driver-reported",
        "mechanism": "selected-primaite-data-manipulation",
        "transformations": [],
    }
    payload: dict[str, Any] = {
        "schema_version": "realization-envelope/v1",
        "contract_id": "realization-envelope-v1",
        "id": "primaite.data-manipulation.v1",
        "expression": {
            "schema_version": "realization-envelope/v1",
            "id": "primaite.data-manipulation.expression.v1",
            "scope": "scenario",
            "domains": {},
            "bindings": [],
            "closure": [],
        },
        "configuration": configuration,
        "concerns": [
            {"concern": "topology", **descriptor},
            {"concern": "architecture", **descriptor},
            {"concern": "image", **unsupported},
            {"concern": "resource-allocation", **unsupported},
            {"concern": "network", **descriptor},
            {"concern": "content-placement", **unsupported},
            {"concern": "account-placement", **unsupported},
            {"concern": "feature-binding", **unsupported},
            {"concern": "service", **descriptor},
            {"concern": "acl", **descriptor},
        ],
    }
    payload["digest"] = realization_envelope_digest(payload)
    return validate_backend_realization_envelope(payload)


def _concept_bindings() -> tuple[ConceptBinding, ...]:
    """Bind declared capability scopes to RAES-owned concept families."""

    return (
        ConceptBinding(
            scope="capabilities.provisioner.supported_node_types",
            family="assets",
        ),
        ConceptBinding(
            scope="capabilities.provisioner.supported_os_families",
            family="assets",
        ),
        ConceptBinding(
            scope="capabilities.orchestrator.supported_sections",
            family="actions-and-events",
        ),
        ConceptBinding(
            scope="capabilities.evaluator.supported_sections",
            family="observables",
        ),
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


def _provisioner_capabilities(
    envelope: BackendRealizationEnvelopeModel,
) -> ProvisionerCapabilities:
    """Derive provisioning capabilities from the validated realization envelope."""

    configuration = envelope.configuration
    return ProvisionerCapabilities(
        name="primaite-provisioner",
        supported_node_types=frozenset(configuration.supported_node_types),
        supported_os_families=frozenset(configuration.supported_os_families),
        supported_content_types=frozenset(configuration.supported_content_types),
        supported_account_features=frozenset(configuration.supported_account_features),
        supported_domain_profiles=frozenset(configuration.supported_domain_profiles),
        supported_service_materialization_profiles=frozenset(),
        max_total_nodes=10,
        supports_acls=configuration.supports_acls,
        supports_accounts=bool(configuration.supported_account_features),
        constraints={
            "scenario_realization": (
                "The fixed selected PrimAITE data_manipulation scenario is realized; "
                "authored SDL topology is a representative portable description, not a "
                "generated native construction."
            ),
        },
    )


def _orchestrator_capabilities() -> OrchestratorCapabilities:
    """Declare portable episode-orchestration support."""

    return OrchestratorCapabilities(
        name="primaite-orchestrator",
        supported_sections=frozenset({"events", "workflows"}),
        supports_workflows=True,
        supports_assertion_refs=False,
        supports_inject_bindings=False,
        supported_workflow_features=frozenset({WorkflowFeature.CALL}),
        constraints={
            "native_transition_owner": "participant-runtime",
            "workflow_scope": "episode lifecycle only; the orchestrator never advances the source",
        },
    )


def _evaluator_capabilities() -> EvaluatorCapabilities:
    """Declare evaluator-owned proposition projection support.

    Scoring is **not** declared for this selection: the source BLUE reward blends
    unqualified components whose source-member evidence closure is incomplete, so
    the evaluator never promotes the reward into a score or derived measure. It
    still admits objectives, but ``terminated`` is hard-coded false so no source
    terminal supports an objective outcome, and every proposition stays unknown
    under lossy evidence; the reward is withheld as a limitation.
    """

    return EvaluatorCapabilities(
        name="primaite-evaluator",
        supported_sections=frozenset({"conditions", "propositions", "assertions", "objectives"}),
        supports_scoring=False,
        supports_objectives=True,
        supported_predicate_families=frozenset({"presence", "boolean", "string", "number"}),
        supported_quantifiers=frozenset({"all", "any", "at_least"}),
        supported_truth_outcomes=frozenset({"true", "false", "unknown", "unsupported"}),
        supported_evidence_channels=frozenset({"api_response"}),
        supported_time_domains=frozenset({"wall_clock"}),
        preserves_binding_provenance=True,
        constraints={
            "outcome_reproduction": "stochastic-bounded",
            "proposition_projection": "unknown under lossy source evidence; no source terminal",
            "reward_projection": (
                "withheld: the source reward's member evidence closure is incomplete, so no "
                "score or derived measure is projected for this selection"
            ),
        },
    )


def _participant_capabilities() -> ParticipantRuntimeCapabilities:
    """Declare bounded blue-participant runtime support.

    The BLUE role is declared, but the broad portable action contracts have no
    qualified single-operation native mapping, so ``action_contracts`` is a
    disclosed-weak feature: an admitted action is modelled and then rejected as
    unrepresentable rather than silently selecting a native operation.
    """

    return ParticipantRuntimeCapabilities(
        name="primaite-participant-runtime",
        supported_participant_roles=frozenset({"blue"}),
        supported_behavior_features=frozenset(
            {
                "action_contracts",
                "behavior_history",
                "effects",
                "failure_classes",
                "observation_boundaries",
                "outcome_interpretation",
                "preconditions",
                "state_transitions",
                "temporal_contracts",
            }
        ),
        supported_interaction_features=frozenset({"interference"}),
        feature_support=(
            ParticipantFeatureSupport(
                feature="action_contracts",
                support_level=ParticipantFeatureSupportLevel.DISCLOSED_WEAK,
                limitation_refs=("limitation:primaite:unrepresentable-action-contracts",),
                disclosure_refs=(_GUARDRAILS_DISCLOSURE,),
            ),
            ParticipantFeatureSupport(
                feature="interference",
                support_level=ParticipantFeatureSupportLevel.DISCLOSED_WEAK,
                limitation_refs=("limitation:primaite:source-internal-red-green",),
                disclosure_refs=(_GUARDRAILS_DISCLOSURE,),
            ),
        ),
        supports_autonomous_execution=False,
        supports_bounded_concurrency=False,
        constraints={
            "max_in_flight_native_transitions": "1",
            "native_action_coordinates": "driver-private",
            "action_representability": (
                "no portable BLUE action contract maps to exactly one qualified native "
                "Discrete(78) operation; admitted actions are rejected before source mutation"
            ),
            "source_internal_participants": (
                "the scripted RED and probabilistic GREEN participants act inside the "
                "aggregate source turn and are not participant-admitted actions"
            ),
        },
    )


def _capabilities() -> BackendCapabilitySet:
    """Compose the complete selected backend capability declaration."""

    envelope = create_primaite_realization_envelope()
    return BackendCapabilitySet(
        provisioner=_provisioner_capabilities(envelope),
        orchestrator=_orchestrator_capabilities(),
        evaluator=_evaluator_capabilities(),
        participant_runtime=_participant_capabilities(),
        cleanup=CleanupCapabilities(
            name="primaite-cleanup",
            supported_contract_versions=CLEANUP_CAPABILITY_REQUIRED_CONTRACTS,
            supported_action_kinds=frozenset({"destroy", "reset", "verify"}),
            supported_verification_methods=frozenset({"probe", "receipt"}),
            supports_reusable_state=True,
            supports_residual_state_disclosure=True,
        ),
    )


def create_primaite_manifest() -> BackendManifest:
    """Return the manifest for the admitted selected source profile."""

    revision = _source_revision()
    envelope = create_primaite_realization_envelope()
    capabilities = _capabilities()
    return BackendManifest(
        name=PRIMAITE_BACKEND_NAME,
        version=_adapter_version(),
        supported_contract_versions=_supported_contracts(capabilities),
        compatible_processors=frozenset({"raes-reference-processor"}),
        concept_bindings=_concept_bindings(),
        realization_support=(
            RealizationSupportDeclaration(
                domain="runtime-realization",
                support_mode=RealizationSupportMode.CONSTRAINED,
                supported_constraint_kinds=frozenset(
                    {
                        "node-type",
                        "os-family",
                        "workflow-feature",
                        "workflow-state-predicate",
                    }
                ),
                supported_exact_requirement_kinds=frozenset({"declared-capability-match"}),
                disclosure_kinds=frozenset(
                    {
                        "backend-manifest-v2",
                        "realization-envelope-v1",
                        "runtime-snapshot-v1",
                        "operation-status-v1",
                    }
                ),
                constraints={
                    "source_profile": f"primaite-data-manipulation-{revision[:7]}",
                    "topology": "fixed selected data_manipulation scenario; SDL is representative",
                },
            ),
        ),
        constraints={
            "source_identity": "qualified-complete-runtime-artifact-root-attested",
            "protocol_configuration": "attested",
            "execution_controls": "partial",
            "run_evidence": "attestable",
            "outcome_reproduction": "stochastic-bounded",
            "dependency_installation": "separately-installed-pinned-source",
            "runtime_claim": "live source qualified on CPython 3.11 only",
            "action_representability": (
                "portable BLUE contracts have no qualified single-operation native mapping"
            ),
        },
        capabilities=capabilities,
        realization_envelope=envelope,
    )


__all__ = [
    "PRIMAITE_BACKEND_NAME",
    "create_primaite_manifest",
    "create_primaite_realization_envelope",
]
