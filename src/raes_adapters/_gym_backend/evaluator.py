"""Neutral evaluator-only projection of sanitized gym-backend run facts."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from raes_contracts.contracts import (  # type: ignore[import-untyped]
    EvaluationHistoryEventModel,
    EvaluationResultStateModel,
    ExperimentCaptureSpecModel,
    ExperimentDerivedMeasureModel,
    ExperimentEvidenceRecordModel,
    PropositionLossDisclosureModel,
    PropositionTruthResultModel,
)
from raes_contracts.diagnostics import Diagnostic  # type: ignore[import-untyped]
from raes_contracts.evaluation import (  # type: ignore[import-untyped]
    EvaluationHistoryEventType,
    EvaluationResultContract,
    EvaluationResultStatus,
)
from raes_contracts.planning import (  # type: ignore[import-untyped]
    ChangeAction,
    EvaluationOp,
    EvaluationPlan,
    RuntimeDomain,
)
from raes_contracts.runtime_state import (  # type: ignore[import-untyped]
    ApplyResult,
    RuntimeSnapshot,
    SnapshotEntry,
)

from raes_adapters._diagnostics import diagnostic_address
from raes_adapters._experiment_evidence import (
    EvaluatorEvidenceConfig,
    EvaluatorSummary,
    build_capture_spec,
    build_evidence_and_measure,
    scoped_id,
)

_SUPPORTED_RESOURCE_TYPES = frozenset(
    {"condition-binding", "proposition", "assertion", "objective"}
)


class _DriverEvaluationFacts(Protocol):
    """The sanitized evaluator facts a driver returns."""

    @property
    def step_count(self) -> int: ...

    @property
    def cumulative_reward(self) -> float: ...

    @property
    def execution_ref(self) -> str: ...

    @property
    def projection_ref(self) -> str: ...


class _EvaluatorDriver(Protocol):
    """The driver surface the evaluator reads (never advances)."""

    def evaluate(self) -> _DriverEvaluationFacts: ...


def _now_iso() -> str:
    """Return a portable UTC timestamp."""

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _summary(facts: _DriverEvaluationFacts) -> EvaluatorSummary:
    """Project driver evaluation facts into the neutral summary."""

    return EvaluatorSummary(
        step_count=facts.step_count,
        cumulative_reward=facts.cumulative_reward,
        execution_ref=facts.execution_ref,
        projection_ref=facts.projection_ref,
    )


class GymEvaluator(object):
    """Read evaluator-owned facts without advancing the source environment."""

    def __init__(
        self,
        driver: _EvaluatorDriver,
        name: str,
        config: EvaluatorEvidenceConfig,
        source_revision: Callable[[], str],
    ) -> None:
        self._driver = driver
        self._name = name
        self._config = config
        self._source_revision = source_revision
        self._running = False
        self._startup_order: list[str] = []
        self._results: dict[str, dict[str, object]] = {}
        self._history: dict[str, list[dict[str, object]]] = {}
        self._capture_spec: ExperimentCaptureSpecModel | None = None
        self._evidence_records: tuple[ExperimentEvidenceRecordModel, ...] = ()
        self._derived_measures: tuple[ExperimentDerivedMeasureModel, ...] = ()

    def start(self, plan: EvaluationPlan, snapshot: RuntimeSnapshot) -> ApplyResult:
        """Apply an evaluation plan and project evaluator-owned source facts."""

        terminal_result = self._terminal_result(plan, snapshot)
        if terminal_result is not None:
            return terminal_result
        summary, projection_failure = self._evaluation_projection(plan, snapshot)
        if projection_failure is not None:
            return projection_failure
        return self._apply_projection(plan, snapshot, summary)

    def _terminal_result(
        self, plan: EvaluationPlan, snapshot: RuntimeSnapshot
    ) -> ApplyResult | None:
        """Return an unsupported failure or unchanged-plan success when terminal."""

        unsupported = self._unsupported_result(plan, snapshot)
        if unsupported is not None:
            return unsupported
        if not self._has_mutations(plan):
            return ApplyResult(success=True, snapshot=snapshot)
        return None

    def _unsupported_result(
        self, plan: EvaluationPlan, snapshot: RuntimeSnapshot
    ) -> ApplyResult | None:
        """Return a portable failure for the first unsupported resource."""

        operation = next(
            (
                item
                for item in plan.operations
                if item.resource_type not in _SUPPORTED_RESOURCE_TYPES
            ),
            None,
        )
        if operation is None:
            return None
        return ApplyResult(
            success=False,
            snapshot=snapshot,
            diagnostics=[
                Diagnostic(
                    code=f"{self._name}.evaluation.unsupported-resource",
                    domain="evaluation",
                    address=diagnostic_address(operation.address, fallback=f"/{self._name}"),
                    message=(
                        "The selected profile does not support this evaluation resource type."
                    ),
                )
            ],
        )

    @staticmethod
    def _has_mutations(plan: EvaluationPlan) -> bool:
        """Return whether a plan changes evaluator-owned state."""

        return any(operation.action != ChangeAction.UNCHANGED for operation in plan.operations)

    @staticmethod
    def _needs_projection(plan: EvaluationPlan) -> bool:
        """Return whether source facts are required by this plan."""

        return any(
            operation.action in {ChangeAction.CREATE, ChangeAction.UPDATE}
            and operation.resource_type in {"condition-binding", "objective"}
            for operation in plan.operations
        )

    def _evaluation_projection(
        self, plan: EvaluationPlan, snapshot: RuntimeSnapshot
    ) -> tuple[EvaluatorSummary, ApplyResult | None]:
        """Read and record one evaluator projection when the plan requires it."""

        if not self._needs_projection(plan):
            self._clear_evidence()
            return self._empty_summary(), None
        try:
            facts = self._driver.evaluate()
        except Exception:
            return self._empty_summary(), self._projection_failure(snapshot)
        captured_at = _now_iso()
        summary = _summary(facts)
        self._capture_spec = build_capture_spec(self._config, summary, captured_at)
        evidence_record, derived_measure = build_evidence_and_measure(
            self._config,
            summary,
            captured_at,
            self._source_revision(),
        )
        self._evidence_records = (evidence_record,)
        self._derived_measures = (derived_measure,)
        return summary, None

    def _clear_evidence(self) -> None:
        """Clear evaluator evidence when no source projection is needed."""

        self._capture_spec = None
        self._evidence_records = ()
        self._derived_measures = ()

    def _empty_summary(self) -> EvaluatorSummary:
        """Return the non-source placeholder used for metadata-only changes."""

        return EvaluatorSummary(
            step_count=0,
            cumulative_reward=0.0,
            execution_ref=f"{self._name}.no-execution",
            projection_ref=f"{self._name}.no-projection",
        )

    def _projection_failure(self, snapshot: RuntimeSnapshot) -> ApplyResult:
        """Return a bounded source-projection failure."""

        return ApplyResult(
            success=False,
            snapshot=snapshot,
            diagnostics=[
                Diagnostic(
                    code=f"{self._name}.evaluation.projection-failed",
                    domain="evaluation",
                    address=f"/evaluation/{self._name}/selected-profile",
                    message=("The evaluator could not project the selected run facts."),
                )
            ],
        )

    def _apply_projection(
        self, plan: EvaluationPlan, snapshot: RuntimeSnapshot, summary: EvaluatorSummary
    ) -> ApplyResult:
        """Apply normalized evaluator state and truth projections."""

        needs_projection = self._needs_projection(plan)
        evidence_ref = (
            scoped_id(self._config.evidence_ref, summary.projection_ref)
            if needs_projection
            else None
        )
        entries, results, history, truth_results, changed = self._apply_operations(
            plan, snapshot, summary, evidence_ref
        )
        self._apply_truth_results(plan, truth_results, evidence_ref, needs_projection)
        self._running = bool(plan.resources or plan.operations)
        self._startup_order = list(plan.startup_order)
        self._results = results
        self._history = history
        return ApplyResult(
            success=True,
            snapshot=snapshot.with_entries(
                entries,
                evaluation_results=results,
                evaluation_history=history,
                proposition_truth_results=truth_results,
            ),
            changed_addresses=changed,
        )

    def _apply_operations(
        self,
        plan: EvaluationPlan,
        snapshot: RuntimeSnapshot,
        summary: EvaluatorSummary,
        evidence_ref: str | None,
    ) -> tuple[
        dict[str, SnapshotEntry],
        dict[str, dict[str, object]],
        dict[str, list[dict[str, object]]],
        dict[str, dict[str, object]],
        list[str],
    ]:
        """Apply create, update, and delete operations to copied state maps."""

        entries = dict(snapshot.entries)
        results = dict(snapshot.evaluation_results)
        history = {address: list(events) for address, events in snapshot.evaluation_history.items()}
        truth_results = dict(snapshot.proposition_truth_results)
        changed: list[str] = []
        now = _now_iso()
        for operation in plan.operations:
            if operation.action == ChangeAction.UNCHANGED:
                continue
            if operation.action == ChangeAction.DELETE:
                self._delete_operation(operation, entries, results, history, truth_results)
            else:
                self._upsert_operation(
                    operation, entries, results, history, summary, now, evidence_ref
                )
            changed.append(operation.address)
        return entries, results, history, truth_results, changed

    @staticmethod
    def _delete_operation(
        operation: EvaluationOp,
        entries: dict[str, SnapshotEntry],
        results: dict[str, dict[str, object]],
        history: dict[str, list[dict[str, object]]],
        truth_results: dict[str, dict[str, object]],
    ) -> None:
        """Delete one evaluator resource and all owned result state."""

        entries.pop(operation.address, None)
        results.pop(operation.address, None)
        history.pop(operation.address, None)
        truth_results.pop(operation.address, None)

    def _upsert_operation(
        self,
        operation: EvaluationOp,
        entries: dict[str, SnapshotEntry],
        results: dict[str, dict[str, object]],
        history: dict[str, list[dict[str, object]]],
        summary: EvaluatorSummary,
        now: str,
        evidence_ref: str | None,
    ) -> None:
        """Create or update one evaluator resource and typed result state."""

        is_truth_resource = operation.resource_type in {"proposition", "assertion"}
        entries[operation.address] = SnapshotEntry(
            address=operation.address,
            domain=RuntimeDomain.EVALUATION,
            resource_type=operation.resource_type,
            payload=operation.payload,
            ordering_dependencies=operation.ordering_dependencies,
            refresh_dependencies=operation.refresh_dependencies,
            status="admitted" if is_truth_resource else "evaluating",
        )
        if is_truth_resource:
            return
        result_state = self._result_state(operation, summary, now, evidence_ref)
        results[operation.address] = result_state.model_dump(mode="json")
        history[operation.address] = [
            event.model_dump(mode="json") for event in self._history_events(result_state, now)
        ]

    @staticmethod
    def _apply_truth_results(
        plan: EvaluationPlan,
        truth_results: dict[str, dict[str, object]],
        evidence_ref: str | None,
        needs_projection: bool,
    ) -> None:
        """Project admitted assertions as bounded unknown truth outcomes."""

        proposition_bases = {
            operation.address: operation.payload.get("evaluation_basis")
            for operation in plan.operations
            if operation.resource_type == "proposition"
        }
        for operation in plan.operations:
            truth_result = GymEvaluator._truth_result(
                operation, proposition_bases, evidence_ref, needs_projection
            )
            if truth_result is not None:
                truth_results[operation.address] = truth_result.model_dump(mode="json")

    @staticmethod
    def _truth_result(
        operation: EvaluationOp,
        proposition_bases: dict[str, object],
        evidence_ref: str | None,
        needs_projection: bool,
    ) -> PropositionTruthResultModel | None:
        """Build one bounded truth result when an assertion is well formed."""

        if (
            operation.action in {ChangeAction.DELETE, ChangeAction.UNCHANGED}
            or operation.resource_type != "assertion"
        ):
            return None
        proposition_address = operation.payload.get("proposition_address")
        polarity = operation.payload.get("polarity")
        evaluation_basis = proposition_bases.get(str(proposition_address))
        valid = (
            isinstance(proposition_address, str)
            and polarity in {"positive", "negative"}
            and evaluation_basis in {"declared_state", "observed_state"}
        )
        if not valid:
            return None
        return PropositionTruthResultModel(
            result_id=f"truth.{operation.address}",
            proposition_address=proposition_address,
            assertion_address=operation.address,
            assertion_polarity=polarity,
            proposition_outcome="unknown",
            assertion_outcome="unknown",
            evaluation_basis=evaluation_basis,
            indeterminacy_reason=("lossy_evidence" if needs_projection else "missing_evidence"),
            evidence_refs=[evidence_ref] if evidence_ref is not None else [],
            loss_disclosures=[
                PropositionLossDisclosureModel(kind="lossy", within_admissible_bound=True)
            ],
        )

    def _result_state(
        self,
        operation: EvaluationOp,
        summary: EvaluatorSummary,
        now: str,
        evidence_ref: str | None,
    ) -> EvaluationResultStateModel:
        result_contract = operation.payload.get("result_contract", {})
        if not isinstance(result_contract, dict):
            raise RuntimeError("compiled evaluation result contract is invalid")
        contract = EvaluationResultContract.from_mapping(result_contract)
        reports_score = contract.supports_score and not contract.supports_passed
        if evidence_ref is None:
            raise RuntimeError("evaluation evidence identity is unavailable")
        return EvaluationResultStateModel(
            resource_type=contract.resource_type,
            run_id=summary.execution_ref,
            status=(
                EvaluationResultStatus.READY.value
                if reports_score
                else EvaluationResultStatus.RUNNING.value
            ),
            observed_at=now,
            updated_at=now,
            passed=None,
            score=summary.cumulative_reward if reports_score else None,
            max_score=contract.fixed_max_score if reports_score else None,
            detail=(
                f"{self._name} evaluator projection after {summary.step_count} source transitions."
            ),
            evidence_refs=[evidence_ref],
        )

    @staticmethod
    def _history_events(
        result_state: EvaluationResultStateModel,
        now: str,
    ) -> list[EvaluationHistoryEventModel]:
        terminal = result_state.status == EvaluationResultStatus.READY.value
        return [
            EvaluationHistoryEventModel(
                event_type=EvaluationHistoryEventType.EVALUATION_STARTED.value,
                timestamp=now,
                status=EvaluationResultStatus.RUNNING.value,
                passed=None,
                score=None,
                max_score=None,
                detail=None,
                evidence_refs=[],
                details={},
            ),
            EvaluationHistoryEventModel(
                event_type=(
                    EvaluationHistoryEventType.EVALUATION_READY.value
                    if terminal
                    else EvaluationHistoryEventType.EVALUATION_UPDATED.value
                ),
                timestamp=now,
                status=result_state.status,
                passed=result_state.passed,
                score=result_state.score,
                max_score=result_state.max_score,
                detail=result_state.detail,
                evidence_refs=result_state.evidence_refs,
                details={},
            ),
        ]

    def status(self) -> dict[str, object]:
        return {
            "running": self._running,
            "startup_order": list(self._startup_order),
            "results": len(self._results),
            "capture_spec": self._capture_spec is not None,
            "evidence_records": len(self._evidence_records),
            "derived_measures": len(self._derived_measures),
        }

    def results(self) -> dict[str, dict[str, object]]:
        return {address: dict(result) for address, result in self._results.items()}

    def history(self) -> dict[str, list[dict[str, object]]]:
        return {
            address: [dict(event) for event in events] for address, events in self._history.items()
        }

    def evidence_records(self) -> tuple[ExperimentEvidenceRecordModel, ...]:
        """Return typed, redacted evaluator evidence for the selected run."""

        return self._evidence_records

    def capture_spec(self) -> ExperimentCaptureSpecModel | None:
        """Return the typed capture boundary used for evaluator evidence."""

        return self._capture_spec

    def derived_measures(self) -> tuple[ExperimentDerivedMeasureModel, ...]:
        """Return typed measures whose limits prevent replay overclaiming."""

        return self._derived_measures

    def stop(self, snapshot: RuntimeSnapshot) -> ApplyResult:
        entries = {
            address: entry
            for address, entry in snapshot.entries.items()
            if entry.domain != RuntimeDomain.EVALUATION
        }
        removed = [
            address
            for address, entry in snapshot.entries.items()
            if entry.domain == RuntimeDomain.EVALUATION
        ]
        self._running = False
        self._startup_order = []
        self._results = {}
        self._history = {}
        self._capture_spec = None
        self._evidence_records = ()
        self._derived_measures = ()
        return ApplyResult(
            success=True,
            snapshot=snapshot.with_entries(
                entries,
                evaluation_results={},
                evaluation_history={},
                proposition_truth_results={},
            ),
            changed_addresses=removed,
        )


__all__ = ["GymEvaluator"]
