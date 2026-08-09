"""CyberBattleSim participant lifecycle and one-step action execution."""

from __future__ import annotations

from raes_contracts.contracts import (  # type: ignore[import-untyped]
    ParticipantConfigurationResultModel,
    ParticipantImplementationManifestModel,
    ParticipantImplementationSelectionModel,
    ParticipantTemporalRuntimeContextModel,
)
from raes_contracts.contracts.participant_execution import (  # type: ignore[import-untyped]
    ParticipantExecutionControlRequestModel,
    ParticipantExecutionServiceStateModel,
)
from raes_contracts.participant_action_arguments import (  # type: ignore[import-untyped]
    ParticipantValidatedActionSelection,
)
from raes_contracts.participant_binding import (  # type: ignore[import-untyped]
    ParticipantActionAdmissionRequest,
)
from raes_contracts.participant_episode import (  # type: ignore[import-untyped]
    ParticipantEpisodeTerminalReason,
)
from raes_contracts.runtime_state import (  # type: ignore[import-untyped]
    ApplyResult,
    RuntimeSnapshot,
)

from raes_adapters._gym_backend.participant_runtime import (
    GymParticipantConfig,
    GymParticipantRuntime,
    StepFacts,
)

from .driver import CyberBattleSimDriverProtocol

ACTION_EVIDENCE_REF = "evidence.cyberbattlesim.attacker-action"

_ACTION_KIND_BY_CONTRACT = {
    "participant.action-contract.connect": "connect",
    "participant.action-contract.local-vulnerability": "local-vulnerability",
    "participant.action-contract.remote-vulnerability": "remote-vulnerability",
}
_REDACTED_OBSERVATION_FIELDS = [
    "native-state",
    "native-action-availability",
    "native-credential-material",
    "evaluator-only-facts",
]
_REDACTED_FIELD_REFS = ["native-state", "evaluator-only-facts"]
_RED = "participant.behavior.red"
_OBSERVATION_BOUNDARY = "participant.observation-boundary.attacker-view"
_ACTION_ARGUMENT_SHAPE = "participant.action-argument-shape.cyberbattlesim"
_TARGET_BY_ACTION_CONTRACT = {
    "participant.action-contract.connect": "provision.node.customer-data",
    "participant.action-contract.local-vulnerability": "provision.node.linux-relay",
    "participant.action-contract.remote-vulnerability": "provision.node.windows-relay",
}


def _terminal_reason(step: StepFacts) -> ParticipantEpisodeTerminalReason:
    """Truncate on the evaluator cutoff; otherwise complete the episode."""

    return (
        ParticipantEpisodeTerminalReason.TRUNCATED
        if step.truncated or step.terminal_cause == "evaluator-cutoff"
        else ParticipantEpisodeTerminalReason.COMPLETED
    )


