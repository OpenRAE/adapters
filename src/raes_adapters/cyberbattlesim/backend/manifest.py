"""Evidence-bounded CyberBattleSim backend manifest."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version

from raes_backend_protocols.backend_manifest import (  # type: ignore[import-untyped]
    BackendManifest,
)
from raes_backend_protocols.capabilities import (  # type: ignore[import-untyped]  # type: ignore[import-untyped]
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
from raes_contracts.vocabulary import (  # type: ignore[import-untyped]
    ParticipantFeatureSupportLevel,
    RealizationSupportMode,
)

from raes_adapters.cyberbattlesim import load_qualification

CYBERBATTLESIM_BACKEND_NAME = "cyberbattlesim"


def _adapter_version() -> str:
    """Return the installed adapter version or a local-development marker."""

    try:
        return distribution_version("raes-adapters")
    except PackageNotFoundError:
        return "0.0.0+unknown"


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


def _provisioner_capabilities() -> ProvisionerCapabilities:
    """Declare selected generated-chain provisioning support."""

    return ProvisionerCapabilities(
        name="cyberbattlesim-provisioner",
        supported_node_types=frozenset({"switch", "vm"}),
        supported_os_families=frozenset({"linux", "windows"}),
        supported_content_types=frozenset(),
        supported_account_features=frozenset({"groups", "auth_method"}),
        supported_domain_profiles=frozenset(),
        supported_service_materialization_profiles=frozenset(),
        max_total_nodes=10,
        supports_accounts=True,
        constraints={
            "topology_realization": (
                "selected generated chain; authored topology is representative"
            ),
            "account_realization": (
                "auth method and group intent map to source-generated credentials; "
                "no source identity equivalence"
            ),
        },
    )


def _orchestrator_capabilities() -> OrchestratorCapabilities:
    """Declare portable episode-orchestration support."""

    return OrchestratorCapabilities(
        name="cyberbattlesim-orchestrator",
        supported_sections=frozenset({"events", "workflows"}),
        supports_workflows=True,
        supports_assertion_refs=False,
        supports_inject_bindings=False,
        supported_workflow_features=frozenset({WorkflowFeature.CALL}),
        constraints={
            "native_transition_owner": "participant-runtime",
            "workflow_scope": "episode lifecycle and serialized participant steps",
        },
    )


def _evaluator_capabilities() -> EvaluatorCapabilities:
    """Declare evaluator-owned stochastic result projection support."""

    return EvaluatorCapabilities(
        name="cyberbattlesim-evaluator",
        supported_sections=frozenset({"conditions", "propositions", "assertions", "objectives"}),
        supports_scoring=True,
        supports_objectives=True,
        supported_predicate_families=frozenset({"presence", "boolean", "string", "number"}),
        supported_quantifiers=frozenset({"all", "any", "at_least"}),
        supported_truth_outcomes=frozenset({"true", "false", "unknown", "unsupported"}),
        supported_evidence_channels=frozenset({"api_response"}),
        supported_time_domains=frozenset({"wall_clock"}),
        preserves_binding_provenance=True,
        constraints={
            "reward_owner": "evaluator",
            "outcome_reproduction": "stochastic-bounded",
            "proposition_projection": "binding-preserving unknown under lossy source evidence",
            "objective_terminal_state": (
                "running until a distinct mapped terminal cause is available"
            ),
        },
    )


def _participant_capabilities() -> ParticipantRuntimeCapabilities:
    """Declare bounded red-participant runtime support."""

    return ParticipantRuntimeCapabilities(
        name="cyberbattlesim-participant-runtime",
        supported_participant_roles=frozenset({"red"}),
        supported_behavior_features=frozenset(
            {
                "action_contracts",
                "attribution_support",
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
                feature="interference",
                support_level=ParticipantFeatureSupportLevel.DISCLOSED_WEAK,
                limitation_refs=("limitation:cyberbattlesim:source-internal-defender",),
                disclosure_refs=("docs/decisions/cyberbattlesim-backend-guardrails.md",),
            ),
        ),
        supports_autonomous_execution=False,
        supports_bounded_concurrency=False,
        constraints={
            "max_in_flight_native_transitions": "1",
            "native_action_coordinates": "driver-private",
            "native_target_attribution": (
                "unavailable; request targets remain intent and are not echoed "
                "as realized effect targets"
            ),
            "participant_action_scope": (
                "connect, local-vulnerability, and remote-vulnerability attacker contracts"
            ),
            "source_internal_defender": (
                "scan-and-reimage executes inside the selected source step "
                "and is not a participant-admitted action"
            ),
        },
    )


def _capabilities() -> BackendCapabilitySet:
    """Compose the complete selected backend capability declaration."""

    return BackendCapabilitySet(
        provisioner=_provisioner_capabilities(),
        orchestrator=_orchestrator_capabilities(),
        evaluator=_evaluator_capabilities(),
        participant_runtime=_participant_capabilities(),
        cleanup=CleanupCapabilities(
            name="cyberbattlesim-cleanup",
            supported_contract_versions=CLEANUP_CAPABILITY_REQUIRED_CONTRACTS,
            supported_action_kinds=frozenset({"destroy", "reset", "verify"}),
            supported_verification_methods=frozenset({"probe", "receipt"}),
            supports_reusable_state=True,
            supports_residual_state_disclosure=True,
        ),
    )


def create_cyberbattlesim_manifest() -> BackendManifest:
    """Return the manifest for the admitted selected source profile."""

    qualification = load_qualification()
    source = qualification.get("source")
    source_revision = source.get("commit") if isinstance(source, dict) else None
    if not isinstance(source_revision, str):
        raise RuntimeError("selected simulator qualification is invalid")
    capabilities = _capabilities()
    return BackendManifest(
        name=CYBERBATTLESIM_BACKEND_NAME,
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
                        "account-feature",
                        "workflow-feature",
                        "workflow-state-predicate",
                    }
                ),
                supported_exact_requirement_kinds=frozenset({"declared-capability-match"}),
                disclosure_kinds=frozenset(
                    {
                        "backend-manifest-v2",
                        "runtime-snapshot-v1",
                        "operation-status-v1",
                    }
                ),
                constraints={
                    "source_profile": f"cyberbattlesim-chain-public-{source_revision[:7]}",
                    "topology": "representative authored topology maps to generated size-10 chain",
                },
            ),
        ),
        constraints={
            "source_identity": "qualified-complete-runtime-artifact-roots-attested",
            "protocol_configuration": "attested",
            "execution_controls": "partial",
            "run_evidence": "attestable",
            "outcome_reproduction": "stochastic-bounded",
            "dependency_installation": "separately-installed-pinned-source",
        },
        capabilities=capabilities,
    )


__all__ = [
    "CYBERBATTLESIM_BACKEND_NAME",
    "create_cyberbattlesim_manifest",
]
