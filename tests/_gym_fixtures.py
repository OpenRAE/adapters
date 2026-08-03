"""Shared RAES model builders for the gym-backend contract tests.

CyberBattleSim and NASim exercise the same published participant, action, and
cleanup contracts; only the backend identities differ. These builders are
parameterized by a small :class:`GymFixtureConfig` so each backend's test
supplies its own names without copying the model construction.
"""

from __future__ import annotations

from dataclasses import dataclass

from raes_contracts.contracts import (
    ApparatusIdentityModel,
    CleanStateRequirementModel,
    CleanupObligationModel,
    CleanupResourceBoundaryModel,
    ExecutionRetryPolicyModel,
    ParticipantExposurePolicyModel,
    ParticipantImplementationCapabilitiesModel,
    ParticipantImplementationCompatibilityModel,
    ParticipantImplementationManifestModel,
    ParticipantImplementationSelectionModel,
    TrialCleanupPlanModel,
)
from raes_contracts.participant_action_arguments import ParticipantValidatedActionSelection
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest


@dataclass(frozen=True)
class GymFixtureConfig:
    """Backend identities the shared model builders fill into RAES contracts."""

    name: str
    backend_name: str
    participant_address: str
    observation_boundary: str
    action_evidence_ref: str
    implementation_name: str
    participant_runtime_name: str


def participant_manifest(config: GymFixtureConfig) -> ParticipantImplementationManifestModel:
    """Build a policy participant-implementation manifest for the backend."""

    contracts = [
        "participant-implementation-manifest-v1",
        "participant-implementation-provenance-v1",
        "participant-episode-state-envelope-v1",
        "participant-episode-history-event-stream-v1",
        "participant-behavior-history-event-stream-v1",
        "participant-decision-surface-v2",
    ]
    return ParticipantImplementationManifestModel(
        identity=ApparatusIdentityModel(name=config.implementation_name, version="1.0.0"),
        implementation_kind="policy",
        supported_contract_versions=contracts,
        compatibility=ParticipantImplementationCompatibilityModel(
            participant_runtimes=[config.participant_runtime_name],
            backends=[config.backend_name],
        ),
        concept_bindings=[
            {"scope": "implementation_kind", "family": "apparatus-declarations"},
            {
                "scope": "capabilities.supported_participant_contracts",
                "family": "apparatus-declarations",
            },
            {
                "scope": "capabilities.supported_decision_surface_modes",
                "family": "apparatus-declarations",
            },
            {"scope": "capabilities.tool_affordance_expectations", "family": "tools-and-artifacts"},
            {"scope": "capabilities.exposure_policy_kinds", "family": "provenance-and-evidence"},
        ],
        capabilities=ParticipantImplementationCapabilitiesModel(
            supported_participant_contracts=[
                "participant-episode-state-envelope-v1",
                "participant-episode-history-event-stream-v1",
                "participant-behavior-history-event-stream-v1",
                "participant-decision-surface-v2",
            ],
            supported_decision_surface_modes=["policy-directed"],
            tool_affordance_expectations=["credential-store"],
            exposure_policy_kinds=["hidden-truth", "observation-stream"],
        ),
    )


def action_request(
    config: GymFixtureConfig,
    action_contract_address: str,
    *,
    action_instance_id: str = "action-1",
    disclose_action_evidence: bool = True,
    target_addresses: tuple[str, ...] = (),
) -> ParticipantActionAdmissionRequest:
    """Build one validated participant action admission request."""

    manifest = participant_manifest(config)
    exposure_policy = ParticipantExposurePolicyModel(
        policy_id=f"{config.name}-attacker-view",
        exposure_policy_kinds=["hidden-truth", "observation-stream"],
        disclosed_refs=[config.observation_boundary],
        withheld_refs=[f"evidence.{config.name}.hidden-world"],
        visibility_scope_refs=[config.participant_address],
    )
    selection = ParticipantImplementationSelectionModel(
        participant_address=config.participant_address,
        implementation_identity=manifest.identity,
        manifest_ref=f"manifest.{config.name}.policy",
        manifest_digest="sha256:" + "1" * 64,
        selected_decision_surface_mode="policy-directed",
        participant_contract_versions=[
            "participant-episode-state-envelope-v1",
            "participant-behavior-history-event-stream-v1",
            "participant-decision-surface-v2",
        ],
        exposure_policy=exposure_policy,
    )
    return ParticipantActionAdmissionRequest(
        participant_address=config.participant_address,
        action_contract_address=action_contract_address,
        observation_boundary_address=config.observation_boundary,
        action_instance_id=action_instance_id,
        implementation_manifest=manifest,
        implementation_selection=selection,
        visible_refs=(config.observation_boundary,),
        disclosed_refs=(config.observation_boundary,),
        observation_boundary_evidence_refs=(
            (config.action_evidence_ref,) if disclose_action_evidence else ()
        ),
        validated_selection=ParticipantValidatedActionSelection(
            action_contract_address=action_contract_address,
            argument_shape_ref=f"argument-shape.{config.name}.selected-action",
            proposal_ref=f"proposal.{action_instance_id}",
            normalized_arguments=(),
            loss_disclosure_refs=("loss-abstracted-state",),
        ),
        target_addresses=target_addresses,
        requires_terminal_outcome=True,
    )


def cleanup_plan(config: GymFixtureConfig, *, required: bool = True) -> TrialCleanupPlanModel:
    """Build a destroy+verify cleanup plan for the backend's in-process driver."""

    boundary = CleanupResourceBoundaryModel(
        boundary_id=f"{config.name}-process",
        resource_kind="in-process-simulator",
        owner_ref=config.backend_name,
        resource_refs=[f"runtime.{config.name}.selected-environment"],
    )
    destroy = CleanupObligationModel(
        obligation_id="destroy-environment",
        boundary_refs=[boundary.boundary_id],
        action_kind="destroy",
        triggers=["success", "failure"],
        requirement="required" if required else "best-effort",
        idempotency="idempotent",
        verification_probe_refs=[f"probe:{config.name}-closed"],
        timeout_seconds=5,
    )
    verify = CleanupObligationModel(
        obligation_id="verify-environment-closed",
        boundary_refs=[boundary.boundary_id],
        action_kind="verify",
        triggers=["success", "failure"],
        requirement="best-effort",
        depends_on=[destroy.obligation_id],
        idempotency="idempotent",
        verification_probe_refs=[f"probe:{config.name}-closed"],
        timeout_seconds=5,
    )
    return TrialCleanupPlanModel(
        plan_id=f"{config.name}-cleanup",
        plan_entry_id=f"{config.name}-cleanup-entry",
        run_id=f"{config.name}-run",
        clean_state=CleanStateRequirementModel(
            mode="verified-reset",
            boundary_refs=[boundary.boundary_id],
            verification_probe_refs=[f"probe:{config.name}-closed"],
        ),
        resource_boundaries={boundary.boundary_id: boundary},
        cleanup_obligations={destroy.obligation_id: destroy, verify.obligation_id: verify},
        retry_policy=ExecutionRetryPolicyModel(max_attempts=1, after_effect_policy="disallow"),
    )
