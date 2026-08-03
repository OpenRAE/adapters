"""Evaluator-only projection of sanitized CyberBattleSim run facts."""

from __future__ import annotations

from raes_adapters._experiment_evidence import EvaluatorEvidenceConfig
from raes_adapters._gym_backend.evaluator import GymEvaluator
from raes_adapters._manifest_support import read_source_revision
from raes_adapters.cyberbattlesim import load_qualification
from raes_adapters.cyberbattlesim.scenario_ledger import CYBERBATTLE_CHAIN

from .driver import CyberBattleSimDriverProtocol

EVALUATION_EVIDENCE_REF = "evidence-record.cyberbattlesim.evaluator-summary"

_TASK_ID = CYBERBATTLE_CHAIN.task_id
_EVIDENCE_CONFIG = EvaluatorEvidenceConfig(
    task_id=_TASK_ID,
    evidence_ref=EVALUATION_EVIDENCE_REF,
    capture_spec_id="cyberbattlesim-evaluator-capture",
    capture_requirement_id="cyberbattlesim-evaluator-summary",
    capture_window_id="cyberbattlesim-selected-episode",
    source_protocol_ref_id="cyberbattlesim-chain-public",
    provenance_ref_id="qualification.cyberbattlesim.selected-source",
    measure_id_base="measure.cyberbattlesim.cumulative-attacker-reward",
    metric_ref_id="cumulative_attacker_reward",
    method_id="cyberbattlesim-cumulative-reward",
    method_name="Source cumulative attacker reward",
    method_description=(
        "Report the sanitized cumulative reward maintained by the serialized source driver."
    ),
    capture_title="CyberBattleSim evaluator summary capture",
    capture_description=(
        "Capture the sanitized evaluator-owned summary used to derive the selected "
        "cumulative-reward measure."
    ),
    capture_window_description=(
        "One read-only evaluator projection after the current serialized source transition."
    ),
    capture_requirement_title="Sanitized evaluator summary",
    channel_ref_id="cyberbattlesim-evaluation-history",
    redaction_policy="redaction.cyberbattlesim.evaluator-summary",
    validity_note=(
        "The capture attests one observed summary; it does not establish deterministic replay."
    ),
    validity_mitigation="Record applied and unbound stochastic streams with the run.",
    loss_disclosure=(
        "Source-native observations, action availability, credentials, reward components, "
        "hidden state, and info are withheld."
    ),
    limitations=(
        "Single-run cumulative source reward; no deterministic replay or outcome "
        "equivalence is claimed.",
        "Python-global and NumPy-global random streams remain unbound by the selected "
        "reset protocol.",
    ),
    capture_notes=(
        "Native observations, masks, credentials, reward components, hidden state, and info "
        "remain driver-private.",
    ),
)


class CyberBattleSimEvaluator(GymEvaluator):
    """Read evaluator-owned facts without advancing the source environment."""

    def __init__(self, driver: CyberBattleSimDriverProtocol) -> None:
        super().__init__(
            driver,
            "cyberbattlesim",
            _EVIDENCE_CONFIG,
            lambda: read_source_revision(load_qualification),
        )


__all__ = [
    "CyberBattleSimEvaluator",
    "EVALUATION_EVIDENCE_REF",
]
