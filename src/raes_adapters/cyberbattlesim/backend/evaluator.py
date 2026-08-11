"""Evaluator-only projection of sanitized CyberBattleSim run facts."""

from __future__ import annotations

import hashlib
import math
from dataclasses import replace
from typing import cast

from raes_contracts.contracts import ExperimentChecksumModel  # type: ignore[import-untyped]
from raes_contracts.contracts.experiment_capture import (  # type: ignore[import-untyped]
    ExperimentRawEvidenceContentModel,
)
from raes_operations.run_artifacts import serialize_run_artifact  # type: ignore[import-untyped]

from raes_adapters._experiment_evidence import (
    EvaluatorEvidenceConfig,
    EvaluatorSummary,
    SupplementalJsonArtifact,
    build_evidence_only,
)
from raes_adapters._gym_backend.evaluator import GymEvaluator, _DriverEvaluationFacts
from raes_adapters._manifest_support import read_source_revision
from raes_adapters.cyberbattlesim import load_qualification
from raes_adapters.cyberbattlesim.scenario_ledger import CYBERBATTLE_CHAIN

from .driver import CyberBattleSimDriverProtocol, DriverEvaluation

EVALUATION_EVIDENCE_REF = "evidence-record.cyberbattlesim.evaluator-summary"
OUTCOME_EVIDENCE_REF = "evidence-record.cyberbattlesim.sanitized-episode-outcome"
OUTCOME_ARTIFACT = "episode-outcome.json"
_OUTCOME_SCHEMA = "cyberbattlesim-sanitized-episode-outcome/v1"

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
        "hidden state, and all source info except network availability are withheld."
    ),
    limitations=(
        "Single-run cumulative source reward; no deterministic replay or outcome "
        "equivalence is claimed.",
        "Python-global and NumPy-global random streams remain unbound by the selected "
        "reset protocol.",
    ),
    capture_notes=(
        "Native observations, masks, credentials, reward components, hidden state, and all "
        "source info except network availability remain driver-private.",
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

    def _record_projection_facts(
        self,
        facts: _DriverEvaluationFacts,
        summary: EvaluatorSummary,
        now: str,
    ) -> None:
        """Retain one compact allowlisted availability/cause evidence member."""

        super()._record_projection_facts(facts, summary, now)
        selected = cast(DriverEvaluation, facts)
        availability = tuple(selected.network_availability)
        if len(availability) != selected.step_count or any(
            not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in availability
        ):
            raise RuntimeError("selected simulator network availability is unavailable")
        payload: dict[str, object] = {
            "schema_version": _OUTCOME_SCHEMA,
            "network_availability": list(availability),
            "terminal_cause": selected.terminal_cause,
        }
        serialized = serialize_run_artifact(payload).encode("utf-8")
        outcome_config: EvaluatorEvidenceConfig = replace(
            _EVIDENCE_CONFIG, evidence_ref=OUTCOME_EVIDENCE_REF
        )
        record = build_evidence_only(
            outcome_config,
            summary,
            now,
            self._source_revision(),
            payload_summary=(
                "Sanitized per-step network availability and reconstructed terminal cause "
                f"are retained in {OUTCOME_ARTIFACT}."
            ),
        )
        raw_content = ExperimentRawEvidenceContentModel(
            content_uri=OUTCOME_ARTIFACT,
            content_checksum=ExperimentChecksumModel(
                algorithm="sha256",
                value=hashlib.sha256(serialized).hexdigest(),
            ),
            payload_summary=record.raw_content.payload_summary,
            loss_disclosure=(
                "Only per-step network availability and the reconstructed terminal cause "
                "are retained; all other source info and native state are withheld."
            ),
        )
        self._evidence_records = (
            *self._evidence_records,
            record.model_copy(update={"raw_content": raw_content}),
        )
        self._supplemental_artifacts = (
            SupplementalJsonArtifact(relative_path=OUTCOME_ARTIFACT, payload=payload),
        )


__all__ = [
    "CyberBattleSimEvaluator",
    "EVALUATION_EVIDENCE_REF",
    "OUTCOME_ARTIFACT",
    "OUTCOME_EVIDENCE_REF",
]
