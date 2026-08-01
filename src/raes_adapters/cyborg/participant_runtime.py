"""Portable participant execution for one aggregate CAGE-2 logical turn."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from typing import NamedTuple, cast

from raes_backend_protocols.participant_runtime_base import (  # type: ignore[import-untyped]
    BaseParticipantRuntime,
)
from raes_contracts.contracts import (  # type: ignore[import-untyped]
    ParticipantActionEffectResultModel,
    ParticipantActionResultModel,
    ParticipantBehaviorHistoryEventModel,
    ParticipantObservationEnvelopeModel,
    ParticipantObservationLossDescriptorModel,
    ParticipantObservationStochasticContextModel,
    SourceStatusModel,
)
from raes_contracts.diagnostics import Diagnostic  # type: ignore[import-untyped]
from raes_contracts.participant_binding import (  # type: ignore[import-untyped]
    ParticipantActionAdmissionRequest,
    ParticipantActionApplyResult,
    ParticipantNativeActionExecution,
)
from raes_contracts.participant_episode import (  # type: ignore[import-untyped]
    ParticipantEpisodeExecutionState,
    ParticipantEpisodeResetRequest,
    ParticipantEpisodeRestartRequest,
    ParticipantEpisodeStatus,
)
from raes_contracts.runtime_state import (  # type: ignore[import-untyped]
    ApplyResult,
    RuntimeSnapshot,
)
from raes_runtime.participant_result_contracts import (  # type: ignore[import-untyped]
    participant_runtime_history_transition_diagnostics,
    participant_runtime_state_contract_diagnostics,
)
from raes_runtime.registry import ReferenceTimeRuntime  # type: ignore[import-untyped]

from .driver import _NativeTurnResult
from .orchestrator import CyborgExecutionControl, CyborgOrchestrator, _ExecutionPolicy
from .provisioner import CyborgProvisioner

_BLUE = "participant.behavior.blue"
_GREEN = "participant.behavior.green"
_RED = "participant.behavior.red"
_ORDER = (_BLUE, _GREEN, _RED)
_CONTROL_TURN_LEDGER = "source-ledger:control-turn-order"
_PRODUCER = "cyborg-cage2-participant-runtime"
_SERIALIZED_ORDER = "serialized_backend_order"
_OBSERVATION_PROVENANCE = [
    "source-ledger:observation-visibility",
    "source-ledger:observation-hidden-truth",
    "mapping:loss-native-observation-boundary",
]
_REDACTED_OBSERVATION_FIELDS = [
    "native-observation",
    "native-action-mask",
    "native-action-id",
    "native-reward-vector",
    "native-hidden-truth",
    "native-object-representation",
]


def _now_iso() -> str:
    """Return one portable UTC timestamp."""

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class _TurnRejected(Exception):
    """Bounded pre-commit rejection with optional session quarantine."""

    def __init__(self, reason: str, *, quarantine: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.quarantine = quarantine


class _ResetRejected(Exception):
    """Bounded reset staging failure with optional contract diagnostics."""

    def __init__(self, diagnostics: list[Diagnostic] | None = None) -> None:
        super().__init__("aggregate reset rejected")
        self.diagnostics = diagnostics


class _TurnRecordContext(NamedTuple):
    """Common logical-time fields for one aggregate-turn record set."""

    now: str
    clock_address: str
    tick: int


class _RuntimeCheckpoint(NamedTuple):
    """Participant-runtime mirrors that must roll back with native failures."""

    results: dict[str, dict[str, object]]
    history: dict[str, list[dict[str, object]]]
    episode_counter: dict[str, int]
    observations: dict[str, list[ParticipantObservationEnvelopeModel]]
    pending_observations: dict[str, tuple[ParticipantObservationEnvelopeModel, ...]]


class CyborgParticipantRuntime(BaseParticipantRuntime):  # type: ignore[misc]
    """Translate admitted blue actions and project all three native occurrences."""

    def __init__(
        self,
        provisioner: CyborgProvisioner,
        control: CyborgExecutionControl,
        orchestrator: CyborgOrchestrator,
        time_runtime: ReferenceTimeRuntime,
    ) -> None:
        super().__init__()
        self._results: dict[str, dict[str, object]]
        self._history: dict[str, list[dict[str, object]]]
        self._episode_counter: dict[str, int]
        self._observations: dict[str, list[ParticipantObservationEnvelopeModel]] = {}
        self._pending_observations: dict[
            str,
            tuple[ParticipantObservationEnvelopeModel, ...],
        ] = {}
        self._provisioner = provisioner
        self._control = control
        self._orchestrator = orchestrator
        self._time_runtime = time_runtime

    def reset(
        self,
        request: ParticipantEpisodeResetRequest,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        """Require the aggregate red/green/blue session to reset as one unit."""

        del request
        return ApplyResult(
            success=False,
            snapshot=snapshot,
            diagnostics=[
                Diagnostic(
                    code="cyborg-backend.participant-reset.coordination-required",
                    domain="participant",
                    address="cyborg-cage2",
                    message="CAGE-2 participant episodes must be reset together.",
                )
            ],
        )

    def reset_many(
        self,
        requests: tuple[ParticipantEpisodeResetRequest, ...],
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        """Serialize one complete native, participant, workflow, and time reset."""

        with self._provisioner.execution_transaction():
            return self._reset_many_transaction(requests, snapshot)

    def _reset_many_transaction(
        self,
        requests: tuple[ParticipantEpisodeResetRequest, ...],
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        """Stage all portable resets, then reset the native aggregate once."""

        if {item.participant_address for item in requests} != set(_ORDER) or len(requests) != 3:
            result = self.reset(
                ParticipantEpisodeResetRequest(participant_address=_BLUE),
                snapshot,
            )
        else:
            checkpoint = self._checkpoint()
            policy = self._control.policy()
            if policy is None:
                result = self.reset(
                    ParticipantEpisodeResetRequest(participant_address=_BLUE), snapshot
                )
            else:
                result = self._coordinated_reset(requests, snapshot, policy, checkpoint)
        return result

    def _coordinated_reset(
        self,
        requests: tuple[ParticipantEpisodeResetRequest, ...],
        snapshot: RuntimeSnapshot,
        policy: _ExecutionPolicy,
        checkpoint: _RuntimeCheckpoint,
    ) -> ApplyResult:
        """Commit one staged portable reset and then one native reset."""

        return self._commit_coordinated_lifecycle(
            snapshot,
            policy,
            checkpoint,
            lambda: self._portable_reset_candidate(requests, snapshot, policy),
        )

    def restart(
        self,
        request: ParticipantEpisodeRestartRequest,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        """Require aggregate restart for the shared red/green/blue session."""

        del request
        return ApplyResult(
            success=False,
            snapshot=snapshot,
            diagnostics=[
                Diagnostic(
                    code="cyborg-backend.participant-restart.coordination-required",
                    domain="participant",
                    address="cyborg-cage2",
                    message="CAGE-2 participant episodes must be restarted together.",
                )
            ],
        )

    def restart_many(
        self,
        requests: tuple[ParticipantEpisodeRestartRequest, ...],
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        """Serialize one complete native, participant, workflow, and time restart."""

        with self._provisioner.execution_transaction():
            return self._restart_many_transaction(requests, snapshot)

    def _restart_many_transaction(
        self,
        requests: tuple[ParticipantEpisodeRestartRequest, ...],
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        """Stage all portable restarts, then reset the native aggregate once."""

        if {item.participant_address for item in requests} != set(_ORDER) or len(requests) != 3:
            result = self.restart(
                ParticipantEpisodeRestartRequest(participant_address=_BLUE),
                snapshot,
            )
        else:
            checkpoint = self._checkpoint()
            policy = self._control.policy()
            if policy is None:
                result = self.restart(
                    ParticipantEpisodeRestartRequest(participant_address=_BLUE), snapshot
                )
            else:
                result = self._coordinated_restart(requests, snapshot, policy, checkpoint)
        return result

    def _coordinated_restart(
        self,
        requests: tuple[ParticipantEpisodeRestartRequest, ...],
        snapshot: RuntimeSnapshot,
        policy: _ExecutionPolicy,
        checkpoint: _RuntimeCheckpoint,
    ) -> ApplyResult:
        """Commit one staged portable restart and then one native reset."""

        return self._commit_coordinated_lifecycle(
            snapshot,
            policy,
            checkpoint,
            lambda: self._portable_restart_candidate(requests, snapshot, policy),
        )

    def _commit_coordinated_lifecycle(
        self,
        snapshot: RuntimeSnapshot,
        policy: _ExecutionPolicy,
        checkpoint: _RuntimeCheckpoint,
        candidate: Callable[[], tuple[RuntimeSnapshot, list[str], list[Diagnostic]]],
    ) -> ApplyResult:
        """Commit one staged portable lifecycle batch and one native reset."""

        try:
            working, changed, diagnostics = candidate()
        except _ResetRejected as rejected:
            self._restore_checkpoint(checkpoint)
            result = (
                self._reset_failure(snapshot)
                if rejected.diagnostics is None
                else ApplyResult(
                    success=False,
                    snapshot=snapshot,
                    diagnostics=rejected.diagnostics,
                )
            )
        except Exception:
            self._restore_checkpoint(checkpoint)
            result = self._reset_failure(snapshot)
        else:
            if not self._provisioner.reset_execution():
                self._restore_checkpoint(checkpoint)
                result = self._reset_failure(snapshot)
            else:
                self._clear_observations()
                self._control.reset_terminal()
                result = ApplyResult(
                    success=True,
                    snapshot=working,
                    diagnostics=diagnostics,
                    changed_addresses=list(dict.fromkeys([*changed, policy.clock_address])),
                )
        return result

    def _portable_reset_candidate(
        self,
        requests: tuple[ParticipantEpisodeResetRequest, ...],
        snapshot: RuntimeSnapshot,
        policy: _ExecutionPolicy,
    ) -> tuple[RuntimeSnapshot, list[str], list[Diagnostic]]:
        """Stage and validate every portable part of a coordinated reset."""

        timed = self._time_runtime.reset(policy.clock_address, False, snapshot)
        if not timed.success:
            raise _ResetRejected
        working = timed.snapshot
        changed: list[str] = []
        diagnostics: list[Diagnostic] = []
        for request in requests:
            reset_result = BaseParticipantRuntime.reset(self, request, working)
            diagnostics.extend(reset_result.diagnostics)
            if not reset_result.success:
                raise _ResetRejected(diagnostics)
            working = reset_result.snapshot
            changed.extend(reset_result.changed_addresses)
        working = self._orchestrator.mark_reset(working)
        invalid = [
            *participant_runtime_state_contract_diagnostics(working),
            *participant_runtime_history_transition_diagnostics(snapshot, working),
        ]
        if invalid:
            raise _ResetRejected
        return working, changed, diagnostics

    def _portable_restart_candidate(
        self,
        requests: tuple[ParticipantEpisodeRestartRequest, ...],
        snapshot: RuntimeSnapshot,
        policy: _ExecutionPolicy,
    ) -> tuple[RuntimeSnapshot, list[str], list[Diagnostic]]:
        """Stage and validate every portable part of a coordinated restart."""

        timed = self._time_runtime.reset(policy.clock_address, False, snapshot)
        if not timed.success:
            raise _ResetRejected
        working = timed.snapshot
        changed: list[str] = []
        diagnostics: list[Diagnostic] = []
        for request in requests:
            restart_result = BaseParticipantRuntime.restart(self, request, working)
            diagnostics.extend(restart_result.diagnostics)
            if not restart_result.success:
                raise _ResetRejected(diagnostics)
            working = restart_result.snapshot
            changed.extend(restart_result.changed_addresses)
        working = self._orchestrator.mark_reset(working)
        invalid = [
            *participant_runtime_state_contract_diagnostics(working),
            *participant_runtime_history_transition_diagnostics(snapshot, working),
        ]
        if invalid:
            raise _ResetRejected
        return working, changed, diagnostics

    def _checkpoint(self) -> _RuntimeCheckpoint:
        """Capture every mutable mirror touched before native commit."""

        return _RuntimeCheckpoint(
            deepcopy(self._results),
            deepcopy(self._history),
            deepcopy(self._episode_counter),
            deepcopy(self._observations),
            deepcopy(self._pending_observations),
        )

    def _restore_checkpoint(self, checkpoint: _RuntimeCheckpoint) -> None:
        """Restore mutable mirrors after a failed aggregate transition."""

        (
            self._results,
            self._history,
            self._episode_counter,
            self._observations,
            self._pending_observations,
        ) = checkpoint

    def _clear_observations(self) -> None:
        """Drop only episode-scoped observation envelopes after recovery."""

        self._observations = {}
        self._pending_observations = {}

    @staticmethod
    def _reset_failure(snapshot: RuntimeSnapshot) -> ApplyResult:
        """Return the bounded aggregate-reset failure."""

        return ApplyResult(
            success=False,
            snapshot=snapshot,
            diagnostics=[
                Diagnostic(
                    code="cyborg-backend.participant-reset.failed",
                    domain="participant",
                    address="cyborg-cage2",
                    message="The CAGE-2 aggregate session could not be reset.",
                )
            ],
        )

    def admit_action(
        self,
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
    ) -> ParticipantActionApplyResult:
        """Serialize and validate the complete native-and-portable turn commit."""

        with self._provisioner.execution_transaction():
            generation = self._provisioner.execution_generation()
            action_instance_id = request.action_instance_id
            try:
                result = BaseParticipantRuntime.admit_action(self, request, snapshot)
            except Exception:
                self._pending_observations.pop(action_instance_id, None)
                if self._provisioner.execution_generation() != generation:
                    self._provisioner.quarantine_execution()
                result = self._commit_failure(request, snapshot)
            if (
                isinstance(result, ParticipantActionApplyResult)
                and self._provisioner.execution_generation() != generation
            ):
                if not result.success:
                    self._provisioner.quarantine_execution()
                else:
                    diagnostics = [
                        *participant_runtime_state_contract_diagnostics(result.snapshot),
                        *participant_runtime_history_transition_diagnostics(
                            snapshot, result.snapshot
                        ),
                    ]
                    if diagnostics:
                        self._provisioner.quarantine_execution()
                        result = self._commit_failure(request, snapshot)
            if isinstance(result, ParticipantActionApplyResult) and result.success:
                self._commit_observations(action_instance_id)
                self._provisioner.commit_evaluation(action_instance_id)
            else:
                self._pending_observations.pop(action_instance_id, None)
            return result

    def _commit_failure(
        self,
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
    ) -> ParticipantActionApplyResult:
        """Return the bounded post-effect portable-commit failure."""

        return ParticipantActionApplyResult(
            success=False,
            snapshot=snapshot,
            diagnostics=[
                Diagnostic(
                    code="cyborg-backend.action.portable-commit-failed",
                    domain="participant",
                    address=_BLUE,
                    message="The aggregate turn could not be committed to portable runtime state.",
                )
            ],
            action_result=self._action_result(
                request,
                episode_id=_episode_id(snapshot, request.participant_address),
                status="failed",
                failure_class="backend_error",
                observation_ref=_withheld_observation_ref(request, "portable-commit-failed"),
            ),
        )

    def _model_action(
        self,
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
        *,
        episode_id: str,
    ) -> ParticipantNativeActionExecution:
        """Execute and stage one admitted aggregate native turn."""

        try:
            policy, tick = self._action_context(request, snapshot)
            projected = self._native_turn(
                request,
                policy=policy,
                episode_id=episode_id,
                tick=tick,
            )
            next_snapshot, observations = self._advance_portable_turn(
                snapshot,
                request=request,
                episode_id=episode_id,
                policy=policy,
                projected=projected,
                tick=tick,
            )
            self._pending_observations[request.action_instance_id] = observations
        except _TurnRejected as rejected:
            if rejected.quarantine:
                self._provisioner.quarantine_execution()
            execution = self._reject_action(
                request,
                snapshot,
                episode_id=episode_id,
                reason=rejected.reason,
            )
        else:
            execution = self._successful_execution(
                request,
                episode_id=episode_id,
                policy=policy,
                projected=projected,
                snapshot=next_snapshot,
            )
        return execution

    def _action_context(
        self,
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
    ) -> tuple[_ExecutionPolicy, int]:
        """Validate all pre-effect session and logical-time conditions."""

        policy = self._control.policy()
        if request.participant_address != _BLUE or request.validated_selection is None:
            raise _TurnRejected("invalid-selection")
        if not self._provisioner.selection_targets_are_realized(request.validated_selection):
            raise _TurnRejected("unsupported-binding")
        if not _all_participants_running(snapshot):
            raise _TurnRejected("participants-not-ready")
        if policy is None or self._control.is_source_terminal():
            raise _TurnRejected("run-not-active")
        tick = _clock_tick(snapshot, policy.clock_address)
        if tick is None or tick >= policy.max_steps:
            raise _TurnRejected("trial-complete")
        if not self._provisioner.execution_available():
            raise _TurnRejected("session-unavailable")
        return policy, tick

    def _native_turn(
        self,
        request: ParticipantActionAdmissionRequest,
        *,
        policy: _ExecutionPolicy,
        episode_id: str,
        tick: int,
    ) -> _NativeTurnResult:
        """Execute and validate the bounded native turn projection."""

        try:
            projected = self._provisioner.execute_turn(
                request.validated_selection,
                run_id=f"{policy.workflow_address}-run",
                episode_id=episode_id,
                action_instance_id=request.action_instance_id,
                logical_step=tick + 1,
                logical_step_limit=policy.max_steps,
            )
        except RuntimeError:
            raise _TurnRejected("turn-failed") from None
        if not _valid_turn(projected, request.action_contract_address):
            raise _TurnRejected("projection-failed", quarantine=True)
        return cast(_NativeTurnResult, projected)

    def _advance_portable_turn(
        self,
        snapshot: RuntimeSnapshot,
        *,
        request: ParticipantActionAdmissionRequest,
        episode_id: str,
        policy: _ExecutionPolicy,
        projected: _NativeTurnResult,
        tick: int,
    ) -> tuple[RuntimeSnapshot, tuple[ParticipantObservationEnvelopeModel, ...]]:
        """Advance logical time and stage the complete portable turn."""

        advanced = self._time_runtime.advance(policy.clock_address, 1, 0, snapshot)
        if not advanced.success:
            raise _TurnRejected("clock-failed", quarantine=True)
        next_tick = tick + 1
        next_snapshot = self._portable_turn(
            advanced.snapshot,
            request=request,
            episode_id=episode_id,
            projected=projected,
            tick=next_tick,
            clock_address=policy.clock_address,
        )
        if projected.source_terminal:
            self._control.mark_source_terminal()
            next_snapshot = self._orchestrator.mark_completed(next_snapshot, "source-terminal")
        elif next_tick == policy.max_steps:
            next_snapshot = self._orchestrator.mark_completed(next_snapshot, "logical-step-limit")
        observations = _turn_observations(
            snapshot,
            request=request,
            projected=projected,
            tick=next_tick,
            clock_address=policy.clock_address,
        )
        return next_snapshot, observations

    @staticmethod
    def _successful_execution(
        request: ParticipantActionAdmissionRequest,
        *,
        episode_id: str,
        policy: _ExecutionPolicy,
        projected: _NativeTurnResult,
        snapshot: RuntimeSnapshot,
    ) -> ParticipantNativeActionExecution:
        """Build the typed result for one portable aggregate-turn commit."""

        observation_ref = _observation_ref(
            request.participant_address,
            episode_id,
            tick=_clock_tick(snapshot, policy.clock_address) or 0,
            action_instance_id=request.action_instance_id,
        )
        action_result = ParticipantActionResultModel(
            status="succeeded" if projected.external_action_succeeded else "failed",
            participant_address=request.participant_address,
            episode_id=episode_id,
            action_instance_id=request.action_instance_id,
            action_contract_address=request.action_contract_address,
            observation_point=observation_ref,
            preconditions=[],
            effects=[
                ParticipantActionEffectResultModel(
                    effect_id=f"{request.action_instance_id}.observation",
                    effect_class="observation_effect",
                    description="A bounded participant-relative observation envelope was emitted.",
                    target_refs=[observation_ref],
                )
            ],
            failure_class=None if projected.external_action_succeeded else "unknown",
            observations=[observation_ref],
            resource_measurements=[],
            evidence_refs=[],
            diagnostics=[],
        )
        return ParticipantNativeActionExecution(
            apply_result=ApplyResult(
                success=True,
                snapshot=snapshot,
                changed_addresses=[request.participant_address, policy.clock_address],
            ),
            action_result=action_result,
        )

    def _reject_action(
        self,
        request: ParticipantActionAdmissionRequest,
        snapshot: RuntimeSnapshot,
        *,
        episode_id: str,
        reason: str,
    ) -> ParticipantNativeActionExecution:
        """Build one bounded action rejection."""

        diagnostic = Diagnostic(
            code=f"cyborg-backend.action.{reason}",
            domain="participant",
            address=_BLUE,
            message="The action could not be admitted to the CAGE-2 execution session.",
        )
        return ParticipantNativeActionExecution(
            apply_result=ApplyResult(success=False, snapshot=snapshot, diagnostics=[diagnostic]),
            action_result=self._action_result(
                request,
                episode_id=episode_id,
                status=_failure_status(reason),
                failure_class=_failure_class(reason),
                observation_ref=_withheld_observation_ref(request, reason),
            ),
        )

    @staticmethod
    def _action_result(
        request: ParticipantActionAdmissionRequest,
        *,
        episode_id: str,
        status: str,
        failure_class: str,
        observation_ref: str,
    ) -> ParticipantActionResultModel:
        """Build a bounded typed result for a failed or rejected action."""

        return ParticipantActionResultModel(
            status=status,
            participant_address=request.participant_address,
            episode_id=episode_id,
            action_instance_id=request.action_instance_id,
            action_contract_address=request.action_contract_address,
            observation_point=observation_ref,
            failure_class=failure_class,
            observations=[],
            evidence_refs=[],
            diagnostics=[],
        )

    def _commit_observations(self, action_instance_id: str) -> None:
        """Publish staged observations after the portable commit is valid."""

        observations = self._pending_observations.pop(action_instance_id, ())
        for observation in observations:
            self._observations.setdefault(observation.participant_address or "", []).append(
                observation
            )

    def observations(
        self,
        participant_address: str,
    ) -> tuple[ParticipantObservationEnvelopeModel, ...]:
        """Return only the requested participant's bounded observation envelopes."""

        return tuple(self._observations.get(participant_address, ()))

    @staticmethod
    def _portable_turn(
        snapshot: RuntimeSnapshot,
        *,
        request: ParticipantActionAdmissionRequest,
        episode_id: str,
        projected: _NativeTurnResult,
        tick: int,
        clock_address: str,
    ) -> RuntimeSnapshot:
        """Assemble one all-or-nothing portable aggregate-turn candidate."""

        del episode_id
        now = _now_iso()
        action_id = request.action_instance_id
        joint_id = f"cyborg.joint-action:{action_id}"
        shared_id = f"cyborg.shared-state:{action_id}"
        context_id = f"cyborg.time-context:{action_id}"
        realized = [action_id, f"{action_id}:green", f"{action_id}:red"]
        context = _TurnRecordContext(now, clock_address, tick)
        behavior = _participant_history(snapshot, projected, now, realized, joint_id, shared_id)
        shared = dict(snapshot.shared_state_records)
        shared[shared_id] = _shared_state_record(shared_id, action_id, context)
        contexts = dict(snapshot.time_management_contexts)
        contexts[context_id] = _time_context_record(context_id, context)
        joints = dict(snapshot.joint_action_records)
        joints[joint_id] = _joint_action_record(joint_id, context_id, realized, context)
        return snapshot.with_entries(
            dict(snapshot.entries),
            participant_behavior_history=behavior,
            shared_state_records=shared,
            joint_action_records=joints,
            time_management_contexts=contexts,
        )


