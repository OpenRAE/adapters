"""Evaluator-only projection of sanitized CyberBattleSim run facts."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from raes_contracts.contracts import (  # type: ignore[import-untyped]
    EvaluationHistoryEventModel,
    EvaluationResultStateModel,
    ExperimentCaptureRequirementModel,
    ExperimentCaptureSpecModel,
    ExperimentCaptureSpecReferenceModel,
    ExperimentCaptureWindowModel,
    ExperimentChecksumModel,
    ExperimentDerivedMeasureMethodModel,
    ExperimentDerivedMeasureModel,
    ExperimentEvidenceRecordModel,
    ExperimentEvidenceRecordReferenceModel,
    ExperimentMeasurementChannelReferenceModel,
    ExperimentReferenceModel,
    ExperimentTaskReferenceModel,
    ExperimentValidityNoteModel,
    PropositionLossDisclosureModel,
    PropositionTruthResultModel,
)
from raes_contracts.contracts.experiment_capture import (  # type: ignore[import-untyped]
    ExperimentRawEvidenceContentModel,
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

from raes_adapters.cyberbattlesim import load_qualification
from raes_adapters.cyberbattlesim.scenario_ledger import CYBERBATTLE_CHAIN

from .driver import CyberBattleSimDriverProtocol, DriverEvaluation

EVALUATION_EVIDENCE_REF = "evidence-record.cyberbattlesim.evaluator-summary"

_EVIDENCE_RECORD_VERSION = "1.0.0"
_CAPTURE_SPEC_ID = "cyberbattlesim-evaluator-capture"
_CAPTURE_REQUIREMENT_ID = "cyberbattlesim-evaluator-summary"
_CAPTURE_WINDOW_ID = "cyberbattlesim-selected-episode"
_TASK_ID = CYBERBATTLE_CHAIN.task_id
_SUPPORTED_RESOURCE_TYPES = frozenset(
    {"condition-binding", "proposition", "assertion", "objective"}
)


def _now_iso() -> str:
    """Return a portable UTC timestamp."""

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _scoped_id(base: str, projection_ref: str) -> str:
    """Scope an artifact identity to one evaluator projection."""

    if not projection_ref:
        raise RuntimeError("CyberBattleSim evaluation projection identity is unavailable")
    identity_digest = hashlib.sha256(projection_ref.encode("utf-8")).hexdigest()
    return f"{base}.{identity_digest}"


class CyberBattleSimEvaluator(object):  # noqa: UP004
    """Read evaluator-owned facts without advancing the source environment."""

    def __init__(self, driver: CyberBattleSimDriverProtocol) -> None:
        self._driver = driver
        self._running = False
        self._startup_order: list[str] = []
        self._results: dict[str, dict[str, object]] = {}
        self._history: dict[str, list[dict[str, object]]] = {}
        self._capture_spec: ExperimentCaptureSpecModel | None = None
        self._evidence_records: tuple[ExperimentEvidenceRecordModel, ...] = ()
        self._derived_measures: tuple[ExperimentDerivedMeasureModel, ...] = ()

    def start(
        self,
        plan: EvaluationPlan,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult:
        """Apply an evaluation plan and project evaluator-owned source facts."""

        terminal_result = self._terminal_result(plan, snapshot)
        if terminal_result is not None:
            return terminal_result
        evaluation, projection_failure = self._evaluation_projection(plan, snapshot)
        if projection_failure is not None:
            return projection_failure
        return self._apply_projection(plan, snapshot, evaluation)

    @staticmethod
    def _terminal_result(
        plan: EvaluationPlan,
        snapshot: RuntimeSnapshot,
    ) -> ApplyResult | None:
        """Return an unsupported failure or unchanged-plan success when terminal."""

        unsupported = CyberBattleSimEvaluator._unsupported_result(plan, snapshot)
        if unsupported is not None:
            return unsupported
        if not CyberBattleSimEvaluator._has_mutations(plan):
            return ApplyResult(success=True, snapshot=snapshot)
        return None

    @staticmethod
    def _unsupported_result(
        plan: EvaluationPlan,
        snapshot: RuntimeSnapshot,
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
                    code="cyberbattlesim.evaluation.unsupported-resource",
                    domain="evaluation",
                    address=operation.address,
                    message=(
                        "The selected CyberBattleSim profile does not support "
                        "this evaluation resource type."
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
        self,
        plan: EvaluationPlan,
        snapshot: RuntimeSnapshot,
    ) -> tuple[DriverEvaluation, ApplyResult | None]:
        """Read and record one evaluator projection when the plan requires it."""

        if not self._needs_projection(plan):
            self._clear_evidence()
            return self._empty_evaluation(), None
        try:
            evaluation = self._driver.evaluate()
        except Exception:
            return self._empty_evaluation(), self._projection_failure(snapshot)
        captured_at = _now_iso()
        self._capture_spec = self._capture_specification(evaluation, captured_at)
        evidence_record, derived_measure = self._experiment_evidence(
            evaluation,
            captured_at,
        )
        self._evidence_records = (evidence_record,)
        self._derived_measures = (derived_measure,)
        return evaluation, None

    def _clear_evidence(self) -> None:
        """Clear evaluator evidence when no source projection is needed."""

        self._capture_spec = None
        self._evidence_records = ()
        self._derived_measures = ()

    @staticmethod
    def _empty_evaluation() -> DriverEvaluation:
        """Return the non-source placeholder used for metadata-only changes."""

        return DriverEvaluation(
            execution_ref="cyberbattlesim.no-execution",
            projection_ref="cyberbattlesim.no-projection",
            step_count=0,
            cumulative_reward=0.0,
            terminated=False,
            truncated=False,
            terminal_cause=None,
        )

    @staticmethod
    def _projection_failure(snapshot: RuntimeSnapshot) -> ApplyResult:
        """Return a bounded source-projection failure."""

        return ApplyResult(
            success=False,
            snapshot=snapshot,
            diagnostics=[
                Diagnostic(
                    code="cyberbattlesim.evaluation.projection-failed",
                    domain="evaluation",
                    address="evaluation.cyberbattlesim.selected-profile",
                    message=(
                        "The CyberBattleSim evaluator could not project the selected run facts."
                    ),
                )
            ],
        )

    def _apply_projection(
        self,
        plan: EvaluationPlan,
        snapshot: RuntimeSnapshot,
        evaluation: DriverEvaluation,
    ) -> ApplyResult:
        """Apply normalized evaluator state and truth projections."""

        needs_projection = self._needs_projection(plan)
        evidence_ref = (
            _scoped_id(EVALUATION_EVIDENCE_REF, evaluation.projection_ref)
            if needs_projection
            else None
        )
        entries, results, history, truth_results, changed = self._apply_operations(
            plan,
            snapshot,
            evaluation,
            evidence_ref,
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
        evaluation: DriverEvaluation,
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
                    operation,
                    entries,
                    results,
                    history,
                    evaluation,
                    now,
                    evidence_ref,
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
        evaluation: DriverEvaluation,
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
        result_state = self._result_state(operation, evaluation, now, evidence_ref)
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
            truth_result = CyberBattleSimEvaluator._truth_result(
                operation,
                proposition_bases,
                evidence_ref,
                needs_projection,
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
                PropositionLossDisclosureModel(
                    kind="lossy",
                    within_admissible_bound=True,
                )
            ],
        )

    @staticmethod
    def _result_state(
        operation: EvaluationOp,
        evaluation: DriverEvaluation,
        now: str,
        evidence_ref: str | None,
    ) -> EvaluationResultStateModel:
        result_contract = operation.payload.get("result_contract", {})
        if not isinstance(result_contract, dict):
            raise RuntimeError("compiled evaluation result contract is invalid")
        contract = EvaluationResultContract.from_mapping(result_contract)
        reports_score = contract.supports_score and not contract.supports_passed
        if evidence_ref is None:
            raise RuntimeError("CyberBattleSim evaluation evidence identity is unavailable")
        return EvaluationResultStateModel(
            resource_type=contract.resource_type,
            run_id=evaluation.execution_ref,
            status=(
                EvaluationResultStatus.READY.value
                if reports_score
                else EvaluationResultStatus.RUNNING.value
            ),
            observed_at=now,
            updated_at=now,
            passed=None,
            score=evaluation.cumulative_reward if reports_score else None,
            max_score=contract.fixed_max_score if reports_score else None,
            detail=(
                "CyberBattleSim evaluator projection after "
                f"{evaluation.step_count} source transitions."
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

    @staticmethod
    def _experiment_evidence(
        evaluation: DriverEvaluation,
        now: str,
    ) -> tuple[ExperimentEvidenceRecordModel, ExperimentDerivedMeasureModel]:
        """Build projection-scoped evidence and its derived reward measure."""

        source_revision = CyberBattleSimEvaluator._source_revision()
        evidence_record_id = _scoped_id(
            EVALUATION_EVIDENCE_REF,
            evaluation.projection_ref,
        )
        evidence_record = CyberBattleSimEvaluator._evidence_record(
            evaluation,
            now,
            source_revision,
            evidence_record_id,
        )
        derived_measure = CyberBattleSimEvaluator._derived_measure(
            evaluation,
            now,
            evidence_record_id,
        )
        return evidence_record, derived_measure

    @staticmethod
    def _source_revision() -> str:
        """Read the selected source revision used in evidence provenance."""

        qualification = load_qualification()
        source = qualification.get("source")
        source_revision = source.get("commit") if isinstance(source, dict) else None
        if not isinstance(source_revision, str):
            raise RuntimeError("selected simulator qualification is invalid")
        return source_revision

    @staticmethod
    def _evidence_record(
        evaluation: DriverEvaluation,
        now: str,
        source_revision: str,
        evidence_record_id: str,
    ) -> ExperimentEvidenceRecordModel:
        """Build one redacted, checksummed evaluator evidence record."""

        capture_spec_id = _scoped_id(_CAPTURE_SPEC_ID, evaluation.projection_ref)
        capture_requirement_id = _scoped_id(
            _CAPTURE_REQUIREMENT_ID,
            evaluation.projection_ref,
        )
        capture_window_id = _scoped_id(_CAPTURE_WINDOW_ID, evaluation.projection_ref)
        payload_summary = (
            "Sanitized evaluator summary: "
            f"{evaluation.step_count} source transitions and cumulative "
            f"reward {evaluation.cumulative_reward:.17g}."
        )
        return ExperimentEvidenceRecordModel(
            schema_version="experiment-evidence-record/v1",
            evidence_record_id=evidence_record_id,
            record_version=_EVIDENCE_RECORD_VERSION,
            capture_spec_ref=ExperimentCaptureSpecReferenceModel(
                ref_kind="capture-spec",
                ref_id=capture_spec_id,
                ref_version="1.0.0",
            ),
            capture_requirement_ref=capture_requirement_id,
            run_ref=ExperimentReferenceModel(
                ref_kind="run",
                ref_id=evaluation.execution_ref,
                ref_version="1.0.0",
            ),
            task_ref=ExperimentTaskReferenceModel(
                ref_kind="task",
                ref_id=_TASK_ID,
                ref_version="1.0.0",
            ),
            source_refs=[
                ExperimentReferenceModel(
                    ref_kind="protocol",
                    ref_id="cyberbattlesim-chain-public",
                    ref_version=source_revision,
                )
            ],
            evidence_kind="telemetry",
            captured_at=now,
            capture_window_ref=capture_window_id,
            raw_content=ExperimentRawEvidenceContentModel(
                content_uri=(f"urn:raes:{evidence_record_id}:payload-summary"),
                content_checksum=ExperimentChecksumModel(
                    algorithm="sha256",
                    value=hashlib.sha256(payload_summary.encode("utf-8")).hexdigest(),
                ),
                payload_summary=payload_summary,
                loss_disclosure=(
                    "Source-native observations, action availability, credentials, "
                    "reward components, hidden state, and info are withheld."
                ),
            ),
            sensitivity="redacted",
            redaction_state="redacted",
            provenance_refs=[
                ExperimentReferenceModel(
                    ref_kind="other",
                    ref_id="qualification.cyberbattlesim.selected-source",
                    ref_version=source_revision,
                )
            ],
        )

    @staticmethod
    def _derived_measure(
        evaluation: DriverEvaluation,
        now: str,
        evidence_record_id: str,
    ) -> ExperimentDerivedMeasureModel:
        """Build the bounded cumulative-reward derived measure."""

        derived_measure_id = _scoped_id(
            "measure.cyberbattlesim.cumulative-attacker-reward",
            evaluation.projection_ref,
        )
        return ExperimentDerivedMeasureModel(
            schema_version="experiment-derived-measure/v1",
            derived_measure_id=derived_measure_id,
            measure_version="1.0.0",
            measure_kind="score",
            metric_ref=ExperimentReferenceModel(
                ref_kind="metric-definition",
                ref_id="cumulative_attacker_reward",
                ref_version="1.0.0",
            ),
            method=ExperimentDerivedMeasureMethodModel(
                method_id="cyberbattlesim-cumulative-reward",
                method_version="1.0.0",
                name="Source cumulative attacker reward",
                description=(
                    "Report the sanitized cumulative reward maintained by the "
                    "serialized source driver."
                ),
            ),
            source_evidence_refs=[
                ExperimentEvidenceRecordReferenceModel(
                    ref_kind="evidence-record",
                    ref_id=evidence_record_id,
                    ref_version=_EVIDENCE_RECORD_VERSION,
                )
            ],
            generated_at=now,
            value_status="reported",
            value=evaluation.cumulative_reward,
            uncertainty="No statistical uncertainty is estimated from this single run.",
            limitations=[
                (
                    "Single-run cumulative source reward; no deterministic replay "
                    "or outcome equivalence is claimed."
                ),
                (
                    "Python-global and NumPy-global random streams remain unbound "
                    "by the selected reset protocol."
                ),
            ],
            provenance_refs=[
                ExperimentReferenceModel(
                    ref_kind="task",
                    ref_id=_TASK_ID,
                    ref_version="1.0.0",
                )
            ],
        )

    @staticmethod
    def _capture_specification(
        evaluation: DriverEvaluation,
        now: str,
    ) -> ExperimentCaptureSpecModel:
        """Build the projection-scoped evaluator capture specification."""

        capture_spec_id = _scoped_id(_CAPTURE_SPEC_ID, evaluation.projection_ref)
        capture_requirement_id = _scoped_id(
            _CAPTURE_REQUIREMENT_ID,
            evaluation.projection_ref,
        )
        capture_window_id = _scoped_id(_CAPTURE_WINDOW_ID, evaluation.projection_ref)
        return ExperimentCaptureSpecModel(
            schema_version="experiment-capture-spec/v1",
            capture_spec_id=capture_spec_id,
            spec_version="1.0.0",
            title="CyberBattleSim evaluator summary capture",
            description=(
                "Capture the sanitized evaluator-owned summary used to derive "
                "the selected cumulative-reward measure."
            ),
            scope_refs=[
                ExperimentReferenceModel(
                    ref_kind="run",
                    ref_id=evaluation.execution_ref,
                    ref_version="1.0.0",
                ),
                ExperimentReferenceModel(
                    ref_kind="task",
                    ref_id=_TASK_ID,
                    ref_version="1.0.0",
                ),
            ],
            capture_windows=[
                ExperimentCaptureWindowModel(
                    window_id=capture_window_id,
                    window_kind="event",
                    starts_at=now,
                    ends_at=now,
                    description=(
                        "One read-only evaluator projection after the current "
                        "serialized source transition."
                    ),
                )
            ],
            capture_requirements={
                capture_requirement_id: ExperimentCaptureRequirementModel(
                    requirement_id=capture_requirement_id,
                    title="Sanitized evaluator summary",
                    capture_kind="telemetry",
                    capture_scope="run",
                    channel_ref=ExperimentMeasurementChannelReferenceModel(
                        ref_kind="measurement-channel",
                        ref_id="cyberbattlesim-evaluation-history",
                        ref_version="1.0.0",
                    ),
                    window_refs=[capture_window_id],
                    expected_media_types=["application/json"],
                    sensitivity="redacted",
                    redaction_policy="redaction.cyberbattlesim.evaluator-summary",
                    integrity_requirements=["sha256"],
                    retention_policy="run-lifetime",
                    loss_disclosure_required=True,
                    notes=[
                        "Native observations, masks, credentials, reward components, "
                        "hidden state, and info remain driver-private."
                    ],
                )
            },
            validity_notes=[
                ExperimentValidityNoteModel(
                    category="reproducibility",
                    note=(
                        "The capture attests one observed summary; it does not "
                        "establish deterministic replay."
                    ),
                    mitigation=("Record applied and unbound stochastic streams with the run."),
                )
            ],
        )


__all__ = [
    "CyberBattleSimEvaluator",
    "EVALUATION_EVIDENCE_REF",
]
