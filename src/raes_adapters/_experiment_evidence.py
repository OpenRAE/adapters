"""Backend-neutral evaluator evidence, measure, and capture construction.

Every gym-style backend projects its committed, sanitized run summary into the
same published RAES experiment contracts: one redacted evidence record, one
cumulative-reward derived measure, and the capture spec that bounds them. This
module builds those contract shapes from a neutral summary plus a backend-local
:class:`EvaluatorEvidenceConfig`; it holds no simulator semantics of its own
(see the NASim backend guardrails "Evaluation" row: reuse the contract shapes,
not either backend's semantics or classes). Each backend supplies its own
identities, provenance, limitations, and disclosure text.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from raes_contracts.contracts import (  # type: ignore[import-untyped]
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
)
from raes_contracts.contracts.experiment_capture import (  # type: ignore[import-untyped]
    ExperimentRawEvidenceContentModel,
)

_EVIDENCE_RECORD_VERSION = "1.0.0"


@dataclass(frozen=True)
class EvaluatorSummary(object):
    """Sanitized, evaluator-owned run facts shared by every gym backend.

    ``terminated`` and ``truncated`` are retained as distinct evaluator evidence
    so a per-run terminal fact (for example, truncation that fired alongside a
    goal) survives into the portable record rather than only a static limitation.
    """

    step_count: int
    cumulative_reward: float
    execution_ref: str
    projection_ref: str
    terminated: bool = False
    truncated: bool = False
    terminal_cause: str | None = None


@dataclass(frozen=True)
class EvaluatorEvidenceConfig(object):
    """Backend-local identities and disclosure text for evaluator evidence."""

    task_id: str
    evidence_ref: str
    capture_spec_id: str
    capture_requirement_id: str
    capture_window_id: str
    source_protocol_ref_id: str
    provenance_ref_id: str
    measure_id_base: str
    metric_ref_id: str
    method_id: str
    method_name: str
    method_description: str
    capture_title: str
    capture_description: str
    capture_window_description: str
    capture_requirement_title: str
    channel_ref_id: str
    redaction_policy: str
    validity_note: str
    validity_mitigation: str
    loss_disclosure: str
    limitations: tuple[str, ...]
    capture_notes: tuple[str, ...] = field(default_factory=tuple)


def scoped_id(base: str, projection_ref: str) -> str:
    """Scope an artifact identity to one evaluator projection."""

    if not projection_ref:
        raise RuntimeError("evaluation projection identity is unavailable")
    identity_digest = hashlib.sha256(projection_ref.encode("utf-8")).hexdigest()
    return f"{base}.{identity_digest}"


def build_capture_spec(
    config: EvaluatorEvidenceConfig,
    summary: EvaluatorSummary,
    now: str,
) -> ExperimentCaptureSpecModel:
    """Build the projection-scoped evaluator capture specification."""

    capture_spec_id = scoped_id(config.capture_spec_id, summary.projection_ref)
    capture_requirement_id = scoped_id(config.capture_requirement_id, summary.projection_ref)
    capture_window_id = scoped_id(config.capture_window_id, summary.projection_ref)
    return ExperimentCaptureSpecModel(
        schema_version="experiment-capture-spec/v1",
        capture_spec_id=capture_spec_id,
        spec_version="1.0.0",
        title=config.capture_title,
        description=config.capture_description,
        scope_refs=[
            ExperimentReferenceModel(
                ref_kind="run",
                ref_id=summary.execution_ref,
                ref_version="1.0.0",
            ),
            ExperimentReferenceModel(
                ref_kind="task",
                ref_id=config.task_id,
                ref_version="1.0.0",
            ),
        ],
        capture_windows=[
            ExperimentCaptureWindowModel(
                window_id=capture_window_id,
                window_kind="event",
                starts_at=now,
                ends_at=now,
                description=config.capture_window_description,
            )
        ],
        capture_requirements={
            capture_requirement_id: ExperimentCaptureRequirementModel(
                requirement_id=capture_requirement_id,
                title=config.capture_requirement_title,
                capture_kind="telemetry",
                capture_scope="run",
                channel_ref=ExperimentMeasurementChannelReferenceModel(
                    ref_kind="measurement-channel",
                    ref_id=config.channel_ref_id,
                    ref_version="1.0.0",
                ),
                window_refs=[capture_window_id],
                expected_media_types=["application/json"],
                sensitivity="redacted",
                redaction_policy=config.redaction_policy,
                integrity_requirements=["sha256"],
                retention_policy="run-lifetime",
                loss_disclosure_required=True,
                notes=list(config.capture_notes),
            )
        },
        validity_notes=[
            ExperimentValidityNoteModel(
                category="reproducibility",
                note=config.validity_note,
                mitigation=config.validity_mitigation,
            )
        ],
    )


def build_evidence_and_measure(
    config: EvaluatorEvidenceConfig,
    summary: EvaluatorSummary,
    now: str,
    source_revision: str,
) -> tuple[ExperimentEvidenceRecordModel, ExperimentDerivedMeasureModel]:
    """Build projection-scoped evidence and its derived reward measure."""

    evidence_record_id = scoped_id(config.evidence_ref, summary.projection_ref)
    evidence_record = _evidence_record(config, summary, now, source_revision, evidence_record_id)
    derived_measure = _derived_measure(config, summary, now, evidence_record_id)
    return evidence_record, derived_measure


def build_evidence_only(
    config: EvaluatorEvidenceConfig,
    summary: EvaluatorSummary,
    now: str,
    source_revision: str,
    *,
    payload_summary: str,
) -> ExperimentEvidenceRecordModel:
    """Build a projection-scoped evidence record with no derived measure.

    A backend that withholds its reward (its member-evidence closure is
    incomplete) records the same redacted evidence shape but supplies its own
    ``payload_summary`` disclosing the withholding, and projects no measure.
    """

    evidence_record_id = scoped_id(config.evidence_ref, summary.projection_ref)
    return _evidence_record(
        config, summary, now, source_revision, evidence_record_id, payload_summary=payload_summary
    )


def _evidence_record(
    config: EvaluatorEvidenceConfig,
    summary: EvaluatorSummary,
    now: str,
    source_revision: str,
    evidence_record_id: str,
    *,
    payload_summary: str | None = None,
) -> ExperimentEvidenceRecordModel:
    """Build one redacted, checksummed evaluator evidence record.

    ``payload_summary`` defaults to the reward-disclosing summary; a backend that
    withholds its reward supplies its own withholding disclosure instead.
    """

    capture_spec_id = scoped_id(config.capture_spec_id, summary.projection_ref)
    capture_requirement_id = scoped_id(config.capture_requirement_id, summary.projection_ref)
    capture_window_id = scoped_id(config.capture_window_id, summary.projection_ref)
    if payload_summary is None:
        payload_summary = (
            "Sanitized evaluator summary: "
            f"{summary.step_count} source transitions and cumulative "
            f"reward {summary.cumulative_reward:.17g}; "
            f"terminated={summary.terminated} truncated={summary.truncated} "
            f"terminal_cause={summary.terminal_cause}."
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
            ref_id=summary.execution_ref,
            ref_version="1.0.0",
        ),
        task_ref=ExperimentTaskReferenceModel(
            ref_kind="task",
            ref_id=config.task_id,
            ref_version="1.0.0",
        ),
        source_refs=[
            ExperimentReferenceModel(
                ref_kind="protocol",
                ref_id=config.source_protocol_ref_id,
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
            loss_disclosure=config.loss_disclosure,
        ),
        sensitivity="redacted",
        redaction_state="redacted",
        provenance_refs=[
            ExperimentReferenceModel(
                ref_kind="other",
                ref_id=config.provenance_ref_id,
                ref_version=source_revision,
            )
        ],
    )


def _derived_measure(
    config: EvaluatorEvidenceConfig,
    summary: EvaluatorSummary,
    now: str,
    evidence_record_id: str,
) -> ExperimentDerivedMeasureModel:
    """Build the bounded cumulative-reward derived measure."""

    derived_measure_id = scoped_id(config.measure_id_base, summary.projection_ref)
    return ExperimentDerivedMeasureModel(
        schema_version="experiment-derived-measure/v1",
        derived_measure_id=derived_measure_id,
        measure_version="1.0.0",
        measure_kind="score",
        metric_ref=ExperimentReferenceModel(
            ref_kind="metric-definition",
            ref_id=config.metric_ref_id,
            ref_version="1.0.0",
        ),
        method=ExperimentDerivedMeasureMethodModel(
            method_id=config.method_id,
            method_version="1.0.0",
            name=config.method_name,
            description=config.method_description,
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
        value=summary.cumulative_reward,
        uncertainty="No statistical uncertainty is estimated from this single run.",
        limitations=list(config.limitations),
        provenance_refs=[
            ExperimentReferenceModel(
                ref_kind="task",
                ref_id=config.task_id,
                ref_version="1.0.0",
            )
        ],
    )


__all__ = [
    "EvaluatorEvidenceConfig",
    "EvaluatorSummary",
    "build_capture_spec",
    "build_evidence_and_measure",
    "build_evidence_only",
    "scoped_id",
]