def _participant_history(
    snapshot: RuntimeSnapshot,
    projected: _NativeTurnResult,
    now: str,
    realized: list[str],
    joint_id: str,
    shared_id: str,
) -> dict[str, list[dict[str, object]]]:
    """Project internal participant occurrences into portable history."""

    behavior = {key: list(value) for key, value in snapshot.participant_behavior_history.items()}
    for index, occurrence in enumerate(projected.occurrences[1:], start=1):
        state = snapshot.participant_episode_results[occurrence.participant_address]
        event = ParticipantBehaviorHistoryEventModel(
            event_type="action_attempted",
            timestamp=now,
            participant_address=occurrence.participant_address,
            episode_id=str(state["episode_id"]),
            action_instance_id=realized[index],
            action_contract_address=occurrence.action_contract_address,
            joint_action_set_id=joint_id,
            realized_order=index,
            shared_state_refs=[shared_id],
        )
        behavior.setdefault(occurrence.participant_address, []).append(
            event.model_dump(mode="json", exclude_none=True)
        )
    return behavior


def _turn_observations(
    snapshot: RuntimeSnapshot,
    *,
    request: ParticipantActionAdmissionRequest,
    projected: _NativeTurnResult,
    tick: int,
    clock_address: str,
) -> tuple[ParticipantObservationEnvelopeModel, ...]:
    """Build participant-relative observation envelopes without native payloads."""

    now = _now_iso()
    observations: list[ParticipantObservationEnvelopeModel] = []
    for index, occurrence in enumerate(projected.occurrences):
        participant = occurrence.participant_address
        action_instance_id = (
            request.action_instance_id
            if index == 0
            else f"{request.action_instance_id}:{_role(participant)}"
        )
        episode_id = _episode_id(snapshot, participant)
        observation_ref = _observation_ref(
            participant,
            episode_id,
            tick=tick,
            action_instance_id=action_instance_id,
        )
        processed = participant != _BLUE or projected.external_action_succeeded
        observations.append(
            ParticipantObservationEnvelopeModel(
                event_id=f"event.{observation_ref}",
                schema_name="raes.participant_runtime.observation",
                schema_version="1.0.0",
                event_type="observation_emission",
                extension_policy="reject_unknown_required",
                source_status=SourceStatusModel(
                    status_id=1 if processed else 2,
                    status="success" if processed else "failure",
                    status_code=(
                        "participant_action_processed" if processed else "participant_action_failed"
                    ),
                    status_detail="A bounded CAGE-2 participant observation was projected.",
                    source_status_label="selected-cyborg-aggregate-turn",
                    source_status_mapping="raes.participant-action.terminal",
                ),
                participant_address=participant,
                episode_id=episode_id,
                sequence_number=tick,
                occurred_at=now,
                recorded_at=now,
                ingested_at=now,
                clock_authority=clock_address,
                temporal_context=f"{clock_address}:{tick}",
                ordering_basis=_SERIALIZED_ORDER,
                logical_order_ref=f"{clock_address}:{tick}",
                actor_ref=participant,
                producer_ref=_PRODUCER,
                source_system_ref="qualification.cyborg-cage2.selected-source",
                provenance_refs=list(_OBSERVATION_PROVENANCE),
                evidence_refs=["source-ledger:observation-visibility"],
                redaction_policy_ref="redaction.cyborg-cage2.participant-view",
                authorization_scope=f"participant:{participant}",
                observation_ref=observation_ref,
                visibility_projection_ref=(
                    request.observation_boundary_address
                    if participant == request.participant_address
                    else _observation_boundary(participant)
                ),
                information_guarantee="lossy_projection",
                delivery_basis="emission_is_delivery",
                delivered_at=now,
                hidden_state_refs=[],
                centralized_state_refs=[],
                loss_descriptor=ParticipantObservationLossDescriptorModel(
                    kind="loss-native-observation-boundary",
                    fields_redacted=list(_REDACTED_OBSERVATION_FIELDS),
                ),
                stochastic_context=ParticipantObservationStochasticContextModel(
                    randomization_policy_ref="qualification.cyborg-cage2.partial-stochastic-control"
                ),
                redacted_field_refs=list(_REDACTED_OBSERVATION_FIELDS),
            )
        )
    return tuple(observations)


