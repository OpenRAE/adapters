"""Evaluator-only projection of sanitized NASim run facts."""

from __future__ import annotations

from raes_adapters._experiment_evidence import EvaluatorEvidenceConfig
from raes_adapters._gym_backend.evaluator import GymEvaluator
from raes_adapters._manifest_support import read_source_revision
from raes_adapters.nasim import load_qualification
from raes_adapters.nasim.scenario_ledger import NASIM_TINY

from .driver import NasimDriverProtocol

EVALUATION_EVIDENCE_REF = "evidence-record.nasim.evaluator-summary"

_TASK_ID = NASIM_TINY.task_id
_EVIDENCE_CONFIG = EvaluatorEvidenceConfig(
    task_id=_TASK_ID,
    evidence_ref=EVALUATION_EVIDENCE_REF,
    capture_spec_id="nasim-evaluator-capture",
    capture_requirement_id="nasim-evaluator-summary",
    capture_window_id="nasim-selected-episode",
    source_protocol_ref_id="nasim-tiny-protocol",
    provenance_ref_id="qualification.nasim.selected-source",
    measure_id_base="measure.nasim.cumulative-attacker-reward",
    metric_ref_id="cumulative_attacker_reward",
    method_id="nasim-cumulative-reward",
    method_name="Source cumulative attacker reward",
    method_description=(
        "Report the sanitized cumulative reward maintained by the serialized source "
        "driver, where each step reward is action_result.value minus action.cost."
    ),
    capture_title="NASim evaluator summary capture",
    capture_description=(
        "Capture the sanitized evaluator-owned summary used to derive the selected "
        "cumulative-reward measure."
    ),
    capture_window_description=(
        "One read-only evaluator projection after the current serialized source transition."
    ),
    capture_requirement_title="Sanitized evaluator summary",
    channel_ref_id="nasim-evaluation-history",
    redaction_policy="redaction.nasim.evaluator-summary",
    validity_note=(
        "The capture attests one observed summary; it does not establish deterministic replay."
    ),
    validity_mitigation="Record applied and unbound stochastic streams with the run.",
    loss_disclosure=(
        "The native fully-observed state, flat observation vector, action index, host "
        "state, and info are withheld."
    ),
    limitations=(
        "Single-run cumulative source reward; no deterministic replay or outcome "
        "equivalence is claimed.",
        "Action success is drawn from the global NumPy stream, which the environment "
        "reset seed does not bind; only an explicit global seed makes a run reproducible.",
        "Goal termination and step-limit truncation are retained as distinct terminal "
        "facts; neither is inferred from the other.",
    ),
    capture_notes=(
        "Native observations, the flat action index, host state, and info remain driver-private.",
    ),
)


class NasimEvaluator(GymEvaluator):
    """Read evaluator-owned facts without advancing the source environment."""

    def __init__(self, driver: NasimDriverProtocol) -> None:
        super().__init__(
            driver,
            "nasim",
            _EVIDENCE_CONFIG,
            lambda: read_source_revision(load_qualification),
        )


__all__ = [
    "EVALUATION_EVIDENCE_REF",
    "NasimEvaluator",
]
