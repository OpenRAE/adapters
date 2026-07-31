"""Portable participant execution for one aggregate CAGE-2 logical turn."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import NamedTuple, cast

from raes_backend_protocols.participant_runtime_base import (  # type: ignore[import-untyped]
    BaseParticipantRuntime,
)
from raes_contracts.contracts import (  # type: ignore[import-untyped]
    ParticipantActionResultModel,
    ParticipantBehaviorHistoryEventModel,
)
from raes_contracts.diagnostics import Diagnostic  # type: ignore[import-untyped]
from raes_contracts.participant_binding import (  # type: ignore[import-untyped]
    ParticipantActionAdmissionRequest,
    ParticipantActionApplyResult,
    ParticipantNativeActionExecution,
)
from raes_contracts.participant_episode import (  # type: ignore[import-untyped]
    ParticipantEpisodeResetRequest,
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
            checkpoint = (
                deepcopy(self._results),
                deepcopy(self._history),
                deepcopy(self._episode_counter),
            )
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
        checkpoint: tuple[
            dict[str, dict[str, object]],
            dict[str, list[dict[str, object]]],
            dict[str, int],
        ],
    ) -> ApplyResult:
        """Commit one staged portable reset and then one native reset."""

        try:
            working, changed, diagnostics = self._portable_reset_candidate(
                requests, snapshot, policy
            )
        except _ResetRejected as rejected:
            self._results, self._history, self._episode_counter = checkpoint
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
            self._results, self._history, self._episode_counter = checkpoint
            result = self._reset_failure(snapshot)
        else:
            if not self._provisioner.reset_execution():
                self._results, self._history, self._episode_counter = checkpoint
                result = self._reset_failure(snapshot)
            else:
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
            try:
                result = BaseParticipantRuntime.admit_action(self, request, snapshot)
            except Exception:
                if self._provisioner.execution_generation() != generation:
                    self._provisioner.quarantine_execution()
                result = self._commit_failure(snapshot)
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
                        result = self._commit_failure(snapshot)
            return result

    @staticmethod
    def _commit_failure(snapshot: RuntimeSnapshot) -> ParticipantActionApplyResult:
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
            projected = self._native_turn(request)
            next_snapshot = self._advance_portable_turn(
                snapshot,
                request=request,
                episode_id=episode_id,
                policy=policy,
                projected=projected,
                tick=tick,
            )
        except _TurnRejected as rejected:
            if rejected.quarantine:
                self._provisioner.quarantine_execution()
            execution = self._reject_action(snapshot, rejected.reason)
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
        if policy is None or self._control.is_source_terminal():
            raise _TurnRejected("run-not-active")
        tick = _clock_tick(snapshot, policy.clock_address)
        if tick is None or tick >= policy.max_steps:
            raise _TurnRejected("trial-complete")
        if not self._provisioner.execution_available():
            raise _TurnRejected("session-unavailable")
        return policy, tick

    def _native_turn(self, request: ParticipantActionAdmissionRequest) -> _NativeTurnResult:
        """Execute and validate the bounded native turn projection."""

        try:
            projected = self._provisioner.execute_turn(request.validated_selection)
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
    ) -> RuntimeSnapshot:
        """Advance logical time and stage the complete portable turn."""

        advanced = self._time_runtime.advance(policy.clock_address, 1, 0, snapshot)
        if not advanced.success:
            raise _TurnRejected("clock-failed", quarantine=True)
        next_snapshot = self._portable_turn(
            advanced.snapshot,
            request=request,
            episode_id=episode_id,
            projected=projected,
            tick=tick + 1,
            clock_address=policy.clock_address,
        )
        if projected.source_terminal:
            self._control.mark_source_terminal()
            next_snapshot = self._orchestrator.mark_completed(next_snapshot, "source-terminal")
        elif tick + 1 == policy.max_steps:
            next_snapshot = self._orchestrator.mark_completed(next_snapshot, "logical-step-limit")
        return next_snapshot

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

        action_result = ParticipantActionResultModel(
            status="succeeded" if projected.external_action_succeeded else "failed",
            participant_address=request.participant_address,
            episode_id=episode_id,
            action_instance_id=request.action_instance_id,
            action_contract_address=request.action_contract_address,
            observation_point=request.observation_boundary_address,
            preconditions=[],
            effects=[],
            failure_class=None if projected.external_action_succeeded else "unknown",
            observations=[],
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

    @staticmethod
    def _reject_action(snapshot: RuntimeSnapshot, reason: str) -> ParticipantNativeActionExecution:
        """Build one bounded action rejection."""

        diagnostic = Diagnostic(
            code=f"cyborg-backend.action.{reason}",
            domain="participant",
            address=_BLUE,
            message="The action could not be admitted to the CAGE-2 execution session.",
        )
        return ParticipantNativeActionExecution(
            apply_result=ApplyResult(success=False, snapshot=snapshot, diagnostics=[diagnostic])
        )

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