def _all_participants_running(snapshot: RuntimeSnapshot) -> bool:
    """Require all fixed CAGE-2 participant episode heads to be running."""

    return all(
        (state := _participant_state(snapshot, address)) is not None
        and state.status == ParticipantEpisodeStatus.RUNNING
        for address in _ORDER
    )


def _participant_state(
    snapshot: RuntimeSnapshot,
    participant_address: str,
) -> ParticipantEpisodeExecutionState | None:
    """Read one participant state through the published episode model."""

    payload = snapshot.participant_episode_results.get(participant_address)
    if payload is None:
        return None
    try:
        return ParticipantEpisodeExecutionState.from_payload(payload)
    except (TypeError, ValueError):
        return None


def _episode_id(snapshot: RuntimeSnapshot, participant_address: str) -> str:
    """Return the live episode id or one bounded placeholder for failures."""

    state = _participant_state(snapshot, participant_address)
    return "episode-unavailable" if state is None else state.episode_id


def _observation_ref(
    participant_address: str,
    episode_id: str,
    *,
    tick: int,
    action_instance_id: str,
) -> str:
    """Derive a portable observation ref from episode/action coordinates."""

    return (
        f"observation.cyborg.{_role(participant_address)}.{episode_id}.{tick}.{action_instance_id}"
    )


