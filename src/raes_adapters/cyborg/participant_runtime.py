"""Portable participant execution for one aggregate CAGE-2 logical turn."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import cast

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
from .orchestrator import CyborgExecutionControl, CyborgOrchestrator
from .provisioner import CyborgProvisioner

_BLUE = "participant.behavior.blue"
_GREEN = "participant.behavior.green"
_RED = "participant.behavior.red"
_ORDER = (_BLUE, _GREEN, _RED)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


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
            return self.reset(
                ParticipantEpisodeResetRequest(participant_address=_BLUE),
                snapshot,
            )
        checkpoint = (
            deepcopy(self._results),
            deepcopy(self._history),
            deepcopy(self._episode_counter),
        )
        policy = self._control.policy()
        if policy is None:
            return self.reset(ParticipantEpisodeResetRequest(participant_address=_BLUE), snapshot)
        try:
            timed = self._time_runtime.reset(policy.clock_address, False, snapshot)
        except Exception:
            return self._reset_failure(snapshot)
        if not timed.success:
            return self._reset_failure(snapshot)
        working = timed.snapshot
        changed: list[str] = []
        diagnostics: list[Diagnostic] = []
        try:
            for request in requests:
                result = BaseParticipantRuntime.reset(self, request, working)
                diagnostics.extend(result.diagnostics)
                if not result.success:
                    self._results, self._history, self._episode_counter = checkpoint
                    return ApplyResult(success=False, snapshot=snapshot, diagnostics=diagnostics)
                working = result.snapshot
                changed.extend(result.changed_addresses)
            working = self._orchestrator.mark_reset(working)
            invalid = [
                *participant_runtime_state_contract_diagnostics(working),
                *participant_runtime_history_transition_diagnostics(snapshot, working),
            ]
        except Exception:
            self._results, self._history, self._episode_counter = checkpoint
            return self._reset_failure(snapshot)
        if invalid:
            self._results, self._history, self._episode_counter = checkpoint
            return self._reset_failure(snapshot)
        if not self._provisioner.reset_execution():
            self._results, self._history, self._episode_counter = checkpoint
            return self._reset_failure(snapshot)
        self._control.reset_terminal()
        return ApplyResult(
            success=True,
            snapshot=working,
            diagnostics=diagnostics,
            changed_addresses=list(dict.fromkeys([*changed, policy.clock_address])),
        )

    @staticmethod
    def _reset_failure(snapshot: RuntimeSnapshot) -> ApplyResult:
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
                return self._commit_failure(snapshot)
            if self._provisioner.execution_generation() != generation:
                if not result.success:
                    self._provisioner.quarantine_execution()
                    return result
                diagnostics = [
                    *participant_runtime_state_contract_diagnostics(result.snapshot),
                    *participant_runtime_history_transition_diagnostics(snapshot, result.snapshot),
                ]
                if diagnostics:
                    self._provisioner.quarantine_execution()
                    return self._commit_failure(snapshot)
            return result

    @staticmethod
    def _commit_failure(snapshot: RuntimeSnapshot) -> ParticipantActionApplyResult:
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
        policy = self._control.policy()
        if request.participant_address != _BLUE or request.validated_selection is None:
            return self._reject_action(snapshot, "invalid-selection")
        if not self._provisioner.selection_targets_are_realized(request.validated_selection):
            return self._reject_action(snapshot, "unsupported-binding")
        if policy is None or self._control.is_source_terminal():
            return self._reject_action(snapshot, "run-not-active")
        tick = _clock_tick(snapshot, policy.clock_address)
        if tick is None or tick >= policy.max_steps:
            return self._reject_action(snapshot, "trial-complete")
        if not self._provisioner.execution_available():
            return self._reject_action(snapshot, "session-unavailable")

        try:
            projected = self._provisioner.execute_turn(request.validated_selection)
        except RuntimeError:
            return self._reject_action(snapshot, "turn-failed")
        if not _valid_turn(projected, request.action_contract_address):
            self._provisioner.quarantine_execution()
            return self._reject_action(snapshot, "projection-failed")
        assert isinstance(projected, _NativeTurnResult)

        advanced = self._time_runtime.advance(policy.clock_address, 1, 0, snapshot)
        if not advanced.success:
            self._provisioner.quarantine_execution()
            return self._reject_action(snapshot, "clock-failed")
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
                snapshot=next_snapshot,
                changed_addresses=[request.participant_address, policy.clock_address],
            ),
            action_result=action_result,
        )

    @staticmethod
    def _reject_action(snapshot: RuntimeSnapshot, reason: str) -> ParticipantNativeActionExecution:
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
        now = _now_iso()
        action_id = request.action_instance_id
        joint_id = f"cyborg.joint-action:{action_id}"
        shared_id = f"cyborg.shared-state:{action_id}"
        context_id = f"cyborg.time-context:{action_id}"
        realized = [action_id, f"{action_id}:green", f"{action_id}:red"]

        behavior = {
            key: list(value) for key, value in snapshot.participant_behavior_history.items()
        }
        for index, occurrence in enumerate(projected.occurrences[1:], start=1):
            internal_id = realized[index]
            state = snapshot.participant_episode_results[occurrence.participant_address]
            event = ParticipantBehaviorHistoryEventModel(
                event_type="action_attempted",
                timestamp=now,
                participant_address=occurrence.participant_address,
                episode_id=str(state["episode_id"]),
                action_instance_id=internal_id,
                action_contract_address=occurrence.action_contract_address,
                joint_action_set_id=joint_id,
                realized_order=index,
                shared_state_refs=[shared_id],
            )
            behavior.setdefault(occurrence.participant_address, []).append(
                event.model_dump(mode="json", exclude_none=True)
            )

        shared = dict(snapshot.shared_state_records)
        shared[shared_id] = {
            "event_id": shared_id,
            "schema_name": "participant-shared-state",
            "schema_version": "participant-shared-state/v1",
            "event_type": "shared_state_changed",
            "occurred_at": now,
            "recorded_at": now,
            "ingested_at": now,
            "clock_authority": clock_address,
            "temporal_context": f"{clock_address}:{tick}",
            "ordering_basis": "serialized_backend_order",
            "logical_order_ref": f"{clock_address}:{tick}",
            "actor_ref": _BLUE,
            "producer_ref": "cyborg-cage2-participant-runtime",
            "provenance_refs": ["source-ledger:control-turn-order"],
            "evidence_refs": [],
            "marking_definition_refs": [],
            "object_marking_refs": [],
            "markings": [],
            "granular_markings": {},
            "authorization_scope": "runtime",
            "state_address": shared_id,
            "state_scope": "aggregate-turn",
            "state_kind": "turn-commit",
            "revision": action_id,
            "predecessor_revision_refs": [],
            "conflict_policy": "serialize",
            "provenance": "backend-realized",
            "accesses": [],
        }
        contexts = dict(snapshot.time_management_contexts)
        contexts[context_id] = {
            "event_id": context_id,
            "schema_name": "participant-time-management-context",
            "schema_version": "participant-time-management-context/v1",
            "event_type": "time_context_recorded",
            "occurred_at": now,
            "recorded_at": now,
            "ingested_at": now,
            "clock_authority": clock_address,
            "temporal_context": f"{clock_address}:{tick}",
            "ordering_basis": "logical_clock",
            "logical_order_ref": f"{clock_address}:{tick}",
            "actor_ref": _BLUE,
            "producer_ref": "cyborg-cage2-participant-runtime",
            "provenance_refs": [
                "source-ledger:control-turn-order",
                "loss-evaluation-seed-unbound",
            ],
            "evidence_refs": [],
            "marking_definition_refs": [],
            "object_marking_refs": [],
            "markings": [],
            "granular_markings": {},
            "authorization_scope": "runtime",
            "context_id": context_id,
            "mode": "backend_serialized",
            "claim_strength": "bounded",
            "basis": "serialized_backend_order",
            "clock_ref": clock_address,
            "advance_by": 1,
            "rollback_event_refs": [],
            "backend_serialized": True,
        }
        joints = dict(snapshot.joint_action_records)
        joints[joint_id] = {
            "event_id": joint_id,
            "schema_name": "participant-joint-action",
            "schema_version": "participant-joint-action/v1",
            "event_type": "joint_action_committed",
            "occurred_at": now,
            "recorded_at": now,
            "ingested_at": now,
            "clock_authority": clock_address,
            "temporal_context": f"{clock_address}:{tick}",
            "ordering_basis": "serialized_backend_order",
            "logical_order_ref": f"{clock_address}:{tick}",
            "actor_ref": _BLUE,
            "producer_ref": "cyborg-cage2-participant-runtime",
            "provenance_refs": ["source-ledger:control-turn-order"],
            "evidence_refs": [],
            "marking_definition_refs": [],
            "object_marking_refs": [],
            "markings": [],
            "granular_markings": {},
            "authorization_scope": "runtime",
            "joint_action_set_id": joint_id,
            "member_event_refs": realized,
            "access_sets": [
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
            "conflict_class": "none",
            "conflict_policy": "serialize",
            "isolation_guarantee": "serializable",
            "atomicity_scope": "coordination_interval",
            "realized_order": realized,
            "time_management_context_ref": context_id,
            "participant_observation_refs": [],
            "rollback_event_refs": [],
            "unsupported_disclosure": False,
            "exact_concurrency_claim": False,
        }
        return snapshot.with_entries(
            dict(snapshot.entries),
            participant_behavior_history=behavior,
            shared_state_records=shared,
            joint_action_records=joints,
            time_management_contexts=contexts,
        )


def _clock_tick(snapshot: RuntimeSnapshot, clock_address: str) -> int | None:
    state = snapshot.time_model_state
    if state is None or clock_address not in state.clocks:
        return None
    return cast(int, state.clocks[clock_address].coordinate.tick)


def _valid_turn(value: object, external_action: str) -> bool:
    if type(value) is not _NativeTurnResult:
        return False
    if type(value.external_action_succeeded) is not bool or type(value.source_terminal) is not bool:
        return False
    if len(value.occurrences) != 3:
        return False
    for occurrence, address in zip(value.occurrences, _ORDER, strict=True):
        if occurrence.participant_address != address:
            return False
        if not occurrence.action_contract_address.startswith("participant.action-contract."):
            return False
    return value.occurrences[0].action_contract_address == external_action


__all__ = ["CyborgParticipantRuntime"]
