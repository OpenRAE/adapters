"""Researcher-run orchestration over published RAES runtime contracts."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

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
from raes_contracts.diagnostics import (  # type: ignore[import-untyped]
    DiagnosticModel,
    diagnostic_model,
)
from raes_contracts.participant_action_arguments import (  # type: ignore[import-untyped]
    ParticipantValidatedActionSelection,
)
from raes_contracts.participant_binding import (  # type: ignore[import-untyped]
    ParticipantActionAdmissionRequest,
)
from raes_contracts.participant_configuration import (  # type: ignore[import-untyped]
    realize_participant_configuration,
    validate_participant_configuration_selection,
)
from raes_contracts.participant_episode import (  # type: ignore[import-untyped]
    ParticipantEpisodeInitializeRequest,
)
from raes_contracts.planning import (  # type: ignore[import-untyped]
    EvaluationPlan,
    OrchestrationPlan,
)
from raes_contracts.runtime_state import RuntimeSnapshot  # type: ignore[import-untyped]
from raes_contracts.satisfiability import canonical_contract_digest  # type: ignore[import-untyped]
from raes_runtime.manager import RuntimeManager  # type: ignore[import-untyped]
from raes_runtime.registry import RuntimeTarget  # type: ignore[import-untyped]

from raes_adapters._researcher_support import (
    ApparatusContextSpec,
    ArchivalRunInputs,
    ArchivalRunSpec,
    build_apparatus_context,
    build_archival_collection,
    build_archival_run,
)

from .driver import CyborgDriver
from .manifest import create_cyborg_manifest
from .runtime_plans import (
    cage2_evaluation_plan,
    cage2_orchestration_plan,
    cage2_time_declaration,
)
from .target import create_cyborg_target

_BLUE = "participant.behavior.blue"
_GREEN = "participant.behavior.green"
_RED = "participant.behavior.red"
_SLEEP = "participant.action-contract.sleep"
_RED_VARIANTS = frozenset({"b-line", "meander", "sleep"})
_OBSERVATION_BOUNDARY = "participant.observation-boundary.blue"


@dataclass(frozen=True)
class RunControls(object):
    """Internal, non-portable selection of already published run controls."""

    run_id: str
    seed: int
    max_steps: int
    red_variant: str
    blue_manifest: ParticipantImplementationManifestModel
    blue_selection: ParticipantImplementationSelectionModel
    blue_configuration: ParticipantConfigurationResultModel

    def __post_init__(self) -> None:
        """Reject controls not bound to the selected published contracts."""

        self._validate_scalars()
        self._validate_bindings()
        self._validate_capabilities()
        _blue_action_contract(self.blue_configuration)

    def _validate_scalars(self) -> None:
        """Validate safe scalar controls before native execution."""

        if not 1 <= len(self.run_id) <= 64 or not self.run_id.replace("-", "").isalnum():
            raise ValueError("run id is not a safe label")
        if type(self.seed) is not int or not 0 <= self.seed <= 0xFFFFFFFF:
            raise ValueError("seed is outside the supported range")
        if type(self.max_steps) is not int or self.max_steps < 1:
            raise ValueError("trial length must be positive")
        if self.red_variant not in _RED_VARIANTS:
            raise ValueError("red variant is unsupported")

    def _validate_bindings(self) -> None:
        """Validate participant identity and realized configuration bindings."""

        if self.blue_selection.participant_address != _BLUE:
            raise ValueError("blue implementation selection has the wrong participant address")
        if self.blue_manifest.implementation_kind != "policy":
            raise ValueError("blue implementation is not an executable policy")
        if self.blue_selection.implementation_identity != self.blue_manifest.identity:
            raise ValueError("blue implementation selection is not bound to its manifest")
        if (
            self.blue_configuration.configuration.implementation_identity
            != self.blue_manifest.identity
        ):
            raise ValueError("blue configuration is not bound to its manifest")
        if self.blue_selection.manifest_digest != canonical_contract_digest(self.blue_manifest):
            raise ValueError("blue implementation manifest digest is invalid")
        validate_participant_configuration_selection(self.blue_selection, self.blue_configuration)
        realized = realize_participant_configuration(
            participant_address=_BLUE,
            manifest=self.blue_manifest,
            manifest_ref=self.blue_selection.manifest_ref,
            manifest_digest=self.blue_selection.manifest_digest,
            overrides=[],
        )
        if realized != self.blue_configuration:
            raise ValueError("blue configuration is not realized from its admitted manifest")

    def _validate_capabilities(self) -> None:
        """Validate the selected participant surfaces against its manifest."""

        if self.blue_selection.selected_decision_surface_mode not in (
            self.blue_manifest.capabilities.supported_decision_surface_modes
        ):
            raise ValueError("blue decision-surface selection is unsupported")
        if not set(self.blue_selection.participant_contract_versions) <= set(
            self.blue_manifest.capabilities.supported_participant_contracts
        ):
            raise ValueError("blue participant contract selection is unsupported")


@dataclass(frozen=True)
class EpisodeEvidence(object):
    """Internal carrier for already validated RAES evidence models."""

    completed_steps: int
    evidence_records: tuple[ExperimentEvidenceRecordModel, ...]
    derived_measures: tuple[ExperimentDerivedMeasureModel, ...]
    proposition_truth_results: dict[str, dict[str, object]]
    objective_results: dict[str, dict[str, object]]
    diagnostics: tuple[DiagnosticModel, ...]
    cleanup_verified: bool


def blue_implementation_provenance(
    run_id: str, selection: ParticipantImplementationSelectionModel
) -> ParticipantImplementationProvenanceModel:
    """Return canonical participant provenance for one researcher run."""

    return ParticipantImplementationProvenanceModel(
        run_id=run_id,
        participant_implementations=[selection],
        backend_manifest_ref="manifest.cyborg-cage2",
        metadata={"selection_source": "admitted-experiment-artifact"},
    )


def _apparatus_context(
    controls: RunControls,
    captured_at: object,
    setup_artifact: ExperimentArtifactRefModel,
) -> dict[str, object]:
    """Project admitted apparatus identities without exposing native state."""

    backend = create_cyborg_manifest()
    blue = controls.blue_manifest
    spec = ApparatusContextSpec(
        run_id=controls.run_id,
        seed=controls.seed,
        backend_name=backend.name,
        backend_version=backend.version,
        participant_component_key="blue-policy",
        participant_identity_name=blue.identity.name,
        participant_identity_version=blue.identity.version,
        participant_identity_json=blue.identity.model_dump(mode="json"),
        compatibility_declarations=[
            {
                "ref_kind": "profile",
                "ref_id": "cage2-cyborg-2.1-source-26ce1c1",
                "ref_version": "26ce1c1253fa9e2e73f25e6a7f2da32860c11257",
            }
        ],
        configuration_parameters=[
            {"name": "red-variant", "value": controls.red_variant, "value_kind": "protocol"}
        ],
        stochastic_seed_control_id="cyborg-seed",
        clock_id="cage2-logical-clock",
        clock_authority="cyborg-cage2 runtime",
        measurement_channel_ref_id="cyborg-reward-projection",
        known_limitations=[
            {
                "category": "apparatus",
                "note": "Native internals are withheld at the adapter boundary.",
            }
        ],
    )
    return build_apparatus_context(spec, captured_at, setup_artifact)


def archival_run(
    *,
    controls: RunControls,
    scenario_digest: str,
    task: ExperimentTaskModel,
    episode: EpisodeEvidence,
    evidence_artifact: ExperimentArtifactRefModel,
) -> ExperimentRunModel:
    """Seal one episode in the published archival run contract."""

    return build_archival_run(
        ArchivalRunInputs(
            evidence_records=episode.evidence_records,
            derived_measures=episode.derived_measures,
            evidence_artifact=evidence_artifact,
            scenario_digest=scenario_digest,
            task=task,
        ),
        apparatus_context=lambda captured_at, setup_artifact: _apparatus_context(
            controls, captured_at, setup_artifact
        ),
        provenance=lambda run_id: blue_implementation_provenance(
            run_id, controls.blue_selection
        ).model_dump(mode="json"),
        spec=ArchivalRunSpec(
            parameter_set=[
                {"name": "red-variant", "value": controls.red_variant, "value_kind": "protocol"},
                {
                    "name": "blue-implementation",
                    "value": controls.blue_manifest.identity.name,
                    "value_kind": "apparatus",
                },
                {"name": "trial-length", "value": controls.max_steps, "value_kind": "protocol"},
            ],
            seed=controls.seed,
            stochastic_seed_control_id="cyborg-seed",
            clock_id="cage2-logical-clock",
            clock_authority="cyborg-cage2 runtime",
            result_summary_key="cage2-cumulative-blue-reward-result",
            metric_id="cage2-cumulative-blue-reward",
        ),
    )


def archival_collection(
    task: ExperimentTaskModel, runs: Sequence[ExperimentRunModel], study_id: str
) -> ExperimentStudyModel:
    """Group a declared run batch without introducing a scientific claim."""

    return build_archival_collection(task, runs, study_id, title="CAGE-2 declared run collection")


def _blue_action_contract(configuration: ParticipantConfigurationResultModel) -> str:
    """Return the executable action selected by an admitted configuration."""

    values = {
        item.target_id: item.value.value
        for item in configuration.configuration.values
        if item.value.kind == "literal"
    }
    selected = values.get("blue-action-contract-address")
    if not isinstance(selected, str) or selected != _SLEEP:
        raise ValueError("blue participant configuration has no installed executable behavior")
    return selected


def _blue_action_request(
    action_instance_id: str, controls: RunControls
) -> ParticipantActionAdmissionRequest:
    """Build one action request bound to the selected blue implementation."""

    action_contract = _blue_action_contract(controls.blue_configuration)
    return ParticipantActionAdmissionRequest(
        participant_address=_BLUE,
        action_contract_address=action_contract,
        observation_boundary_address=_OBSERVATION_BOUNDARY,
        action_instance_id=action_instance_id,
        implementation_manifest=controls.blue_manifest,
        implementation_selection=controls.blue_selection,
        visible_refs=(_OBSERVATION_BOUNDARY,),
        disclosed_refs=(_OBSERVATION_BOUNDARY,),
        validated_selection=ParticipantValidatedActionSelection(
            action_contract_address=action_contract,
            argument_shape_ref="participant.action-argument-shape.cage2",
            proposal_ref=f"proposal:{action_instance_id}",
            normalized_arguments=(),
            loss_disclosure_refs=("loss-observation-abstraction",),
        ),
        requires_terminal_outcome=True,
    )


def _orchestration_plan(controls: RunControls) -> OrchestrationPlan:
    """Return the bounded workflow for one admitted researcher run."""

    workflow = f"orchestration.workflow.{controls.run_id}"
    return cage2_orchestration_plan(
        workflow=workflow,
        name="cage2-research-run",
        max_steps=controls.max_steps,
        red_variant=controls.red_variant,
    )


def _start_runtime(
    target: RuntimeTarget, scenario: object, controls: RunControls
) -> tuple[RuntimeSnapshot, list[DiagnosticModel], EvaluationPlan]:
    """Apply the scenario, logical clock, and bounded workflow."""

    manager = RuntimeManager(target)
    planned = manager.plan(scenario)
    applied = manager.apply(planned)
    diagnostics = [diagnostic_model(item) for item in applied.diagnostics]
    if not applied.success or target.time_runtime is None or target.orchestrator is None:
        raise RuntimeError("researcher runtime admission failed")
    timed = target.time_runtime.initialize(cage2_time_declaration(), applied.snapshot)
    diagnostics.extend(diagnostic_model(item) for item in timed.diagnostics)
    if not timed.success:
        raise RuntimeError("researcher time admission failed")
    started = target.orchestrator.start(_orchestration_plan(controls), timed.snapshot)
    diagnostics.extend(diagnostic_model(item) for item in started.diagnostics)
    if not started.success or target.participant_runtime is None or target.evaluator is None:
        raise RuntimeError("researcher orchestration admission failed")
    evaluation = planned.evaluation
    if not evaluation.resources:
        evaluation = cage2_evaluation_plan()
    return started.snapshot, diagnostics, evaluation


def _initialize_participants(
    target: RuntimeTarget,
    snapshot: RuntimeSnapshot,
    controls: RunControls,
    diagnostics: list[DiagnosticModel],
) -> RuntimeSnapshot:
    """Initialize every aggregate participant through the published runtime."""

    if target.participant_runtime is None:
        raise RuntimeError("researcher participant runtime is unavailable")
    for participant in (_BLUE, _GREEN, _RED):
        initialized = target.participant_runtime.initialize(
            ParticipantEpisodeInitializeRequest(
                participant_address=participant,
                episode_id=f"{controls.run_id}-{participant.rsplit('.', 1)[-1]}",
            ),
            snapshot,
        )
        diagnostics.extend(diagnostic_model(item) for item in initialized.diagnostics)
        if not initialized.success:
            raise RuntimeError("researcher participant admission failed")
        snapshot = initialized.snapshot
    return snapshot


def _execute_steps(
    target: RuntimeTarget,
    snapshot: RuntimeSnapshot,
    controls: RunControls,
    diagnostics: list[DiagnosticModel],
) -> tuple[RuntimeSnapshot, int]:
    """Execute the admitted action until the declared terminal boundary."""

    if target.participant_runtime is None or target.orchestrator is None:
        raise RuntimeError("researcher execution runtime is unavailable")
    completed_steps = 0
    for step in range(1, controls.max_steps + 1):
        action = target.participant_runtime.admit_action(
            _blue_action_request(f"{controls.run_id}-blue-action-{step}", controls), snapshot
        )
        diagnostics.extend(diagnostic_model(item) for item in action.diagnostics)
        if not action.success:
            raise RuntimeError("researcher participant action failed")
        snapshot = action.snapshot
        completed_steps = step
        if target.orchestrator.status()["running"] is False:
            break
    return snapshot, completed_steps


def _evaluate_episode(
    target: RuntimeTarget,
    snapshot: RuntimeSnapshot,
    diagnostics: list[DiagnosticModel],
    evaluation_plan: EvaluationPlan,
) -> tuple[
    RuntimeSnapshot,
    tuple[ExperimentEvidenceRecordModel, ...],
    tuple[ExperimentDerivedMeasureModel, ...],
]:
    """Evaluate the final portable snapshot and return published evidence."""

    if target.evaluator is None:
        raise RuntimeError("researcher evaluator is unavailable")
    evaluated = target.evaluator.start(evaluation_plan, snapshot)
    diagnostics.extend(diagnostic_model(item) for item in evaluated.diagnostics)
    if not evaluated.success:
        raise RuntimeError("researcher evaluation failed")
    return (
        evaluated.snapshot,
        target.evaluator.evidence_records(),
        target.evaluator.derived_measures(),
    )


def execute_episode(
    scenario: object,
    controls: RunControls,
    *,
    driver: CyborgDriver | None = None,
) -> EpisodeEvidence:
    """Execute one selected episode and return only validated RAES evidence."""

    target = create_cyborg_target(
        scenario=scenario,
        seed=controls.seed,
        **({"driver": driver} if driver else {}),
    )
    snapshot, diagnostics, evaluation_plan = _start_runtime(target, scenario, controls)
    completed_steps = 0
    cleanup_verified = False
    evidence_records: tuple[ExperimentEvidenceRecordModel, ...] = ()
    derived_measures: tuple[ExperimentDerivedMeasureModel, ...] = ()
    try:
        snapshot = _initialize_participants(target, snapshot, controls, diagnostics)
        snapshot, completed_steps = _execute_steps(target, snapshot, controls, diagnostics)
        snapshot, evidence_records, derived_measures = _evaluate_episode(
            target, snapshot, diagnostics, evaluation_plan
        )
    finally:
        cleanup = RuntimeManager(target, initial_snapshot=snapshot).destroy()
        diagnostics.extend(diagnostic_model(item) for item in cleanup.diagnostics)
        cleanup_verified = cleanup.success
    if not cleanup_verified:
        raise RuntimeError("researcher cleanup failed")
    return EpisodeEvidence(
        completed_steps=completed_steps,
        evidence_records=evidence_records,
        derived_measures=derived_measures,
        proposition_truth_results={
            address: dict(payload)
            for address, payload in snapshot.proposition_truth_results.items()
        },
        objective_results={
            address: dict(payload) for address, payload in snapshot.evaluation_results.items()
        },
        diagnostics=tuple(diagnostics),
        cleanup_verified=cleanup_verified,
    )


__all__ = [
    "EpisodeEvidence",
    "RunControls",
    "archival_collection",
    "archival_run",
    "blue_implementation_provenance",
    "execute_episode",
]