def _withheld_observation_ref(
    request: ParticipantActionAdmissionRequest,
    reason: str,
) -> str:
    """Derive a bounded ref for a withheld observation on rejection/failure."""

    return (
        f"observation.cyborg.{_role(request.participant_address)}."
        f"{request.action_instance_id}.{reason}.withheld"
    )


def _observation_boundary(participant_address: str) -> str:
    """Return the fixed participant-relative observation-boundary address."""

    return f"participant.observation-boundary.{_role(participant_address)}"


def _role(participant_address: str) -> str:
    """Extract the bounded RAES participant role token from a fixed address."""

    return participant_address.rsplit(".", 1)[-1]


def _failure_status(reason: str) -> str:
    """Map bounded rejection reasons to RAES action-result statuses."""

    failed = {
        "clock-failed",
        "portable-commit-failed",
        "projection-failed",
        "session-unavailable",
        "turn-failed",
    }
    return "failed" if reason in failed else "rejected"


def _failure_class(reason: str) -> str:
    """Map bounded rejection reasons to RAES participant failure classes."""

    mapping = {
        "clock-failed": "backend_error",
        "invalid-selection": "unsupported_action",
        "participants-not-ready": "target_unavailable",
        "portable-commit-failed": "backend_error",
        "projection-failed": "backend_error",
        "run-not-active": "target_unavailable",
        "session-unavailable": "backend_error",
        "trial-complete": "resource_exhausted",
        "turn-failed": "backend_error",
        "unsupported-binding": "unsupported_action",
    }
    return mapping.get(reason, "unknown")


