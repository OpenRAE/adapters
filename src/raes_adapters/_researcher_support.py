"""Backend-neutral researcher-run and plan payload builders.

Every gym-backend researcher command seals its episodes into the same published
RAES contracts the same way: it projects an apparatus context, seals an
archival run, groups runs into a declared study, and declares a logical time
model, a bounded orchestration workflow, and an objective evaluation plan. The
*structure* of those payloads is RAES-payload-shaped and identical across
backends; only the backend-local values differ (clock identities, manifest
identities, metric ids, propositions, subjects, and variant selection).

This module is the single shared implementation of that structural boilerplate,
parameterized by the backend-local values the caller supplies. It holds no
backend semantics: CAGE-2's blue/red-variant selection and each gym backend's
single red-attacker selection stay in their own modules and reach these builders
only as explicit arguments.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from importlib import metadata

from raes_contracts.contracts import (  # type: ignore[import-untyped]
    ExperimentArtifactRefModel,
    ExperimentDerivedMeasureModel,
    ExperimentEvidenceRecordModel,
    ExperimentRunModel,
    ExperimentStudyModel,
    ExperimentTaskModel,
    ParticipantConfigurationResultModel,
    ParticipantImplementationManifestModel,
    ParticipantImplementationProvenanceModel,
    ParticipantImplementationSelectionModel,
)
from raes_contracts.contracts.time_model import (  # type: ignore[import-untyped]
    ClockDeclarationModel,
    ExactRatioModel,
    TimeDomainDeclarationModel,
    TimeModelDeclarationModel,
    TimeProgressionPolicyDeclarationModel,
)
from raes_contracts.diagnostics import (  # type: ignore[import-untyped]
    DiagnosticModel,
    diagnostic_model,
)
from raes_contracts.participant_configuration import (  # type: ignore[import-untyped]
    realize_participant_configuration,
    validate_participant_configuration_selection,
)
from raes_contracts.participant_episode import (  # type: ignore[import-untyped]
    ParticipantEpisodeInitializeRequest,
)
from raes_contracts.planning import (  # type: ignore[import-untyped]
    ChangeAction,
    EvaluationOp,
    EvaluationPlan,
    OrchestrationOp,
    OrchestrationPlan,
    PlannedResource,
    RuntimeDomain,
)
from raes_contracts.runtime_state import RuntimeSnapshot  # type: ignore[import-untyped]
from raes_contracts.satisfiability import canonical_contract_digest  # type: ignore[import-untyped]
from raes_runtime.manager import RuntimeManager  # type: ignore[import-untyped]
from raes_runtime.registry import RuntimeTarget  # type: ignore[import-untyped]


@dataclass(frozen=True)
class RedParticipantRunControls(object):
    """Backend-neutral values for one bounded single-red-participant run."""

    run_id: str
    seed: int
    max_steps: int
    red_manifest: ParticipantImplementationManifestModel
    red_selection: ParticipantImplementationSelectionModel
    red_configuration: ParticipantConfigurationResultModel

    def validate_common(self, participant_address: str) -> None:
        """Validate shared scalar and published participant-contract bindings."""

        self._validate_scalars()
        self._validate_bindings(participant_address)
        self._validate_capabilities()

    def _validate_scalars(self) -> None:
        if not 1 <= len(self.run_id) <= 64 or not self.run_id.replace("-", "").isalnum():
            raise ValueError("run id is not a safe label")
        if type(self.seed) is not int or not 0 <= self.seed <= 0xFFFFFFFF:
            raise ValueError("seed is outside the supported range")
        if type(self.max_steps) is not int or self.max_steps < 1:
            raise ValueError("trial length must be positive")

    def _validate_bindings(self, participant_address: str) -> None:
        if self.red_selection.participant_address != participant_address:
            raise ValueError("red implementation selection has the wrong participant address")
        if self.red_manifest.implementation_kind != "policy":
            raise ValueError("red implementation is not an executable policy")
        if self.red_selection.implementation_identity != self.red_manifest.identity:
            raise ValueError("red implementation selection is not bound to its manifest")
        if (
            self.red_configuration.configuration.implementation_identity
            != self.red_manifest.identity
        ):
            raise ValueError("red configuration is not bound to its manifest")
        if self.red_selection.manifest_digest != canonical_contract_digest(self.red_manifest):
            raise ValueError("red implementation manifest digest is invalid")
        validate_participant_configuration_selection(self.red_selection, self.red_configuration)
        realized = realize_participant_configuration(
            participant_address=participant_address,
            manifest=self.red_manifest,
            manifest_ref=self.red_selection.manifest_ref,
            manifest_digest=self.red_selection.manifest_digest,
            overrides=[],
        )
        if realized != self.red_configuration:
            raise ValueError("red configuration is not realized from its admitted manifest")

    def _validate_capabilities(self) -> None:
        if self.red_selection.selected_decision_surface_mode not in (
            self.red_manifest.capabilities.supported_decision_surface_modes
        ):
            raise ValueError("red decision-surface selection is unsupported")
        if not set(self.red_selection.participant_contract_versions) <= set(
            self.red_manifest.capabilities.supported_participant_contracts
        ):
            raise ValueError("red participant contract selection is unsupported")


@dataclass(frozen=True)
class EpisodeEvidence(object):
    """Backend-neutral carrier for already validated RAES episode evidence."""

    completed_steps: int
    evidence_records: tuple[ExperimentEvidenceRecordModel, ...]
    derived_measures: tuple[ExperimentDerivedMeasureModel, ...]
    diagnostics: tuple[DiagnosticModel, ...]
    cleanup_verified: bool


def single_participant_provenance(
    run_id: str,
    selection: ParticipantImplementationSelectionModel,
    backend_manifest_ref: str,
) -> ParticipantImplementationProvenanceModel:
    """Bind one admitted participant selection to an archival run."""

    return ParticipantImplementationProvenanceModel(
        run_id=run_id,
        participant_implementations=[selection],
        backend_manifest_ref=backend_manifest_ref,
        metadata={"selection_source": "admitted-experiment-artifact"},
    )


def manifest_ref(
    ref_id: str, ref_version: str, subject_kind: str, subject_id: str, subject_version: str
) -> dict[str, object]:
    """Build a published manifest reference for archival apparatus context."""

    return {
        "ref_kind": "manifest",
        "ref_id": ref_id,
        "ref_version": ref_version,
        "subject_ref": {
            "ref_kind": subject_kind,
            "ref_id": subject_id,
            "ref_version": subject_version,
        },
    }


def clock_context(clock_id: str, authority: str, time_domain: str = "logical") -> dict[str, object]:
    """Return one archival clock-context payload for a runtime logical clock."""

    return {"clock_id": clock_id, "authority": authority, "time_domain": time_domain}


def seed_stochastic_controls(control_id: str, seed: int) -> list[dict[str, object]]:
    """Return the single-seed stochastic-control declaration used by a run."""

    return [{"control_id": control_id, "role": "seed", "value": seed}]


@dataclass(frozen=True)
class ApparatusContextSpec(object):
    """Backend-local values for one projected apparatus context.

    Every field is an already-published identity or declaration selected by the
    caller; this module never inspects native state.
    """

    run_id: str
    seed: int
    backend_name: str
    backend_version: str
    participant_component_key: str
    participant_identity_name: str
    participant_identity_version: str
    participant_identity_json: dict[str, object]
    compatibility_declarations: list[dict[str, object]]
    configuration_parameters: list[dict[str, object]]
    stochastic_seed_control_id: str
    clock_id: str
    clock_authority: str
    measurement_channel_ref_id: str
    known_limitations: list[dict[str, object]]


def build_apparatus_context(
    spec: ApparatusContextSpec,
    captured_at: object,
    setup_artifact: ExperimentArtifactRefModel,
) -> dict[str, object]:
    """Project admitted apparatus identities without exposing native state."""

    processor_version = metadata.version("raes")
    processor_ref = manifest_ref(
        "raes-runtime-manager",
        "processor-manifest/v2",
        "processor",
        "raes-runtime-manager",
        processor_version,
    )
    backend_ref = manifest_ref(
        spec.backend_name, "backend-manifest/v2", "backend", spec.backend_name, spec.backend_version
    )
    participant_ref = manifest_ref(
        spec.participant_identity_name,
        "participant-implementation-manifest/v1",
        "participant-implementation",
        spec.participant_identity_name,
        spec.participant_identity_version,
    )
    return {
        "schema_version": "experiment-apparatus-context/v1",
        "apparatus_context_id": f"apparatus-{spec.run_id}",
        "context_version": "1.0.0",
        "declared_at": captured_at,
        "components": {
            "processor": {
                "component_kind": "processor",
                "identity": {"name": "raes-runtime-manager", "version": processor_version},
                "manifest_ref": processor_ref,
                "observed": True,
            },
            "backend": {
                "component_kind": "backend",
                "identity": {"name": spec.backend_name, "version": spec.backend_version},
                "manifest_ref": backend_ref,
                "observed": True,
            },
            spec.participant_component_key: {
                "component_kind": "participant-implementation",
                "identity": spec.participant_identity_json,
                "manifest_ref": participant_ref,
                "observed": True,
            },
        },
        "selected_manifests": [processor_ref, backend_ref, participant_ref],
        "compatibility_declarations": spec.compatibility_declarations,
        "configuration_parameters": spec.configuration_parameters,
        "stochastic_controls": seed_stochastic_controls(spec.stochastic_seed_control_id, spec.seed),
        "clocks": [clock_context(spec.clock_id, spec.clock_authority)],
        "measurement_channels": [
            {
                "ref_kind": "measurement-channel",
                "ref_id": spec.measurement_channel_ref_id,
                "ref_version": "1.0.0",
            }
        ],
        "observed_setup_evidence": [setup_artifact.model_dump(mode="json")],
        "known_limitations": spec.known_limitations,
    }


@dataclass(frozen=True)
class ArchivalRunInputs(object):
    """Per-episode inputs the archival run seals into portable evidence."""

    evidence_records: tuple[ExperimentEvidenceRecordModel, ...]
    derived_measures: tuple[ExperimentDerivedMeasureModel, ...]
    evidence_artifact: ExperimentArtifactRefModel
    scenario_digest: str
    task: ExperimentTaskModel


@dataclass(frozen=True)
class ArchivalRunSpec(object):
    """Backend-local scalars that shape the archival run payload."""

    parameter_set: list[dict[str, object]]
    seed: int
    stochastic_seed_control_id: str
    clock_id: str
    clock_authority: str
    result_summary_key: str
    metric_id: str


def build_single_participant_archival_run(
    episode: EpisodeEvidence,
    evidence_artifact: ExperimentArtifactRefModel,
    scenario_digest: str,
    task: ExperimentTaskModel,
    *,
    apparatus_context: Callable[[object, ExperimentArtifactRefModel], dict[str, object]],
    provenance: Callable[[str], dict[str, object]],
    spec: ArchivalRunSpec,
) -> ExperimentRunModel:
    """Seal the common evidence and parameter surface of a single-participant run."""

    return build_archival_run(
        ArchivalRunInputs(
            evidence_records=episode.evidence_records,
            derived_measures=episode.derived_measures,
            evidence_artifact=evidence_artifact,
            scenario_digest=scenario_digest,
            task=task,
        ),
        apparatus_context=apparatus_context,
        provenance=provenance,
        spec=spec,
    )


def start_single_participant_runtime(
    target: RuntimeTarget,
    scenario: object,
    orchestration_plan: OrchestrationPlan,
) -> tuple[RuntimeSnapshot, list[DiagnosticModel]]:
    """Provision and start a backend-supplied single-participant plan."""

    manager = RuntimeManager(target)
    execution_plan = manager.plan(scenario)
    diagnostics = [diagnostic_model(item) for item in execution_plan.diagnostics]
    if (
        any(item.is_error for item in execution_plan.diagnostics)
        or target.provisioner is None
        or target.orchestrator is None
    ):
        raise RuntimeError("researcher runtime admission failed")
    provisioned = target.provisioner.apply(
        execution_plan.provisioning, execution_plan.base_snapshot
    )
    diagnostics.extend(diagnostic_model(item) for item in provisioned.diagnostics)
    if not provisioned.success:
        raise RuntimeError("researcher provisioning admission failed")
    started = target.orchestrator.start(orchestration_plan, provisioned.snapshot)
    diagnostics.extend(diagnostic_model(item) for item in started.diagnostics)
    if not started.success or target.participant_runtime is None or target.evaluator is None:
        raise RuntimeError("researcher orchestration admission failed")
    return started.snapshot, diagnostics


def initialize_single_participant(
    target: RuntimeTarget,
    snapshot: RuntimeSnapshot,
    participant_address: str,
    episode_id: str,
    diagnostics: list[DiagnosticModel],
) -> RuntimeSnapshot:
    """Initialize one backend-supplied participant through the published runtime."""

    if target.participant_runtime is None:
        raise RuntimeError("researcher participant runtime is unavailable")
    initialized = target.participant_runtime.initialize(
        ParticipantEpisodeInitializeRequest(
            participant_address=participant_address,
            episode_id=episode_id,
        ),
        snapshot,
    )
    diagnostics.extend(diagnostic_model(item) for item in initialized.diagnostics)
    if not initialized.success:
        raise RuntimeError("researcher participant admission failed")
    return initialized.snapshot


def build_archival_run(
    inputs: ArchivalRunInputs,
    *,
    apparatus_context: Callable[[object, ExperimentArtifactRefModel], dict[str, object]],
    provenance: Callable[[str], dict[str, object]],
    spec: ArchivalRunSpec,
) -> ExperimentRunModel:
    """Seal one episode in the published archival run contract.

    ``apparatus_context`` and ``provenance`` are backend-local closures invoked
    once the shared episode identities are resolved: the former receives the
    resolved ``captured_at`` and setup artifact, the latter the resolved run id.
    """

    evidence_records = inputs.evidence_records
    derived_measures = inputs.derived_measures
    evidence_artifact = inputs.evidence_artifact
    task = inputs.task
    if not evidence_records or not derived_measures:
        raise ValueError("portable evidence is incomplete")
    run_id = evidence_records[0].run_ref.ref_id
    if not isinstance(run_id, str):
        raise ValueError("portable run identity is incomplete")
    captured_at = evidence_records[0].captured_at
    generated_at = derived_measures[-1].generated_at
    setup_artifact = evidence_artifact.model_copy(
        update={"artifact_id": "researcher-setup-evidence", "role": "apparatus-evidence"}
    )
    measure = derived_measures[-1]
    payload: dict[str, object] = {
        "schema_version": "experiment-run/v1",
        "run_id": run_id,
        "run_version": "1.0.0",
        "task_ref": {"ref_kind": "task", "ref_id": task.task_id, "ref_version": task.task_version},
        "scenario_snapshot_ref": {
            "ref_kind": "scenario-snapshot",
            "ref_id": task.scenario_ref.ref_id,
            "ref_digest": inputs.scenario_digest,
            "ref_path": task.scenario_ref.ref_path,
        },
        "apparatus_context": apparatus_context(captured_at, setup_artifact),
        "participant_implementation_provenance": provenance(run_id),
        "parameter_set": spec.parameter_set,
        "stochastic_controls": seed_stochastic_controls(spec.stochastic_seed_control_id, spec.seed),
        "started_at": captured_at,
        "ended_at": generated_at,
        "clock_context": clock_context(spec.clock_id, spec.clock_authority),
        "run_status": "sealed",
        "outcome_status": "succeeded",
        "traceability": {
            "capture_spec_refs": [evidence_records[0].capture_spec_ref.model_dump(mode="json")],
            "evidence_record_refs": [
                {
                    "ref_kind": "evidence-record",
                    "ref_id": item.evidence_record_id,
                    "ref_version": item.record_version,
                }
                for item in evidence_records
            ],
            "derived_measure_refs": [
                {
                    "ref_kind": "derived-measure",
                    "ref_id": item.derived_measure_id,
                    "ref_version": item.measure_version,
                }
                for item in derived_measures
            ],
        },
        "evidence_artifacts": [evidence_artifact.model_dump(mode="json")],
        "result_summaries": {
            spec.result_summary_key: {
                "metric_id": spec.metric_id,
                "value": measure.value,
                "value_status": measure.value_status,
                "evidence_refs": [
                    {"ref_kind": "evidence", "ref_id": evidence_artifact.artifact_id}
                ],
            }
        },
    }
    return ExperimentRunModel.model_validate(payload)


def build_archival_collection(
    task: ExperimentTaskModel,
    runs: Sequence[ExperimentRunModel],
    study_id: str,
    *,
    title: str,
) -> ExperimentStudyModel:
    """Group a declared run batch without introducing a scientific claim."""

    membership: dict[str, object] = {
        "task": {
            "target_ref": {
                "ref_kind": "task",
                "ref_id": task.task_id,
                "ref_version": task.task_version,
            },
            "role": "primary-task",
            "inclusion_rationale": "Task selected by the admitted experiment authoring input.",
        }
    }
    for index, run in enumerate(runs, start=1):
        membership[f"run-{index}"] = {
            "target_ref": {"ref_kind": "run", "ref_id": run.run_id, "ref_version": run.run_version},
            "role": "evaluation-run",
            "grouping": "declared-study",
        }
    return ExperimentStudyModel(
        schema_version="experiment-study/v1",
        study_id=study_id,
        study_version="1.0.0",
        study_kind="collection",
        title=title,
        owner="RAES adapters",
        description="Portable grouping of the exact runs admitted by the packaged authoring input.",
        purpose="Retain batch membership without adding an empirical or equivalence claim.",
        membership=membership,
        inclusion_criteria=[
            "Only sealed runs from the exact admitted pack, scenario, task, and control selection."
        ],
    )


def logical_time_declaration(
    *,
    clock: str,
    domain: str,
    policy: str,
    authority_ref: str,
    domain_description: str,
    clock_description: str,
    policy_description: str,
) -> TimeModelDeclarationModel:
    """Return a RAES-owned logical step-clock time model for one backend."""

    return TimeModelDeclarationModel(
        domains={
            domain: TimeDomainDeclarationModel(
                address=domain,
                kind="logical",
                tick_period_seconds=ExactRatioModel(numerator=1, denominator=1),
                epoch="run_start",
                visibility="runtime_only",
                description=domain_description,
            )
        },
        clocks={
            clock: ClockDeclarationModel(
                address=clock,
                time_domain_address=domain,
                authority_kind="runtime",
                authority_ref=authority_ref,
                monotonicity="non_decreasing",
                supports_pause=True,
                supports_reset=True,
                supports_jump=False,
                description=clock_description,
            )
        },
        progression_policies={
            policy: TimeProgressionPolicyDeclarationModel(
                address=policy,
                clock_address=clock,
                advancement_mode="event_driven",
                synchronization_mode="none",
                reset_behavior="new_segment_zero",
                replay_behavior="unsupported",
                description=policy_description,
            )
        },
    )


def orchestration_plan(
    *,
    workflow: str,
    name: str,
    episode_control: dict[str, object],
    extra_payload: dict[str, object] | None = None,
) -> OrchestrationPlan:
    """Return a bounded workflow through the RAES orchestration contract.

    ``extra_payload`` carries backend-local top-level payload entries (e.g. a
    CAGE-2 red-variant selection) that a backend with no such selection omits.
    """

    payload: dict[str, object] = {
        "name": name,
        "episode_control": episode_control,
        **(extra_payload or {}),
        "result_contract": {
            "state_schema_version": "workflow-step-state/v1",
            "observable_steps": {},
        },
        "execution_contract": {
            "state_schema_version": "workflow-step-state/v1",
            "start_step": "",
            "steps": {},
            "step_types": {},
            "control_edges": {},
            "join_owners": {},
            "call_steps": {},
            "observable_steps": [],
        },
    }
    operation = OrchestrationOp(
        action=ChangeAction.CREATE,
        address=workflow,
        resource_type="workflow",
        payload=payload,
    )
    return OrchestrationPlan(
        resources={
            workflow: PlannedResource(
                address=workflow,
                domain=RuntimeDomain.ORCHESTRATION,
                resource_type="workflow",
                payload=payload,
            )
        },
        operations=[operation],
        startup_order=[workflow],
    )


def objective_evaluation_plan(
    *,
    proposition: str,
    assertion: str,
    objective: str,
    subject_addresses: list[str],
    evidence_requirement_refs: list[str],
    predicate: dict[str, object],
    include_execution_contract: bool = True,
) -> EvaluationPlan:
    """Return a single-objective evaluation plan over projected evidence."""

    objective_payload: dict[str, object] = {
        "success_addresses": [assertion],
        "spec": {"success": {"mode": "all"}},
        "result_contract": {
            "resource_type": "objective",
            "supports_passed": True,
            "supports_score": False,
        },
    }
    if include_execution_contract:
        objective_payload["execution_contract"] = {
            "resource_type": "objective",
            "allowed_statuses": ["pending", "running", "ready", "failed"],
            "history_event_types": [
                "evaluation_started",
                "evaluation_updated",
                "evaluation_ready",
                "evaluation_failed",
            ],
            "requires_start_event": True,
        }
    operations = [
        EvaluationOp(
            action=ChangeAction.CREATE,
            address=proposition,
            resource_type="proposition",
            payload={
                "evaluation_basis": "observed_state",
                "subject_addresses": subject_addresses,
                "evidence_requirement_refs": evidence_requirement_refs,
                "spec": {"predicate": predicate},
            },
        ),
        EvaluationOp(
            action=ChangeAction.CREATE,
            address=assertion,
            resource_type="assertion",
            payload={"proposition_address": proposition, "polarity": "positive"},
        ),
        EvaluationOp(
            action=ChangeAction.CREATE,
            address=objective,
            resource_type="objective",
            payload=objective_payload,
        ),
    ]
    return EvaluationPlan(operations=operations, startup_order=[proposition, assertion, objective])


__all__ = [
    "ApparatusContextSpec",
    "build_apparatus_context",
    "build_archival_collection",
    "build_archival_run",
    "clock_context",
    "logical_time_declaration",
    "manifest_ref",
    "objective_evaluation_plan",
    "orchestration_plan",
    "seed_stochastic_controls",
]