class CyberBattleSimParticipantRuntime(GymParticipantRuntime):
    """Bind RAES participant lifecycle to exactly one serialized source action."""

    def __init__(
        self,
        driver: CyberBattleSimDriverProtocol,
        *,
        seed: int | None = None,
        participant_manifest: ParticipantImplementationManifestModel | None = None,
        participant_selection: ParticipantImplementationSelectionModel | None = None,
        participant_configuration: ParticipantConfigurationResultModel | None = None,
        conformance_mode: bool = False,
    ) -> None:
        self._driver = driver
        self._participant_manifest = participant_manifest
        self._participant_selection = participant_selection
        self._participant_configuration = participant_configuration
        self._conformance_mode = conformance_mode
        super().__init__(
            GymParticipantConfig(
                name="cyberbattlesim",
                action_kind_by_contract=_ACTION_KIND_BY_CONTRACT,
                redacted_observation_fields=_REDACTED_OBSERVATION_FIELDS,
                redacted_field_refs=_REDACTED_FIELD_REFS,
            ),
            reset_driver=driver.reset,
            drive_step=self._drive_authorized_step,
            terminal_reason=_terminal_reason,
            seed=seed,
        )

    def _drive_authorized_step(
        self,
        action_kind: str,
        request: ParticipantActionAdmissionRequest,
    ) -> StepFacts:
        """Pass only an exact portable autonomous authorization to the driver."""

        selected = request.validated_selection
        if selected is None:
            return self._driver.step(action_kind)
        target = selected.argument_map.get("target_address")
        if target is None:
            return self._driver.step(action_kind)
        if self._is_conformance_probe_binding(request):
            return self._driver.step(action_kind)
        manifest = self._participant_manifest
        selection = self._participant_selection
        configuration = self._participant_configuration
        expected = _TARGET_BY_ACTION_CONTRACT.get(request.action_contract_address)
        if (
            manifest is None
            or selection is None
            or configuration is None
            or request.participant_address != _RED
            or request.observation_boundary_address != _OBSERVATION_BOUNDARY
            or request.visible_refs != (_OBSERVATION_BOUNDARY,)
            or request.disclosed_refs != (_OBSERVATION_BOUNDARY,)
            or request.implementation_manifest != manifest
            or request.implementation_selection != selection
            or selection.participant_address != _RED
            or tuple(selection.exposure_policy.visibility_scope_refs) != (_RED,)
            or _OBSERVATION_BOUNDARY not in selection.exposure_policy.disclosed_refs
            or selection.implementation_identity != manifest.identity
            or configuration.configuration.implementation_identity != manifest.identity
            or selected.action_contract_address != request.action_contract_address
            or not isinstance(target, str)
            or target != expected
            or request.target_addresses != (target,)
        ):
            raise ValueError("autonomous action authorization is invalid")
        return self._driver.step(
            action_kind,
            target_address=target,
            proposal_ref=selected.proposal_ref,
        )

    def _is_conformance_probe_binding(
        self,
        request: ParticipantActionAdmissionRequest,
    ) -> bool:
        """Recognize only the published RAES probe's synthetic fixture identities."""

        return (
            self._conformance_mode
            and request.participant_address
            in {"participant.conformance", "participant.conformance-2"}
            and request.action_instance_id.startswith("participant-execution-conformance-")
            and request.execution_scope_ref == "participant.autonomous-execution.conformance"
        )

    def bind_autonomous_action(
        self,
        participant_address: str,
        action_contract_address: str,
        observation_boundary_address: str,
        participant_implementation_ref: str,
        action_instance_id: str,
        temporal_contexts: tuple[ParticipantTemporalRuntimeContextModel, ...],
        snapshot: RuntimeSnapshot,
    ) -> ParticipantActionAdmissionRequest:
        """Bind one source-policy proposal to its exact configured apparatus."""

        manifest = self._participant_manifest
        selection = self._participant_selection
        configuration = self._participant_configuration
        conformance_binding = (
            self._conformance_mode
            and participant_address in {"participant.conformance", "participant.conformance-2"}
            and action_instance_id.startswith("participant-execution-conformance-")
            and "participant.autonomous-execution.conformance"
            in snapshot.participant_execution_services
        )
        if (
            manifest is None
            or selection is None
            or configuration is None
            or selection.manifest_ref != participant_implementation_ref
            or action_contract_address not in _ACTION_KIND_BY_CONTRACT
            or (not conformance_binding and selection.participant_address != participant_address)
            or (
                not conformance_binding
                and tuple(selection.exposure_policy.visibility_scope_refs) != (participant_address,)
            )
            or observation_boundary_address not in selection.exposure_policy.disclosed_refs
            or selection.implementation_identity != manifest.identity
            or configuration.configuration.implementation_identity != manifest.identity
        ):
            raise ValueError("autonomous participant binding is unavailable")
        bound_selection = selection
        if conformance_binding:
            exposure_policy = selection.exposure_policy.model_copy(
                update={"visibility_scope_refs": [participant_address]}
            )
            bound_selection = selection.model_copy(
                update={
                    "participant_address": participant_address,
                    "exposure_policy": exposure_policy,
                }
            )
        target_address = _TARGET_BY_ACTION_CONTRACT[action_contract_address]
        return ParticipantActionAdmissionRequest(
            participant_address=participant_address,
            action_contract_address=action_contract_address,
            observation_boundary_address=observation_boundary_address,
            action_instance_id=action_instance_id,
            implementation_manifest=manifest,
            implementation_selection=bound_selection,
            visible_refs=(observation_boundary_address,),
            disclosed_refs=(observation_boundary_address,),
            validated_selection=ParticipantValidatedActionSelection(
                action_contract_address=action_contract_address,
                argument_shape_ref=_ACTION_ARGUMENT_SHAPE,
                proposal_ref=f"proposal:{action_instance_id}",
                normalized_arguments=(("target_address", target_address),),
                loss_disclosure_refs=("loss-observation-abstraction",),
            ),
            temporal_contexts=temporal_contexts,
            target_addresses=(target_address,),
            requires_terminal_outcome=True,
        )

    def control_execution(
        self,
        request: ParticipantExecutionControlRequestModel,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        """Publish bounded lifecycle readback for the in-process policy service."""

        payload = snapshot.participant_execution_services.get(request.execution_scope_ref)
        if payload is None:
            return ApplyResult(success=False, snapshot=snapshot)
        before = ParticipantExecutionServiceStateModel.model_validate(payload)
        lifecycle = {
            "start": "running",
            "resume": "running",
            "reset": "running",
            "pause": "paused",
            "drain": "quiescent",
            "teardown": "terminated",
        }[request.action]
        generation = before.generation + (1 if request.action == "reset" else 0)
        transition = f"{request.execution_scope_ref}.transition.{generation}.{request.action}"
        evidence = tuple(dict.fromkeys((*before.evidence_refs, transition)))
        accepting = lifecycle == "running"
        observed = before.model_copy(
            update={
                "desired_lifecycle": lifecycle,
                "observed_lifecycle": lifecycle,
                "generation": generation,
                "observed_generation": generation,
                "health": "healthy",
                "readiness": "ready" if accepting else "not_ready",
                "accepting_new_work": accepting,
                "draining": False,
                "quiescent": lifecycle in {"quiescent", "terminated"},
                "resources_released": lifecycle == "terminated",
                "reserved": 0,
                "in_flight": 0,
                "last_transition_ref": transition,
                "evidence_refs": evidence,
            }
        )
        services = dict(snapshot.participant_execution_services)
        services[request.execution_scope_ref] = observed.model_dump(mode="json")
        return ApplyResult(
            success=True,
            snapshot=snapshot.with_entries(
                dict(snapshot.entries), participant_execution_services=services
            ),
            changed_addresses=[request.execution_scope_ref],
        )

    @staticmethod
    def execution_state(
        execution_scope_ref: str,
        snapshot: RuntimeSnapshot,
    ) -> ParticipantExecutionServiceStateModel:
        """Return validated lifecycle state for one configured execution scope."""

        payload = snapshot.participant_execution_services.get(execution_scope_ref)
        if payload is None:
            raise ValueError("participant execution scope is unavailable")
        return ParticipantExecutionServiceStateModel.model_validate(payload)


__all__ = [
    "ACTION_EVIDENCE_REF",
    "CyberBattleSimParticipantRuntime",
]
