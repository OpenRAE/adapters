"""CAGE-2 logical-run admission over published RAES orchestration contracts."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, datetime

from raes_contracts.contracts import (  # type: ignore[import-untyped]
    ExperimentEpisodeControlModel,
    ExperimentRedVariantSelectionModel,
    WorkflowExecutionStateModel,
)
from raes_contracts.diagnostics import Diagnostic  # type: ignore[import-untyped]
from raes_contracts.planning import (  # type: ignore[import-untyped]
    ChangeAction,
    OrchestrationOp,
    OrchestrationPlan,
    RuntimeDomain,
)
from raes_contracts.runtime_state import (  # type: ignore[import-untyped]
    ApplyResult,
    RuntimeSnapshot,
    SnapshotEntry,
)

from .provisioner import CyborgProvisioner

_VARIANTS = frozenset({"b-line", "meander", "sleep"})


def _now_iso() -> str:
    """Return one portable UTC timestamp."""

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class _ExecutionPolicy(object):
    """Closed execution controls admitted from one workflow declaration."""

    workflow_address: str
    clock_address: str
    max_steps: int
    red_variant: str


class _AdmissionError(Exception):
    """Bounded internal failure used while parsing orchestration input."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class CyborgExecutionControl(object):
    """Small shared policy latch; portable progress remains in the snapshot."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._policy: _ExecutionPolicy | None = None
        self._source_terminal = False

    def activate(self, policy: _ExecutionPolicy) -> None:
        """Activate one admitted execution policy."""

        with self._lock:
            self._policy = policy
            self._source_terminal = False

    def clear(self) -> None:
        """Clear all active execution controls."""

        with self._lock:
            self._policy = None
            self._source_terminal = False

    def policy(self) -> _ExecutionPolicy | None:
        """Return the currently admitted policy, if any."""

        with self._lock:
            return self._policy

    def is_source_terminal(self) -> bool:
        """Report whether the native source declared a terminal state."""

        with self._lock:
            return self._source_terminal

    def mark_source_terminal(self) -> None:
        """Latch a source-native terminal signal."""

        with self._lock:
            self._source_terminal = True

    def reset_terminal(self) -> None:
        """Reopen the admitted policy after one coordinated native reset."""

        with self._lock:
            self._source_terminal = False


class CyborgOrchestrator(object):
    """Admit one CAGE-2 workflow and bind its declared control policy."""

    def __init__(self, provisioner: CyborgProvisioner, control: CyborgExecutionControl) -> None:
        self._provisioner = provisioner
        self._control = control
        self._results: dict[str, dict[str, object]] = {}
        self._history: dict[str, list[dict[str, object]]] = {}

    def start(self, plan: OrchestrationPlan, snapshot: RuntimeSnapshot) -> ApplyResult:
        """Serialize policy admission, native construction, and portable commit."""

        with self._provisioner.execution_transaction():
            return self._start_transaction(plan, snapshot)

    def _start_transaction(
        self,
        plan: OrchestrationPlan,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        """Start an admitted session while the shared transaction lock is held."""

        admitted = self._admit(plan, snapshot)
        if isinstance(admitted, ApplyResult):
            return admitted
        operation, policy = admitted

        now = _now_iso()
        entries = dict(snapshot.entries)
        entries[operation.address] = SnapshotEntry(
            address=operation.address,
            domain=RuntimeDomain.ORCHESTRATION,
            resource_type="workflow",
            payload=dict(operation.payload),
            ordering_dependencies=operation.ordering_dependencies,
            refresh_dependencies=operation.refresh_dependencies,
            status="running",
        )
        result = WorkflowExecutionStateModel(
            workflow_status="running",
            run_id=f"{operation.address}-run",
            started_at=now,
            updated_at=now,
            terminal_reason=None,
            compensation_status="not_required",
            compensation_started_at=None,
            compensation_updated_at=None,
            compensation_failures=[],
            steps={},
        ).model_dump(mode="json")
        event: dict[str, object] = {
            "event_type": "workflow_started",
            "timestamp": now,
            "step_name": None,
            "branch_name": None,
            "join_step": None,
            "outcome": None,
            "details": {},
        }
        results = dict(snapshot.orchestration_results)
        history = {key: list(value) for key, value in snapshot.orchestration_history.items()}
        results[operation.address] = result
        history[operation.address] = [event]
        next_snapshot = snapshot.with_entries(
            entries,
            orchestration_results=results,
            orchestration_history=history,
        )
        if not self._provisioner.configure_execution(policy.red_variant):
            return _failure(
                snapshot,
                "cyborg-backend.orchestration.session-construction-failed",
                "The selected CybORG execution session could not be constructed.",
            )
        self._results = results
        self._history = history
        self._control.activate(policy)
        return ApplyResult(
            success=True,
            snapshot=next_snapshot,
            changed_addresses=[operation.address],
        )

    @staticmethod
    def _admit(
        plan: object,
        snapshot: RuntimeSnapshot,
    ) -> tuple[OrchestrationOp, _ExecutionPolicy] | ApplyResult:
        """Return a closed policy or one bounded admission failure."""

        try:
            operation = _workflow_operation(plan)
            clock_address = _clock_address(snapshot)
            policy = _execution_policy(operation, clock_address)
        except _AdmissionError as error:
            admitted: tuple[OrchestrationOp, _ExecutionPolicy] | ApplyResult = _failure(
                snapshot, error.code, error.message
            )
        else:
            admitted = operation, policy
        return admitted

    def status(self) -> dict[str, object]:
        """Return a bounded status summary without native state."""

        return {"running": self._control.policy() is not None, "results": len(self._results)}

    def results(self) -> dict[str, dict[str, object]]:
        """Return defensive copies of portable workflow results."""

        return {key: dict(value) for key, value in self._results.items()}

    def history(self) -> dict[str, list[dict[str, object]]]:
        """Return defensive copies of portable workflow history."""

        return {key: list(value) for key, value in self._history.items()}

    def mark_completed(self, snapshot: RuntimeSnapshot, reason: str) -> RuntimeSnapshot:
        """Commit the workflow terminal envelope after its final logical turn."""

        policy = self._control.policy()
        if policy is None:
            return snapshot
        now = _now_iso()
        results = dict(snapshot.orchestration_results)
        history = {key: list(value) for key, value in snapshot.orchestration_history.items()}
        current = dict(results.get(policy.workflow_address, {}))
        current.update(
            workflow_status="completed",
            updated_at=now,
            terminal_reason=reason,
        )
        results[policy.workflow_address] = current
        history.setdefault(policy.workflow_address, []).append(
            {
                "event_type": "workflow_completed",
                "timestamp": now,
                "step_name": None,
                "branch_name": None,
                "join_step": None,
                "outcome": "succeeded",
                "details": {"terminal_reason": reason},
            }
        )
        self._results = results
        self._history = history
        return snapshot.with_entries(
            dict(snapshot.entries),
            orchestration_results=results,
            orchestration_history=history,
        )

    def mark_reset(self, snapshot: RuntimeSnapshot) -> RuntimeSnapshot:
        """Reopen the admitted workflow for a new logical-time segment."""

        policy = self._control.policy()
        if policy is None:
            return snapshot
        now = _now_iso()
        results = dict(snapshot.orchestration_results)
        history = {key: list(value) for key, value in snapshot.orchestration_history.items()}
        current = dict(results.get(policy.workflow_address, {}))
        current.update(workflow_status="running", updated_at=now, terminal_reason=None)
        results[policy.workflow_address] = current
        history.setdefault(policy.workflow_address, []).append(
            {
                "event_type": "workflow_started",
                "timestamp": now,
                "step_name": None,
                "branch_name": None,
                "join_step": None,
                "outcome": None,
                "details": {"reset": True},
            }
        )
        self._results = results
        self._history = history
        return snapshot.with_entries(
            dict(snapshot.entries),
            orchestration_results=results,
            orchestration_history=history,
        )

    def stop(self, snapshot: RuntimeSnapshot) -> ApplyResult:
        """Serialize portable stop with every other session transition."""

        with self._provisioner.execution_transaction():
            return self._stop_transaction(snapshot)

    def _stop_transaction(self, snapshot: RuntimeSnapshot) -> ApplyResult:
        """Clear portable orchestration state while holding the session lock."""

        removed = [
            key
            for key, value in snapshot.entries.items()
            if value.domain == RuntimeDomain.ORCHESTRATION
        ]
        entries = {key: value for key, value in snapshot.entries.items() if key not in removed}
        self._control.clear()
        self._results = {}
        self._history = {}
        return ApplyResult(
            success=True,
            snapshot=snapshot.with_entries(
                entries, orchestration_results={}, orchestration_history={}
            ),
            changed_addresses=removed,
        )


def _workflow_operation(plan: object) -> OrchestrationOp:
    """Extract the sole supported workflow operation."""

    if not isinstance(plan, OrchestrationPlan):
        raise _AdmissionError(
            "cyborg-backend.orchestration.invalid-plan",
            "A RAES orchestration plan is required.",
        )
    workflows = [
        operation
        for operation in plan.operations
        if operation.action != ChangeAction.DELETE and operation.resource_type == "workflow"
    ]
    if len(workflows) != 1 or len(plan.resources) != 1:
        raise _AdmissionError(
            "cyborg-backend.orchestration.invalid-plan",
            "Exactly one CAGE-2 workflow is required.",
        )
    return workflows[0]


def _clock_address(snapshot: RuntimeSnapshot) -> str:
    """Return the sole initialized logical clock address."""

    state = snapshot.time_model_state
    if state is None or len(state.clocks) != 1:
        raise _AdmissionError(
            "cyborg-backend.orchestration.time-unavailable",
            "Exactly one initialized logical clock is required.",
        )
    return str(next(iter(state.clocks)))


def _execution_policy(operation: OrchestrationOp, clock_address: str) -> _ExecutionPolicy:
    """Parse the closed CAGE-2 controls from the workflow payload."""

    try:
        episode = ExperimentEpisodeControlModel.model_validate(operation.payload["episode_control"])
        variant = ExperimentRedVariantSelectionModel.model_validate(
            operation.payload["red_variant_selection"]
        )
        variant_id = str(variant.variant_id)
        if episode.turn_order != "scenario-defined" or episode.max_steps is None:
            raise ValueError
        if variant_id not in _VARIANTS:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise _AdmissionError(
            "cyborg-backend.orchestration.invalid-control",
            "The workflow control declaration is not supported by CAGE-2.",
        ) from None
    return _ExecutionPolicy(
        workflow_address=operation.address,
        clock_address=clock_address,
        max_steps=episode.max_steps,
        red_variant=variant_id,
    )


def _failure(snapshot: RuntimeSnapshot, code: str, message: str) -> ApplyResult:
    """Build one bounded orchestration diagnostic."""

    return ApplyResult(
        success=False,
        snapshot=snapshot,
        diagnostics=[
            Diagnostic(code=code, domain="orchestration", address="cyborg-cage2", message=message)
        ],
    )


__all__ = ["CyborgExecutionControl", "CyborgOrchestrator"]
