"""Evidence-bounded NASim backend manifest.

The manifest declares only the RAES surfaces the adapter actually implements
for the admitted ``tiny`` static benchmark. The native environment is fully
observed (``fully_obs=True``); the portable participant boundary is deliberately
narrower, so the raw observation vector, host state, action availability, and
evaluator-only goal truth are disclosed as withheld rather than advertised.
"""

from __future__ import annotations

from raes_backend_protocols.backend_manifest import (  # type: ignore[import-untyped]
    BackendManifest,
)
from raes_backend_protocols.capabilities import (  # type: ignore[import-untyped]
    CLEANUP_CAPABILITY_REQUIRED_CONTRACTS,
    BackendCapabilitySet,
    CleanupCapabilities,
    EvaluatorCapabilities,
    OrchestratorCapabilities,
    ParticipantRuntimeCapabilities,
    ProvisionerCapabilities,
    WorkflowFeature,
)
from raes_contracts.apparatus import (  # type: ignore[import-untyped]
    RealizationSupportDeclaration,
)
from raes_contracts.vocabulary import (  # type: ignore[import-untyped]
    RealizationSupportMode,
)

from raes_adapters._manifest_support import (
    assemble_manifest,
    declared_cleanup_capabilities,
    read_source_revision,
)
from raes_adapters.nasim import load_qualification

NASIM_BACKEND_NAME = "nasim-tiny"


def _provisioner_capabilities() -> ProvisionerCapabilities:
    """Declare selected static-benchmark provisioning support."""

    return ProvisionerCapabilities(
        name="nasim-provisioner",
        supported_node_types=frozenset({"switch", "vm"}),
        supported_os_families=frozenset({"linux"}),
        supported_content_types=frozenset(),
        supported_account_features=frozenset({"groups"}),
        supported_domain_profiles=frozenset(),
        supported_service_materialization_profiles=frozenset(),
        max_total_nodes=6,
        supports_accounts=True,
        constraints={
            "topology_realization": (
                "selected static tiny benchmark; the authored three-host topology is "
                "realized node-for-node with no generator abstraction"
            ),
            "account_realization": (
                "authored account intent is portable scenario truth; no native "
                "credential or access-level equivalence is claimed"
            ),
        },
    )


def _participant_capabilities() -> ParticipantRuntimeCapabilities:
    """Declare the bounded single red-participant runtime support."""

    return ParticipantRuntimeCapabilities(
        name="nasim-participant-runtime",
        supported_participant_roles=frozenset({"red"}),
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
            }
        ),
        supported_interaction_features=frozenset({"shared_state_change"}),
        supports_autonomous_execution=False,
        supports_bounded_concurrency=False,
        constraints={
            "max_in_flight_native_transitions": "1",
            "native_action_coordinates": "driver-private",
            "interaction_scope": (
                "the single red participant mutates shared network state; the "
                "selected tiny scenario has no defender or second participant, so no "
                "contention, coordination, or interference is claimed"
            ),
            "native_observation": (
                "the native environment is fully observed; the portable participant "
                "view is a lossy default-deny projection that withholds the flat "
                "observation vector, action index, host state, and info"
            ),
            "native_target_attribution": (
                "unavailable; a requested target stays intent and is not echoed as a "
                "realized effect target without a verified source join"
            ),
            "participant_action_scope": (
                "service-exploit, privilege-escalation, service-discovery, and "
                "subnet-discovery attacker contracts"
            ),
        },
    )


def _orchestrator_capabilities() -> OrchestratorCapabilities:
    """Declare the NASim orchestration surface."""

    return OrchestratorCapabilities(
        name="nasim-orchestrator",
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
    """Declare the NASim evaluator surface."""

    return EvaluatorCapabilities(
        name="nasim-evaluator",
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
            "goal_truth": (
                "goal attainment is evaluator-only truth, separate from reward and "
                "from the participant observation boundary"
            ),
            "objective_terminal_state": (
                "running until a distinct mapped terminal cause is available"
            ),
        },
    )


def _cleanup_capabilities() -> CleanupCapabilities:
    """Declare the NASim cleanup surface."""

    return declared_cleanup_capabilities(
        name="nasim-cleanup",
        supported_contract_versions=CLEANUP_CAPABILITY_REQUIRED_CONTRACTS,
        supported_action_kinds=frozenset({"destroy", "reset", "verify"}),
        supported_verification_methods=frozenset({"probe", "receipt"}),
        supports_reusable_state=True,
        supports_residual_state_disclosure=True,
    )


def _capabilities() -> BackendCapabilitySet:
    """Compose the complete selected backend capability declaration."""

    return BackendCapabilitySet(
        provisioner=_provisioner_capabilities(),
        orchestrator=_orchestrator_capabilities(),
        evaluator=_evaluator_capabilities(),
        participant_runtime=_participant_capabilities(),
        cleanup=_cleanup_capabilities(),
    )


def _realization_support(source_revision: str) -> tuple[RealizationSupportDeclaration, ...]:
    """Declare the selected static-scenario realization and its disclosures."""

    return (
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
                "source_profile": f"nasim-tiny-static-benchmark-{source_revision[:7]}",
                "topology": (
                    "authored three-host topology realizes the static tiny benchmark node-for-node"
                ),
                "observation": (
                    "native fully observed; portable participant view is a narrower "
                    "lossy default-deny projection"
                ),
            },
        ),
    )


def create_nasim_manifest() -> BackendManifest:
    """Return the manifest for the admitted selected NASim profile."""

    source_revision = read_source_revision(load_qualification)
    return assemble_manifest(
        NASIM_BACKEND_NAME,
        _capabilities(),
        _realization_support(source_revision),
        {
            "source_identity": "qualified-complete-runtime-artifact-roots-attested",
            "protocol_configuration": "attested",
            "execution_controls": "partial",
            "run_evidence": "attestable",
            "outcome_reproduction": "stochastic-bounded",
            "dependency_installation": "index-published-pinned-runtime",
            "native_observability": "fully-observed-source-narrowed-to-lossy-participant-view",
        },
    )


__all__ = [
    "NASIM_BACKEND_NAME",
    "create_nasim_manifest",
]
