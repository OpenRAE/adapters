"""Evaluator-only projection of committed, sanitized CybORG reward facts."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from operator import eq, ge, gt, le, lt, ne
from typing import NamedTuple, cast

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
    ExperimentValidityNoteModel,
    PropositionLossDisclosureModel,
    PropositionProbeBindingModel,
    PropositionTemporalContextModel,
    PropositionTruthResultModel,
)
from raes_contracts.contracts.experiment_capture import (  # type: ignore[import-untyped]
    ExperimentRawEvidenceContentModel,
)
from raes_contracts.diagnostics import Diagnostic  # type: ignore[import-untyped]
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

from ._diagnostics import diagnostic_address
from .driver import _NativeEvaluationTurn, _NativeRewardComponent
from .manifest import CYBORG_PROFILE_ID
from .provisioner import CyborgProvisioner
from .qualification import load_qualification

_BLUE = "participant.behavior.blue"
_SUPPORTED_RESOURCE_TYPES = frozenset(
    {"condition-binding", "proposition", "assertion", "objective"}
)
_SUPPORTED_COMPONENTS = frozenset({"confidentiality", "availability", "action-cost"})
_OPERATORS = {"eq": eq, "ne": ne, "lt": lt, "lte": le, "gt": gt, "gte": ge}
_COMPILED_OPERATOR_NAMES = {
    "equals": "eq",
    "not_equals": "ne",
    "less_than": "lt",
    "less_than_or_equal": "lte",
    "greater_than": "gt",
    "greater_than_or_equal": "gte",
}
_REWARD_COMPONENT_SOURCE_ROW = "source-ledger:reward-components"
_EVIDENCE_REQUIREMENT_BINDINGS: dict[str, tuple[str, str | None]] = {
    _REWARD_COMPONENT_SOURCE_ROW: (_REWARD_COMPONENT_SOURCE_ROW, None),
    "operational-service-state": (_REWARD_COMPONENT_SOURCE_ROW, _BLUE),
}
_CAPTURE_SPEC_ID = "capture-spec.cyborg-cage2.reward-projection"
_CAPTURE_REQUIREMENT_ID = "capture-requirement.cyborg-cage2.reward-fact"
_CAPTURE_WINDOW_ID = "capture-window.cyborg-cage2.committed-turns"
_RECORD_VERSION = "1.0.0"
_PROBE_DIGEST = "sha256:" + hashlib.sha256(b"cyborg-cage2-reward-probe-v1").hexdigest()
_EvaluatorBase = object


def _now_iso() -> str:
    """Return one UTC timestamp in the contract's canonical spelling."""

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _identity(*parts: object) -> str:
    """Derive a stable identifier from a closed set of portable values."""

    encoded = json.dumps(parts, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _blue_component_values_and_refs(
    facts: tuple[_NativeEvaluationTurn, ...],
    records: tuple[ExperimentEvidenceRecordModel, ...],
) -> tuple[
    dict[str, float],
    dict[str, list[ExperimentEvidenceRecordReferenceModel]],
]:
    """Accumulate allowlisted Blue components and their committed evidence refs."""

    values: dict[str, float] = dict.fromkeys(_SUPPORTED_COMPONENTS, 0.0)
    refs: dict[str, list[ExperimentEvidenceRecordReferenceModel]] = {
        name: [] for name in _SUPPORTED_COMPONENTS
    }
    record_ids = {record.evidence_record_id for record in records}
    for turn in facts:
        for component in turn.components:
            if component.participant_address != _BLUE:
                continue
            if component.component not in _SUPPORTED_COMPONENTS:
                continue
            values[component.component] += component.value
            record_id = _identity(
                turn.run_id,
                turn.action_instance_id,
                turn.logical_step,
                component.participant_address,
                component.target_address,
                component.component,
            )
            evidence_id = "evidence-record.cyborg-cage2." + record_id
            if evidence_id in record_ids:
                refs[component.component].append(
                    ExperimentEvidenceRecordReferenceModel(
                        ref_kind="evidence-record",
                        ref_id=evidence_id,
                        ref_version=_RECORD_VERSION,
                    )
                )
    return values, refs


def _blue_component_measure(
    facts: tuple[_NativeEvaluationTurn, ...],
    component_name: str,
    value: float,
    refs: list[ExperimentEvidenceRecordReferenceModel],
    now: str,
) -> ExperimentDerivedMeasureModel:
    """Build one allowlisted cumulative Blue component measure."""

    identity = _identity(facts[-1].run_id, facts[-1].episode_id, len(facts))
    return ExperimentDerivedMeasureModel(
        schema_version="experiment-derived-measure/v1",
        derived_measure_id=f"measure.cyborg-cage2.cumulative-blue-{component_name}.{identity}",
        measure_version="1.0.0",
        measure_kind="metric",
        metric_ref=ExperimentReferenceModel(
            ref_kind="metric-definition",
            ref_id=f"cage2-cumulative-blue-{component_name}-reward",
            ref_version="1.0.0",
        ),
        method=ExperimentDerivedMeasureMethodModel(
            method_id=f"cyborg-cage2-sum-blue-{component_name}-rewards",
            method_version="1.0.0",
            name=f"Cumulative committed Blue {component_name} reward",
            description="Sum the named committed per-step Blue component in logical step order.",
        ),
        source_evidence_refs=refs,
        generated_at=now,
        value_status="reported",
        value=value,
        uncertainty="No uncertainty interval is inferred from one source run.",
        limitations=[
            "This component is not a conformance result, objective outcome, "
            "or replication-equivalence claim."
        ],
        provenance_refs=[
            ExperimentReferenceModel(ref_kind="run", ref_id=facts[-1].run_id, ref_version="1.0.0")
        ],
    )


def _blue_component_measures(
    facts: tuple[_NativeEvaluationTurn, ...],
    records: tuple[ExperimentEvidenceRecordModel, ...],
    now: str,
) -> list[ExperimentDerivedMeasureModel]:
    """Build measures only for Blue components with retained source evidence."""

    values, component_refs = _blue_component_values_and_refs(facts, records)
    return [
        _blue_component_measure(facts, name, values[name], component_refs[name], now)
        for name in sorted(_SUPPORTED_COMPONENTS)
        if component_refs[name]
    ]


def _blue_score_refs(
    records: tuple[ExperimentEvidenceRecordModel, ...],
) -> list[ExperimentEvidenceRecordReferenceModel]:
    """Return evidence references for committed per-step Blue rewards."""

    return [
        ExperimentEvidenceRecordReferenceModel(
            ref_kind="evidence-record",
            ref_id=record.evidence_record_id,
            ref_version=_RECORD_VERSION,
        )
        for record in records
        if f"participant={_BLUE};" in (record.raw_content.payload_summary or "")
        and "meaning=per-step-reward;" in (record.raw_content.payload_summary or "")
    ]


def _blue_score_measure(
    facts: tuple[_NativeEvaluationTurn, ...],
    records: tuple[ExperimentEvidenceRecordModel, ...],
    now: str,
) -> ExperimentDerivedMeasureModel:
    """Build the cumulative committed Blue score measure."""

    identity = _identity(facts[-1].run_id, facts[-1].episode_id, len(facts))
    return ExperimentDerivedMeasureModel(
        schema_version="experiment-derived-measure/v1",
        derived_measure_id=f"measure.cyborg-cage2.cumulative-blue-score.{identity}",
        measure_version="1.0.0",
        measure_kind="score",
        metric_ref=ExperimentReferenceModel(
            ref_kind="metric-definition",
            ref_id="cage2-cumulative-blue-reward",
            ref_version="1.0.0",
        ),
        method=ExperimentDerivedMeasureMethodModel(
            method_id="cyborg-cage2-sum-committed-blue-rewards",
            method_version="1.0.0",
            name="Cumulative committed Blue reward",
            description="Sum exact per-step Blue rewards in committed logical-step order.",
        ),
        source_evidence_refs=_blue_score_refs(records),
        generated_at=now,
        value_status="reported",
        value=sum(dict(turn.rewards)[_BLUE] for turn in facts),
        uncertainty="No uncertainty interval is inferred from one source run.",
        limitations=[
            "This score is not a conformance result, objective outcome, "
            "scenario-correctness claim, or replication-equivalence claim."
        ],
        provenance_refs=[
            ExperimentReferenceModel(ref_kind="run", ref_id=facts[-1].run_id, ref_version="1.0.0"),
            ExperimentReferenceModel(
                ref_kind="other", ref_id=facts[-1].episode_id, ref_version="1.0.0"
            ),
        ],
    )


class _PredicateBinding(NamedTuple):
    """Supported proposition fields resolved from one compiled operation."""

    property_name: str
    operator_name: str
    expected: float
    subject: str
    source_row: str
    participant_address: str | None


class _EvaluationState(NamedTuple):
    """Mutable projection maps reconciled as one evaluator state."""

    entries: dict[str, SnapshotEntry]
    results: dict[str, dict[str, object]]
    history: dict[str, list[dict[str, object]]]
    truth: dict[str, dict[str, object]]
    assertion_outcomes: dict[str, str]


class CyborgEvaluator(_EvaluatorBase):
    """Project committed backend facts without advancing or inspecting CybORG."""

    def __init__(self, provisioner: CyborgProvisioner) -> None:
        self._provisioner = provisioner
        self._running = False
        self._startup_order: list[str] = []
        self._results: dict[str, dict[str, object]] = {}
        self._history: dict[str, list[dict[str, object]]] = {}
        self._capture_spec: ExperimentCaptureSpecModel | None = None
        self._evidence_records: tuple[ExperimentEvidenceRecordModel, ...] = ()
        self._derived_measures: tuple[ExperimentDerivedMeasureModel, ...] = ()

    def start(self, plan: EvaluationPlan, snapshot: RuntimeSnapshot) -> ApplyResult:
        """Apply a compiled evaluation plan to already committed turn facts."""

        failure = self._validate_plan(plan, snapshot)
        if failure is not None:
            result = failure
        elif not any(item.action != ChangeAction.UNCHANGED for item in plan.operations):
            result = ApplyResult(success=True, snapshot=snapshot)
        else:
            result = self._start_changed(plan, snapshot)
        return result

    def _start_changed(self, plan: EvaluationPlan, snapshot: RuntimeSnapshot) -> ApplyResult:
        """Project a plan containing at least one changed operation."""

        try:
            facts = self._provisioner.committed_evaluation()
            now = _now_iso()
            records, record_index = self._evidence(facts, now)
            capture_spec = self._capture_specification(facts)
            measures = self._measures(facts, records, now)
            projected = self._apply(plan, snapshot, facts, record_index, now)
        except Exception:
            return ApplyResult(
                success=False,
                snapshot=snapshot,
                diagnostics=[
                    Diagnostic(
                        code="cyborg-backend.evaluation.projection-failed",
                        domain="evaluation",
                        address=diagnostic_address("cyborg-cage2"),
                        message="Committed CybORG evaluation facts could not be projected.",
                    )
                ],
            )
        self._capture_spec = capture_spec
        self._evidence_records = records
        self._derived_measures = measures
        self._running = True
        self._startup_order = list(plan.startup_order)
        self._results = dict(projected.snapshot.evaluation_results)
        self._history = {
            key: list(value) for key, value in projected.snapshot.evaluation_history.items()
        }
        return projected

    @staticmethod
    def _validate_plan(plan: object, snapshot: RuntimeSnapshot) -> ApplyResult | None:
        if not isinstance(plan, EvaluationPlan):
            operation = None
        else:
            operation = next(
                (
                    item
                    for item in plan.operations
                    if item.resource_type not in _SUPPORTED_RESOURCE_TYPES
                ),
                False,
            )
            if operation is False:
                return None
        address = operation.address if isinstance(operation, EvaluationOp) else "cyborg-cage2"
        return ApplyResult(
            success=False,
            snapshot=snapshot,
            diagnostics=[
                Diagnostic(
                    code="cyborg-backend.evaluation.unsupported-resource",
                    domain="evaluation",
                    address=diagnostic_address(address),
                    message="The CybORG evaluator cannot represent this evaluation resource.",
                )
            ],
        )

    def _apply(
        self,
        plan: EvaluationPlan,
        snapshot: RuntimeSnapshot,
        facts: tuple[_NativeEvaluationTurn, ...],
        record_index: dict[tuple[str, int, str, str | None, str], str],
        now: str,
    ) -> ApplyResult:
        entries = dict(snapshot.entries)
        results = dict(snapshot.evaluation_results)
        history = {key: list(value) for key, value in snapshot.evaluation_history.items()}
        truth = dict(snapshot.proposition_truth_results)
        changed: list[str] = []
        active = [item for item in plan.operations if item.action != ChangeAction.DELETE]
        propositions = {
            item.address: item for item in active if item.resource_type == "proposition"
        }
        assertion_outcomes = self._existing_assertion_outcomes(truth)
        state = _EvaluationState(entries, results, history, truth, assertion_outcomes)

        for operation in plan.operations:
            if operation.action == ChangeAction.UNCHANGED:
                continue
            changed.append(operation.address)
            self._apply_operation(
                operation,
                state,
                propositions,
                facts,
                record_index,
            )

        self._apply_objectives(active, facts, now, state)
        return ApplyResult(
            success=True,
            snapshot=snapshot.with_entries(
                entries,
                evaluation_results=results,
                evaluation_history=history,
                proposition_truth_results=truth,
            ),
            changed_addresses=changed,
        )

    @staticmethod
    def _existing_assertion_outcomes(
        truth: dict[str, dict[str, object]],
    ) -> dict[str, str]:
        """Seed objective inputs from assertion outcomes preserved by reconciliation."""

        outcomes: dict[str, str] = {}
        for address, payload in truth.items():
            outcome = payload.get("assertion_outcome") if isinstance(payload, dict) else None
            if isinstance(outcome, str) and outcome in {
                "true",
                "false",
                "unknown",
                "unsupported",
            }:
                outcomes[address] = outcome
        return outcomes

    def _apply_operation(
        self,
        operation: EvaluationOp,
        state: _EvaluationState,
        propositions: dict[str, EvaluationOp],
        facts: tuple[_NativeEvaluationTurn, ...],
        record_index: dict[tuple[str, int, str, str | None, str], str],
    ) -> None:
        """Apply one changed non-objective resource or remove prior state."""

        if operation.action == ChangeAction.DELETE:
            state.entries.pop(operation.address, None)
            state.results.pop(operation.address, None)
            state.history.pop(operation.address, None)
            state.truth.pop(operation.address, None)
            return
        state.entries[operation.address] = SnapshotEntry(
            address=operation.address,
            domain=RuntimeDomain.EVALUATION,
            resource_type=operation.resource_type,
            payload=operation.payload,
            ordering_dependencies=operation.ordering_dependencies,
            refresh_dependencies=operation.refresh_dependencies,
            status="admitted" if operation.resource_type != "objective" else "evaluating",
        )
        if operation.resource_type == "assertion":
            truth_result = self._truth_result(operation, propositions, facts, record_index)
            if truth_result is not None:
                state.truth[operation.address] = truth_result.model_dump(mode="json")
                state.assertion_outcomes[operation.address] = truth_result.assertion_outcome.value

    def _apply_objectives(
        self,
        operations: list[EvaluationOp],
        facts: tuple[_NativeEvaluationTurn, ...],
        now: str,
        state: _EvaluationState,
    ) -> None:
        """Refresh every active objective from the reconciled assertion state."""

        terminal = bool(facts and facts[-1].terminal_cause is not None)
        run_id = facts[-1].run_id if facts else "cyborg-cage2.run-unavailable"
        for operation in operations:
            if operation.resource_type == "objective":
                result = self._objective_result(
                    operation, state.assertion_outcomes, terminal, run_id, now
                )
                state.results[operation.address] = result.model_dump(mode="json")
                state.history[operation.address] = [
                    event.model_dump(mode="json") for event in self._history_events(result, now)
                ]

    @staticmethod
    def _truth_result(
        assertion: EvaluationOp,
        propositions: dict[str, EvaluationOp],
        facts: tuple[_NativeEvaluationTurn, ...],
        record_index: dict[tuple[str, int, str, str | None, str], str],
    ) -> PropositionTruthResultModel | None:
        proposition_address = assertion.payload.get("proposition_address")
        polarity = assertion.payload.get("polarity")
        proposition = propositions.get(str(proposition_address))
        result = None
        if proposition is not None and polarity in {"positive", "negative"}:
            evaluation_basis = proposition.payload.get("evaluation_basis")
            if not isinstance(evaluation_basis, str) or not evaluation_basis:
                return None
            base = {
                "result_id": f"truth.{assertion.address}",
                "proposition_address": str(proposition_address),
                "assertion_address": assertion.address,
                "assertion_polarity": polarity,
                "evaluation_basis": evaluation_basis,
            }
            binding, capability = CyborgEvaluator._predicate_binding(proposition)
            match = CyborgEvaluator._latest_component(facts, binding)
            if binding is None:
                result = CyborgEvaluator._unsupported_truth(base, capability)
            elif match is None:
                result = CyborgEvaluator._unknown_truth(base)
            else:
                result = CyborgEvaluator._observed_truth(base, binding, match, record_index)
        return result

    @staticmethod
    def _predicate_binding(
        proposition: EvaluationOp,
    ) -> tuple[_PredicateBinding | None, str]:
        """Resolve the one supported finite reward-component predicate shape."""

        payload = proposition.payload
        spec = payload.get("spec")
        predicate = spec.get("predicate") if isinstance(spec, dict) else None
        property_name = predicate.get("property") if isinstance(predicate, dict) else None
        raw_operator = predicate.get("operator") if isinstance(predicate, dict) else None
        operator_name = (
            _COMPILED_OPERATOR_NAMES.get(raw_operator, raw_operator)
            if isinstance(raw_operator, str)
            else None
        )
        expected = None
        if isinstance(predicate, dict):
            expected = predicate.get("value", predicate.get("expected"))
        subjects = payload.get("subject_addresses")
        requirements = payload.get("evidence_requirement_refs")
        subject = CyborgEvaluator._single_subject(subjects)
        requirement = CyborgEvaluator._single_requirement(requirements)
        evidence_binding = _EVIDENCE_REQUIREMENT_BINDINGS.get(requirement or "")
        supported = (
            CyborgEvaluator._supported_predicate_values(property_name, operator_name, expected)
            and subject is not None
            and evidence_binding is not None
        )
        binding = None
        if supported and evidence_binding is not None:
            binding = _PredicateBinding(
                cast(str, property_name),
                cast(str, operator_name),
                float(cast(int | float, expected)),
                cast(str, subject),
                evidence_binding[0],
                evidence_binding[1],
            )
        capability = (
            "cyborg-cage2.evaluation.critical-impact-unavailable"
            if property_name == "critical-impact"
            else "cyborg-cage2.evaluation.predicate-unsupported"
        )
        return binding, capability

    @staticmethod
    def _supported_predicate_values(
        property_name: object, operator_name: object, expected: object
    ) -> bool:
        """Check the scalar fields of a supported reward-component predicate."""

        return (
            isinstance(property_name, str)
            and property_name in _SUPPORTED_COMPONENTS
            and isinstance(operator_name, str)
            and operator_name in _OPERATORS
            and type(expected) in {int, float}
        )

    @staticmethod
    def _single_subject(subjects: object) -> str | None:
        """Resolve one exact portable subject address from a compiled predicate."""

        if not isinstance(subjects, (list, tuple)) or len(subjects) != 1:
            return None
        subject = subjects[0]
        return subject if isinstance(subject, str) else None

    @staticmethod
    def _single_requirement(requirements: object) -> str | None:
        """Resolve one exact compiled evidence-requirement reference."""

        if not isinstance(requirements, (list, tuple)) or len(requirements) != 1:
            return None
        requirement = requirements[0]
        return requirement if isinstance(requirement, str) else None

    @staticmethod
    def _latest_component(
        facts: tuple[_NativeEvaluationTurn, ...],
        binding: _PredicateBinding | None,
    ) -> tuple[_NativeEvaluationTurn, _NativeRewardComponent] | None:
        """Return the latest exact component matching a supported predicate."""

        if binding is None:
            return None
        matches = [
            (turn, component)
            for turn in facts
            for component in turn.components
            if component.component == binding.property_name
            and component.target_address == binding.subject
            and component.source_row == binding.source_row
            and (
                binding.participant_address is None
                or component.participant_address == binding.participant_address
            )
        ]
        return matches[-1] if matches else None

    @staticmethod
    def _unsupported_truth(base: dict[str, str], capability: str) -> PropositionTruthResultModel:
        """Build an explicit unsupported result without inferring hidden truth."""

        return PropositionTruthResultModel(
            **base,
            proposition_outcome="unsupported",
            assertion_outcome="unsupported",
            unsupported_capability_refs=[capability],
            loss_disclosures=[
                PropositionLossDisclosureModel(kind="lossy", within_admissible_bound=True)
            ],
        )

    @staticmethod
    def _unknown_truth(base: dict[str, str]) -> PropositionTruthResultModel:
        """Build an unknown result when no committed component evidence exists."""

        return PropositionTruthResultModel(
            **base,
            proposition_outcome="unknown",
            assertion_outcome="unknown",
            indeterminacy_reason="missing_evidence",
            loss_disclosures=[
                PropositionLossDisclosureModel(kind="lossy", within_admissible_bound=True)
            ],
        )

    @staticmethod
    def _observed_truth(
        base: dict[str, str],
        binding: _PredicateBinding,
        match: tuple[_NativeEvaluationTurn, _NativeRewardComponent],
        record_index: dict[tuple[str, int, str, str | None, str], str],
    ) -> PropositionTruthResultModel:
        """Evaluate one proposition from its latest committed component evidence."""

        turn, component = match
        proposition_true = bool(
            _OPERATORS[binding.operator_name](component.value, binding.expected)
        )
        polarity = base["assertion_polarity"]
        assertion_true = proposition_true if polarity == "positive" else not proposition_true
        evidence_ref = record_index[
            (
                turn.action_instance_id,
                turn.logical_step,
                component.participant_address,
                component.target_address,
                component.component,
            )
        ]
        return PropositionTruthResultModel(
            **base,
            proposition_outcome="true" if proposition_true else "false",
            assertion_outcome="true" if assertion_true else "false",
            probe_binding=PropositionProbeBindingModel(
                binding_id="cyborg-cage2.reward-probe",
                implementation_id="cyborg-cage2-reward-projection",
                implementation_version="1.0.0",
                artifact_digest=_PROBE_DIGEST,
                backend_manifest_ref="backend-manifest.cyborg-cage2",
                proposition_address=base["proposition_address"],
                capability_refs=["cyborg-cage2.evaluation.reward-components"],
            ),
            evidence_refs=[evidence_ref],
            temporal_context=PropositionTemporalContextModel(
                boundary_ref=f"logical-step:{turn.logical_step}",
                time_domain="logical",
                clock_authority="cyborg-cage2-time-runtime",
            ),
        )

    @staticmethod
    def _objective_result(
        operation: EvaluationOp,
        outcomes: dict[str, str],
        terminal: bool,
        run_id: str,
        now: str,
    ) -> EvaluationResultStateModel:
        addresses = operation.payload.get("success_addresses")
        spec = operation.payload.get("spec")
        success = spec.get("success") if isinstance(spec, dict) else None
        mode = success.get("mode") if isinstance(success, dict) else None
        valid = (
            isinstance(addresses, (list, tuple))
            and bool(addresses)
            and all(isinstance(item, str) for item in addresses)
            and mode in {"all", "all_of", "any", "any_of"}
        )
        values = [outcomes.get(address, "unknown") for address in addresses] if valid else []
        if not terminal:
            status, passed = "running", None
        elif not valid or any(value not in {"true", "false"} for value in values):
            status, passed = "failed", None
        else:
            booleans = [value == "true" for value in values]
            status = "ready"
            passed = all(booleans) if mode in {"all", "all_of"} else any(booleans)
        return EvaluationResultStateModel(
            resource_type="objective",
            run_id=run_id,
            status=status,
            observed_at=now,
            updated_at=now,
            passed=passed,
            score=None,
            max_score=None,
            detail="Objective evaluated from its compiled assertion references.",
            evidence_refs=[],
        )

    @staticmethod
    def _history_events(
        result: EvaluationResultStateModel, now: str
    ) -> tuple[EvaluationHistoryEventModel, ...]:
        return (
            EvaluationHistoryEventModel(
                event_type="evaluation_started",
                timestamp=now,
                status="running",
            ),
            EvaluationHistoryEventModel(
                event_type={
                    "ready": "evaluation_ready",
                    "failed": "evaluation_failed",
                }.get(result.status, "evaluation_updated"),
                timestamp=now,
                status=result.status,
                passed=result.passed,
                detail=result.detail,
                evidence_refs=result.evidence_refs,
            ),
        )

    @staticmethod
    def _evidence(
        facts: tuple[_NativeEvaluationTurn, ...], now: str
    ) -> tuple[
        tuple[ExperimentEvidenceRecordModel, ...],
        dict[tuple[str, int, str, str | None, str], str],
    ]:
        records: list[ExperimentEvidenceRecordModel] = []
        index: dict[tuple[str, int, str, str | None, str], str] = {}
        for turn in facts:
            for participant, value in turn.rewards:
                records.append(
                    CyborgEvaluator._evidence_record(
                        turn,
                        participant,
                        None,
                        "per-step-reward",
                        value,
                        "source-ledger:reward-objectives",
                        now,
                    )
                )
            for component in turn.components:
                record = CyborgEvaluator._evidence_record(
                    turn,
                    component.participant_address,
                    component.target_address,
                    component.component,
                    component.value,
                    component.source_row,
                    now,
                )
                records.append(record)
                index[
                    (
                        turn.action_instance_id,
                        turn.logical_step,
                        component.participant_address,
                        component.target_address,
                        component.component,
                    )
                ] = record.evidence_record_id
            if turn.terminal_cause is not None:
                records.append(
                    CyborgEvaluator._evidence_record(
                        turn,
                        "evaluation.run",
                        None,
                        "terminal-cause",
                        turn.terminal_cause,
                        "source-ledger:wrapper-termination-cutoff",
                        now,
                    )
                )
        return tuple(records), index

    @staticmethod
    def _evidence_record(
        turn: _NativeEvaluationTurn,
        participant: str,
        target: str | None,
        meaning: str,
        value: float | str,
        source_row: str,
        now: str,
    ) -> ExperimentEvidenceRecordModel:
        record_id = "evidence-record.cyborg-cage2." + _identity(
            turn.run_id, turn.action_instance_id, turn.logical_step, participant, target, meaning
        )
        rendered_value = f"{value:.17g}" if isinstance(value, float) else value
        summary = (
            f"run={turn.run_id}; episode={turn.episode_id}; action={turn.action_instance_id}; "
            f"logical-step:{turn.logical_step}; participant={participant}; "
            f"target={target or 'none'}; "
            f"meaning={meaning}; value={rendered_value}; source={source_row}."
        )
        qualification = load_qualification()
        source = qualification.get("source")
        source_revision = source.get("commit") if isinstance(source, dict) else None
        if not isinstance(source_revision, str) or not source_revision:
            raise RuntimeError
        source_refs = [
            ExperimentReferenceModel(ref_kind="protocol", ref_id=source_row, ref_version="1.0.0"),
            ExperimentReferenceModel(ref_kind="other", ref_id=turn.episode_id, ref_version="1.0.0"),
            ExperimentReferenceModel(
                ref_kind="result", ref_id=turn.action_instance_id, ref_version="1.0.0"
            ),
            ExperimentReferenceModel(
                ref_kind="other", ref_id=f"logical-step:{turn.logical_step}", ref_version="1.0.0"
            ),
            ExperimentReferenceModel(
                ref_kind="other",
                ref_id="derivation:cyborg-cage2-reward-projection-v1",
                ref_version="1.0.0",
            ),
            ExperimentReferenceModel(
                ref_kind="profile",
                ref_id=CYBORG_PROFILE_ID,
                ref_version=source_revision,
            ),
        ]
        return ExperimentEvidenceRecordModel(
            schema_version="experiment-evidence-record/v1",
            evidence_record_id=record_id,
            record_version=_RECORD_VERSION,
            capture_spec_ref=ExperimentCaptureSpecReferenceModel(
                ref_kind="capture-spec", ref_id=_CAPTURE_SPEC_ID, ref_version="1.0.0"
            ),
            capture_requirement_ref=_CAPTURE_REQUIREMENT_ID,
            run_ref=ExperimentReferenceModel(
                ref_kind="run", ref_id=turn.run_id, ref_version="1.0.0"
            ),
            source_refs=source_refs,
            evidence_kind="telemetry",
            captured_at=now,
            capture_window_ref=_CAPTURE_WINDOW_ID,
            raw_content=ExperimentRawEvidenceContentModel(
                content_uri=f"urn:raes:{record_id}",
                content_checksum=ExperimentChecksumModel(
                    algorithm="sha256",
                    value=hashlib.sha256(summary.encode("utf-8")).hexdigest(),
                ),
                payload_summary=summary,
                loss_disclosure=(
                    "Native state, reward vectors, observations, object representations, "
                    "and hidden truth are withheld. Missing facts are not projected as zero."
                ),
            ),
            sensitivity="redacted",
            redaction_state="redacted",
            provenance_refs=source_refs,
        )

    @staticmethod
    def _capture_specification(
        facts: tuple[_NativeEvaluationTurn, ...],
    ) -> ExperimentCaptureSpecModel | None:
        if not facts:
            return None
        return ExperimentCaptureSpecModel(
            schema_version="experiment-capture-spec/v1",
            capture_spec_id=_CAPTURE_SPEC_ID,
            spec_version="1.0.0",
            title="CybORG committed reward fact capture",
            description="Capture finite reward facts after the portable aggregate turn commits.",
            scope_refs=[
                ExperimentReferenceModel(
                    ref_kind="run", ref_id=facts[-1].run_id, ref_version="1.0.0"
                )
            ],
            capture_windows=[
                ExperimentCaptureWindowModel(
                    window_id=_CAPTURE_WINDOW_ID,
                    window_kind="event",
                    trigger_ref=ExperimentReferenceModel(
                        ref_kind="run", ref_id=facts[-1].run_id, ref_version="1.0.0"
                    ),
                    description="Accepted aggregate CybORG turns in one episode.",
                )
            ],
            capture_requirements={
                _CAPTURE_REQUIREMENT_ID: ExperimentCaptureRequirementModel(
                    requirement_id=_CAPTURE_REQUIREMENT_ID,
                    title="Committed finite reward fact",
                    capture_kind="telemetry",
                    capture_scope="run",
                    channel_ref=ExperimentMeasurementChannelReferenceModel(
                        ref_kind="measurement-channel",
                        ref_id="measurement-channel.cyborg-cage2.reward-calculators",
                        ref_version="1.0.0",
                    ),
                    window_refs=[_CAPTURE_WINDOW_ID],
                    expected_media_types=["application/json"],
                    sensitivity="redacted",
                    redaction_policy="withhold-native-simulator-state",
                    integrity_requirements=["sha256"],
                    loss_disclosure_required=True,
                )
            },
            validity_notes=[
                ExperimentValidityNoteModel(
                    category="construct",
                    note="Reward and score remain distinct from objective outcome and conformance.",
                )
            ],
        )

    @staticmethod
    def _measures(
        facts: tuple[_NativeEvaluationTurn, ...],
        records: tuple[ExperimentEvidenceRecordModel, ...],
        now: str,
    ) -> tuple[ExperimentDerivedMeasureModel, ...]:
        """Build the component and score measures for committed Blue reward facts."""

        if not facts or not records:
            return ()
        measures = _blue_component_measures(facts, records, now)
        measures.append(_blue_score_measure(facts, records, now))
        return tuple(measures)

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
        return {key: dict(value) for key, value in self._results.items()}

    def history(self) -> dict[str, list[dict[str, object]]]:
        return {key: [dict(item) for item in value] for key, value in self._history.items()}

    def capture_spec(self) -> ExperimentCaptureSpecModel | None:
        return self._capture_spec

    def evidence_records(self) -> tuple[ExperimentEvidenceRecordModel, ...]:
        return self._evidence_records

    def derived_measures(self) -> tuple[ExperimentDerivedMeasureModel, ...]:
        return self._derived_measures

    def stop(self, snapshot: RuntimeSnapshot) -> ApplyResult:
        entries = {
            key: value
            for key, value in snapshot.entries.items()
            if value.domain != RuntimeDomain.EVALUATION
        }
        removed = [
            key
            for key, value in snapshot.entries.items()
            if value.domain == RuntimeDomain.EVALUATION
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