def _event_envelope(
    event_id: str,
    *,
    schema_name: str,
    schema_version: str,
    event_type: str,
    context: _TurnRecordContext,
    ordering_basis: str,
    provenance_refs: list[str],
) -> dict[str, object]:
    """Build the common published event-envelope fields."""

    return {
        "event_id": event_id,
        "schema_name": schema_name,
        "schema_version": schema_version,
        "event_type": event_type,
        "occurred_at": context.now,
        "recorded_at": context.now,
        "ingested_at": context.now,
        "clock_authority": context.clock_address,
        "temporal_context": f"{context.clock_address}:{context.tick}",
        "ordering_basis": ordering_basis,
        "logical_order_ref": f"{context.clock_address}:{context.tick}",
        "actor_ref": _BLUE,
        "producer_ref": _PRODUCER,
        "provenance_refs": provenance_refs,
        "evidence_refs": [],
        "marking_definition_refs": [],
        "object_marking_refs": [],
        "markings": [],
        "granular_markings": {},
        "authorization_scope": "runtime",
    }


def _shared_state_record(
    shared_id: str,
    action_id: str,
    context: _TurnRecordContext,
) -> dict[str, object]:
    """Build the aggregate turn's portable shared-state record."""

    record = _event_envelope(
        shared_id,
        schema_name="participant-shared-state",
        schema_version="participant-shared-state/v1",
        event_type="shared_state_changed",
        context=context,
        ordering_basis=_SERIALIZED_ORDER,
        provenance_refs=[_CONTROL_TURN_LEDGER],
    )
    record.update(
        state_address=shared_id,
        state_scope="aggregate-turn",
        state_kind="turn-commit",
        revision=action_id,
        predecessor_revision_refs=[],
        conflict_policy="serialize",
        provenance="backend-realized",
        accesses=[],
    )
    return record


