"""Portable orchestration state for PrimAITE episodes.

The orchestrator owns only the workflow lifecycle. It never advances the source
(the participant runtime owns the single aggregate ``env.step``), and it never
fabricates orchestration operations: an empty compiled-SDL orchestration is a
valid no-op.
"""

from __future__ import annotations

from datetime import UTC, datetime

from raes_contracts.contracts import (  # type: ignore[import-untyped]
    WorkflowExecutionStateModel,
    WorkflowHistoryEventModel,
    WorkflowStepStateModel,
)
from raes_contracts.diagnostics import Diagnostic  # type: ignore[import-untyped]
from raes_contracts.planning import (  # type: ignore[import-untyped]
    ChangeAction,
    OrchestrationPlan,
    RuntimeDomain,
)
from raes_contracts.runtime_state import (  # type: ignore[import-untyped]
    ApplyResult,
    RuntimeSnapshot,
    SnapshotEntry,
)
from raes_contracts.workflow import (  # type: ignore[import-untyped]
    WorkflowCompensationStatus,
    WorkflowHistoryEventType,
    WorkflowStatus,
    WorkflowStepLifecycle,
)

from ._diagnostics import diagnostic_address

_SUPPORTED_RESOURCE_TYPES = frozenset({"event", "workflow"})
_RUN_ID_STEM = "primaite-episode"


def _now_iso() -> str:
    """Return a portable UTC timestamp."""

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class PrimaiteOrchestrator(object):
    """Own workflow lifecycle only; the participant runtime owns source steps."""

    def __init__(self) -> None:
        self._running = False
        self._startup_order: list[str] = []
        self._results: dict[str, dict[str, object]] = {}
        self._history: dict[str, list[dict[str, object]]] = {}

    def start(
        self,
        plan: OrchestrationPlan,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        unsupported = [
            operation
            for operation in plan.operations
            if operation.resource_type not in _SUPPORTED_RESOURCE_TYPES
        ]
        if unsupported:
            operation = unsupported[0]
            return ApplyResult(
                success=False,
                snapshot=snapshot,
                diagnostics=[
                    Diagnostic(
                        code="primaite.orchestration.unsupported-resource",
                        domain="orchestration",
                        address=diagnostic_address(operation.address),
                        message=(
                            "The PrimAITE orchestrator does not support this "
                            "orchestration resource type."
                        ),
                    )
                ],
            )
        mutating_operations = [
            operation for operation in plan.operations if operation.action != ChangeAction.UNCHANGED
        ]
        if not mutating_operations:
            return ApplyResult(success=True, snapshot=snapshot)

        entries = dict(snapshot.entries)
        results = dict(snapshot.orchestration_results)
        history = {
            address: list(events) for address, events in snapshot.orchestration_history.items()
        }
        changed_addresses: list[str] = []
        now = _now_iso()
        for operation in plan.operations:
            if operation.action == ChangeAction.UNCHANGED:
                continue
            if operation.action == ChangeAction.DELETE:
                entries.pop(operation.address, None)
                results.pop(operation.address, None)
                history.pop(operation.address, None)
                changed_addresses.append(operation.address)
                continue
            entries[operation.address] = SnapshotEntry(
                address=operation.address,
                domain=RuntimeDomain.ORCHESTRATION,
                resource_type=operation.resource_type,
                payload=operation.payload,
                ordering_dependencies=operation.ordering_dependencies,
                refresh_dependencies=operation.refresh_dependencies,
                status="queued",
            )
            if operation.resource_type == "workflow":
                results[operation.address] = self._workflow_result(
                    operation.payload, now
                ).model_dump(mode="json")
                history[operation.address] = [
                    self._workflow_started_event(operation.payload, now).model_dump(mode="json")
                ]
            changed_addresses.append(operation.address)

        self._running = bool(results or changed_addresses)
        self._startup_order = list(plan.startup_order)
        self._results = results
        self._history = history
        return ApplyResult(
            success=True,
            snapshot=snapshot.with_entries(
                entries,
                orchestration_results=results,
                orchestration_history=history,
            ),
            changed_addresses=changed_addresses,
        )

    @staticmethod
    def _workflow_result(
        payload: dict[str, object],
        now: str,
    ) -> WorkflowExecutionStateModel:
        result_contract = payload.get("result_contract", {})
        if not isinstance(result_contract, dict):
            result_contract = {}
        observable_steps_raw = result_contract.get("observable_steps", {})
        observable_steps = {
            step_name: WorkflowStepStateModel(
                lifecycle=WorkflowStepLifecycle.PENDING.value,
                outcome=None,
                attempts=0,
            )
            for step_name, step_payload in (
                observable_steps_raw.items() if isinstance(observable_steps_raw, dict) else []
            )
            if isinstance(step_payload, dict)
        }
        return WorkflowExecutionStateModel(
            workflow_status=WorkflowStatus.RUNNING.value,
            run_id=f"{payload.get('name', _RUN_ID_STEM)}-run",
            started_at=now,
            updated_at=now,
            terminal_reason=None,
            compensation_status=WorkflowCompensationStatus.NOT_REQUIRED.value,
            compensation_started_at=None,
            compensation_updated_at=None,
            compensation_failures=[],
            steps=observable_steps,
        )

    @staticmethod
    def _workflow_started_event(
        payload: dict[str, object],
        now: str,
    ) -> WorkflowHistoryEventModel:
        execution_contract = payload.get("execution_contract", {})
        start_step = (
            execution_contract.get("start_step") if isinstance(execution_contract, dict) else None
        )
        return WorkflowHistoryEventModel(
            event_type=WorkflowHistoryEventType.WORKFLOW_STARTED.value,
            timestamp=now,
            step_name=start_step if isinstance(start_step, str) else None,
            branch_name=None,
            join_step=None,
            outcome=None,
            details={},
        )

    def status(self) -> dict[str, object]:
        return {
            "running": self._running,
            "startup_order": list(self._startup_order),
            "results": len(self._results),
        }

    def results(self) -> dict[str, dict[str, object]]:
        return {address: dict(result) for address, result in self._results.items()}

    def history(self) -> dict[str, list[dict[str, object]]]:
        return {
            address: [dict(event) for event in events] for address, events in self._history.items()
        }

    def stop(self, snapshot: RuntimeSnapshot) -> ApplyResult:
        entries = {
            address: entry
            for address, entry in snapshot.entries.items()
            if entry.domain != RuntimeDomain.ORCHESTRATION
        }
        removed = [
            address
            for address, entry in snapshot.entries.items()
            if entry.domain == RuntimeDomain.ORCHESTRATION
        ]
        self._running = False
        self._startup_order = []
        self._results = {}
        self._history = {}
        return ApplyResult(
            success=True,
            snapshot=snapshot.with_entries(
                entries,
                orchestration_results={},
                orchestration_history={},
            ),
            changed_addresses=removed,
        )


__all__ = ["PrimaiteOrchestrator"]
