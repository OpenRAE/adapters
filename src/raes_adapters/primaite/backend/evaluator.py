"""Evaluator-only projection of sanitized PrimAITE run facts.

The evaluator reads the one committed driver fact without advancing the source.
The neutral :class:`GymEvaluator` already realizes the portable evaluation
lifecycle (unsupported-resource rejection, unknown proposition truth, result and
history projection, capture-spec and evidence construction), so PrimAITE
parameterizes it and overrides only what claim integrity requires: it
**withholds** the cumulative BLUE reward. The source reward's member-evidence
closure is incomplete, so the result stays ``RUNNING`` with no score, no
reward-valued derived measure is projected, and the evidence record discloses the
withholding rather than the reward value.
"""

from __future__ import annotations

from raes_contracts.contracts import (  # type: ignore[import-untyped]
    EvaluationResultStateModel,
)
from raes_contracts.evaluation import (  # type: ignore[import-untyped]
    EvaluationResultContract,
    EvaluationResultStatus,
)
from raes_contracts.planning import EvaluationOp  # type: ignore[import-untyped]

from raes_adapters._experiment_evidence import (
    EvaluatorEvidenceConfig,
    EvaluatorSummary,
    build_capture_spec,
    build_evidence_only,
)
from raes_adapters._gym_backend.evaluator import GymEvaluator
from raes_adapters.primaite import load_qualification
from raes_adapters.primaite.scenario_ledger import DATA_MANIPULATION

from .driver import PrimaiteDriverProtocol

EVALUATION_EVIDENCE_REF = "evidence-record.primaite.evaluator-summary"

_TASK_ID = DATA_MANIPULATION.task_id
# The measure identities below name what a live, evidence-closed run *would*
# measure; PrimAITE withholds the reward, so no derived measure is built from
# them. They are retained so the neutral evidence config stays fully specified.
_EVIDENCE_CONFIG = EvaluatorEvidenceConfig(
    task_id=_TASK_ID,
    evidence_ref=EVALUATION_EVIDENCE_REF,
    capture_spec_id="primaite-evaluator-capture",
    capture_requirement_id="primaite-evaluator-summary",
    capture_window_id="primaite-selected-episode",
    source_protocol_ref_id="primaite-data-manipulation",
    provenance_ref_id="qualification.primaite.selected-source",
    measure_id_base="measure.primaite.cumulative-blue-reward",
    metric_ref_id="cumulative_blue_reward",
    method_id="primaite-cumulative-reward",
    method_name="Source cumulative BLUE reward",
    method_description=(
        "The cumulative BLUE reward is withheld pending source-member evidence closure."
    ),
    capture_title="PrimAITE evaluator summary capture",
    capture_description=(
        "Capture the sanitized evaluator-owned summary for the selected serialized "
        "source transition."
    ),
    capture_window_description=(
        "One read-only evaluator projection after the current serialized source transition."
    ),
    capture_requirement_title="Sanitized evaluator summary",
    channel_ref_id="primaite-evaluation-history",
    redaction_policy="redaction.primaite.evaluator-summary",
    validity_note=(
        "The capture attests one observed summary; it does not establish deterministic replay."
    ),
    validity_mitigation="Record broken, absent, and unbound stochastic streams with the run.",
    loss_disclosure=(
        "Source-native observation vector, action availability, info, reward components, "
        "hidden state, and traffic are withheld."
    ),
    limitations=("The cumulative BLUE reward is withheld pending source-member evidence closure.",),
    capture_notes=(
        "Native observation vector, action ids, info, reward components, hidden state, and "
        "traffic remain driver-private.",
    ),
)


def _source_revision() -> str:
    """Read the selected source revision used in evidence provenance."""

    qualification = load_qualification()
    source = qualification.get("source")
    source_revision = source.get("commit") if isinstance(source, dict) else None
    if not isinstance(source_revision, str):
        raise RuntimeError("selected simulator qualification is invalid")
    return source_revision


def _withheld_payload_summary(summary: EvaluatorSummary) -> str:
    """Disclose the withheld reward without leaking its value."""

    return (
        "Sanitized evaluator summary: "
        f"{summary.step_count} source transitions; terminal cause "
        f"{summary.terminal_cause or 'none'}; cumulative BLUE reward withheld "
        "pending source-member evidence closure."
    )


class PrimaiteEvaluator(GymEvaluator):
    """Read evaluator-owned facts without advancing or scoring the source."""

    def __init__(self, driver: PrimaiteDriverProtocol) -> None:
        super().__init__(driver, "primaite", _EVIDENCE_CONFIG, _source_revision)

    def _record_projection(self, summary: EvaluatorSummary, now: str) -> None:
        """Emit a withheld evidence record and no derived measure for one projection."""

        self._capture_spec = build_capture_spec(self._config, summary, now)
        self._evidence_records = (
            build_evidence_only(
                self._config,
                summary,
                now,
                self._source_revision(),
                payload_summary=_withheld_payload_summary(summary),
            ),
        )
        # No derived measure: the source reward is withheld pending evidence closure.
        self._derived_measures = ()

    def _result_state(
        self,
        operation: EvaluationOp,
        summary: EvaluatorSummary,
        now: str,
        evidence_ref: str | None,
    ) -> EvaluationResultStateModel:
        """Project a running, unscored result: the reward stays withheld."""

        result_contract = operation.payload.get("result_contract", {})
        if not isinstance(result_contract, dict):
            raise RuntimeError("compiled evaluation result contract is invalid")
        contract = EvaluationResultContract.from_mapping(result_contract)
        if evidence_ref is None:
            raise RuntimeError("PrimAITE evaluation evidence identity is unavailable")
        return EvaluationResultStateModel(
            resource_type=contract.resource_type,
            run_id=summary.execution_ref,
            status=EvaluationResultStatus.RUNNING.value,
            observed_at=now,
            updated_at=now,
            passed=None,
            score=None,
            max_score=None,
            detail=(
                f"PrimAITE evaluator projection after {summary.step_count} "
                "source transitions; reward withheld."
            ),
            evidence_refs=[evidence_ref],
        )


__all__ = [
    "EVALUATION_EVIDENCE_REF",
    "PrimaiteEvaluator",
]
