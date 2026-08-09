"""Evidence-bounded CyberBattleSim backend manifest."""

from __future__ import annotations

from raes_backend_protocols.backend_manifest import (  # type: ignore[import-untyped]
    BackendManifest,
)
from raes_backend_protocols.capabilities import (  # type: ignore[import-untyped]
    BackendCapabilitySet,
    ParticipantExecutionBinding,
    ParticipantFeatureSupport,
    ParticipantRuntimeCapabilities,
    ProvisionerCapabilities,
)
from raes_contracts.apparatus import (  # type: ignore[import-untyped]
    RealizationSupportDeclaration,
)
from raes_contracts.vocabulary import (  # type: ignore[import-untyped]
    ParticipantFeatureSupportLevel,
    RealizationSupportMode,
)

from raes_adapters._manifest_support import (
    assemble_manifest,
    read_source_revision,
    standard_cleanup_capabilities,
    standard_evaluator_capabilities,
    standard_orchestrator_capabilities,
)
from raes_adapters.cyberbattlesim import load_qualification

CYBERBATTLESIM_BACKEND_NAME = "cyberbattlesim"


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


def _participant_capabilities() -> ParticipantRuntimeCapabilities:
    """Declare bounded red-participant runtime support."""

    action_contracts = frozenset(
        {
            "participant.action-contract.connect",
            "participant.action-contract.local-vulnerability",
            "participant.action-contract.remote-vulnerability",
        }
    )
    target_addresses = frozenset(
        {
            "provision.node.customer-data",
            "provision.node.linux-relay",
            "provision.node.windows-relay",
        }
    )
    implementation_ref = "participant/cyberbattlesim-red-credential-cache.manifest.json"
    target_by_action = {
        "participant.action-contract.connect": "provision.node.customer-data",
        "participant.action-contract.local-vulnerability": "provision.node.linux-relay",
        "participant.action-contract.remote-vulnerability": "provision.node.windows-relay",
    }
    execution_bindings = tuple(
        ParticipantExecutionBinding(
            binding_id=f"cyberbattlesim-{action.rsplit('.', 1)[-1]}",
            action_contract_address=action,
            target_addresses=(target_by_action[action],),
            participant_implementation_ref=implementation_ref,
            constraint_refs=("constraint:serialized-native-transition",),
            evidence_refs=("source-ledger:credential-cache-exploiter",),
            max_action_attempts=1,
            max_in_flight=1,
            timeout_seconds=30,
            max_retries=0,
        )
        for action in sorted(action_contracts)
    )
    return ParticipantRuntimeCapabilities(
        name="cyberbattlesim-participant-runtime",
        supported_participant_roles=frozenset({"red"}),
        supported_behavior_features=frozenset(
            {
                "action_contracts",
                "autonomous_execution",
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
        supports_autonomous_execution=True,
        supported_autonomous_selection_strategies=frozenset({"ordered_cycle"}),
        supported_autonomous_action_contracts=action_contracts,
        supported_autonomous_observation_boundaries=frozenset(
            {"participant.observation-boundary.attacker-view"}
        ),
        supported_autonomous_target_addresses=target_addresses,
        supported_autonomous_policy_profiles=frozenset({"participant-autonomous-execution/v1"}),
        max_autonomous_participants=1,
        max_autonomous_action_attempts=1,
        max_autonomous_in_flight=1,
        max_autonomous_occurrences=10_000,
        max_autonomous_retries_per_occurrence=1,
        max_autonomous_burst_size=1,
        execution_bindings=execution_bindings,
        supports_execution_control=True,
        supported_execution_control_actions=frozenset(
            {"start", "pause", "resume", "drain", "reset", "teardown"}
        ),
        supports_bounded_concurrency=True,
        max_execution_services=1,
        max_concurrent_actions=2,
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
            "autonomous_policy": (
                "qualified CredentialCacheExploiter through RAES action admission"
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
        orchestrator=standard_orchestrator_capabilities(
            "cyberbattlesim",
            {
                "native_transition_owner": "participant-runtime",
                "workflow_scope": "episode lifecycle and serialized participant steps",
            },
        ),
        evaluator=standard_evaluator_capabilities(
            "cyberbattlesim",
            {
                "reward_owner": "evaluator",
                "outcome_reproduction": "stochastic-bounded",
                "proposition_projection": (
                    "binding-preserving unknown under lossy source evidence"
                ),
                "objective_terminal_state": (
                    "running until a distinct mapped terminal cause is available"
                ),
            },
        ),
        participant_runtime=_participant_capabilities(),
        cleanup=standard_cleanup_capabilities("cyberbattlesim"),
    )


def _realization_support(source_revision: str) -> tuple[RealizationSupportDeclaration, ...]:
    """Declare the selected generated-chain realization and its disclosures."""

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
                "source_profile": f"cyberbattlesim-chain-public-{source_revision[:7]}",
                "topology": "representative authored topology maps to generated size-10 chain",
            },
        ),
    )


def create_cyberbattlesim_manifest() -> BackendManifest:
    """Return the manifest for the admitted selected source profile."""

    source_revision = read_source_revision(load_qualification)
    return assemble_manifest(
        CYBERBATTLESIM_BACKEND_NAME,
        _capabilities(),
        _realization_support(source_revision),
        {
            "source_identity": "qualified-complete-runtime-artifact-roots-attested",
            "protocol_configuration": "attested",
            "execution_controls": "partial",
            "run_evidence": "attestable",
            "outcome_reproduction": "stochastic-bounded",
            "dependency_installation": "separately-installed-pinned-source",
        },
    )


__all__ = [
    "CYBERBATTLESIM_BACKEND_NAME",
    "create_cyberbattlesim_manifest",
]