def _time_context_record(
    context_id: str,
    context: _TurnRecordContext,
) -> dict[str, object]:
    """Build the bounded logical-time context for one aggregate turn."""

    record = _event_envelope(
        context_id,
        schema_name="participant-time-management-context",
        schema_version="participant-time-management-context/v1",
        event_type="time_context_recorded",
        context=context,
        ordering_basis="logical_clock",
        provenance_refs=[_CONTROL_TURN_LEDGER, "loss-evaluation-seed-unbound"],
    )
    record.update(
        context_id=context_id,
        mode="backend_serialized",
        claim_strength="bounded",
        basis=_SERIALIZED_ORDER,
        clock_ref=context.clock_address,
        advance_by=1,
        rollback_event_refs=[],
        backend_serialized=True,
    )
    return record


def _joint_action_record(
    joint_id: str,
    context_id: str,
    realized: list[str],
    context: _TurnRecordContext,
) -> dict[str, object]:
    """Build the serialized three-participant joint-action record."""

    record = _event_envelope(
        joint_id,
        schema_name="participant-joint-action",
        schema_version="participant-joint-action/v1",
        event_type="joint_action_committed",
        context=context,
        ordering_basis=_SERIALIZED_ORDER,
        provenance_refs=[_CONTROL_TURN_LEDGER],
    )
    record.update(
        joint_action_set_id=joint_id,
        member_event_refs=realized,
        access_sets=[
            {
                "member_event_ref": member,
                "shared_state_read_refs": [],
                "shared_state_write_refs": [],
                "exclusive_resource_refs": [],
                "visibility_effect_refs": [],
                "evidence_stream_refs": [],
            }
            for member in realized
        ],
        conflict_class="none",
        conflict_policy="serialize",
        isolation_guarantee="serializable",
        atomicity_scope="coordination_interval",
        realized_order=realized,
        time_management_context_ref=context_id,
        participant_observation_refs=[],
        rollback_event_refs=[],
        unsupported_disclosure=False,
        exact_concurrency_claim=False,
    )
    return record


def _clock_tick(snapshot: RuntimeSnapshot, clock_address: str) -> int | None:
    """Read one exact logical-clock tick from portable state."""

    state = snapshot.time_model_state
    if state is None or clock_address not in state.clocks:
        return None
    return cast(int, state.clocks[clock_address].coordinate.tick)


def _valid_turn(value: object, external_action: str) -> bool:
    """Validate the exact bounded three-participant native projection."""

    if type(value) is not _NativeTurnResult:
        return False
    valid_occurrences = len(value.occurrences) == 3 and all(
        occurrence.participant_address == address
        and occurrence.action_contract_address.startswith("participant.action-contract.")
        for occurrence, address in zip(value.occurrences, _ORDER, strict=True)
    )
    return (
        type(value.external_action_succeeded) is bool
        and type(value.source_terminal) is bool
        and valid_occurrences
        and value.occurrences[0].action_contract_address == external_action
    )


__all__ = ["CyborgParticipantRuntime"]
