"""NASim researcher-run orchestration over published RAES runtime contracts.

This mirrors the CAGE-2 researcher command for the selected NASim ``tiny``
static benchmark, adapted to a single red bruteforce attacker with no
red-variant, no defender, and no second participant. Determinism loss is
retained as a non-claim: action success is drawn from the process-global legacy
NumPy stream, which neither ``make_benchmark`` nor the gym reset seed binds for a
static benchmark (ADR-069), so a bound seed is never a deterministic-replay
claim.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

from raes_backend_protocols.manifest import (  # type: ignore[import-untyped]
    backend_manifest_payload,
)
from raes_contracts.backend_profiles import (  # type: ignore[import-untyped]
    backend_profiles_root,
    load_backend_profile,
)
from raes_contracts.contracts import (  # type: ignore[import-untyped]
    ExperimentArtifactRefModel,
    ExperimentDerivedMeasureModel,
    ExperimentEvidenceRecordModel,
    ExperimentRunModel,
    ExperimentStudyModel,
    ExperimentTaskModel,
    ParticipantConfigurationResultModel,
    ParticipantImplementationProvenanceModel,
    ParticipantImplementationSelectionModel,
)
from raes_contracts.diagnostics import (  # type: ignore[import-untyped]
    DiagnosticModel,
    diagnostic_model,
    diagnostic_payload,
)
from raes_contracts.participant_action_arguments import (  # type: ignore[import-untyped]
    ParticipantValidatedActionSelection,
)
from raes_contracts.participant_binding import (  # type: ignore[import-untyped]
    ParticipantActionAdmissionRequest,
)
from raes_contracts.planning import OrchestrationPlan  # type: ignore[import-untyped]
from raes_contracts.runtime_state import RuntimeSnapshot  # type: ignore[import-untyped]
from raes_operations.realization_conformance import (  # type: ignore[import-untyped]
    write_backend_conformance_report,
)
from raes_runtime.manager import RuntimeManager  # type: ignore[import-untyped]
from raes_runtime.registry import RuntimeTarget  # type: ignore[import-untyped]

from raes_adapters._manifest_support import read_source_revision
from raes_adapters._researcher_support import (
    ApparatusContextSpec,
    ArchivalRunSpec,
    EpisodeEvidence,
    RedParticipantRunControls,
    build_apparatus_context,
    build_archival_collection,
    build_single_participant_archival_run,
    initialize_single_participant,
    single_participant_provenance,
    start_single_participant_runtime,
)
from raes_adapters.nasim import load_qualification
from raes_adapters.nasim.backend.conformance import (
    PR_CONFORMANCE_SEED,
    nasim_backend_conformance_payload,
    nasim_declared_weaknesses,
    nasim_manifest_capability_gaps,
    nasim_source_protocol_diagnostics,
    run_nasim_conformance,
)
from raes_adapters.nasim.backend.driver import NasimDriverProtocol, verify_selected_nasim_source
from raes_adapters.nasim.backend.manifest import create_nasim_manifest
from raes_adapters.nasim.backend.target import create_nasim_target
from raes_adapters.nasim.runtime_plans import (
    NASIM_CLOCK,
    nasim_evaluation_plan,
    nasim_orchestration_plan,
)
from raes_adapters.nasim.scenario_ledger import NASIM_TINY

_RED = "participant.behavior.red"
_SERVICE_EXPLOIT = "participant.action-contract.service-exploit"
_OBSERVATION_BOUNDARY = "participant.observation-boundary.red"
_ACTION_CONTRACT_TARGET = "red-action-contract-address"
_BACKEND_MANIFEST_REF = "manifest.nasim-tiny"
_ACTION_ARGUMENT_SHAPE = "participant.action-argument-shape.nasim"


@dataclass(frozen=True)
class RunControls(RedParticipantRunControls):
    """Internal, non-portable selection of already published run controls.

    Bound to the single red bruteforce attacker; there is no red-variant, no
    blue, and no green participant for the selected tiny scenario.
    """

    def __post_init__(self) -> None:
        """Reject controls not bound to the selected published contracts."""

        self.validate_common(_RED)
        _red_action_contract(self.red_configuration)


def red_implementation_provenance(
    run_id: str, selection: ParticipantImplementationSelectionModel
) -> ParticipantImplementationProvenanceModel:
    """Return canonical participant provenance for one researcher run."""

    return single_participant_provenance(run_id, selection, _BACKEND_MANIFEST_REF)


def _apparatus_context(
    controls: RunControls,
    captured_at: object,
    setup_artifact: ExperimentArtifactRefModel,
) -> dict[str, object]:
    """Project admitted apparatus identities without exposing native state."""

    backend = create_nasim_manifest()
    red = controls.red_manifest
    source_revision = read_source_revision(load_qualification)
    spec = ApparatusContextSpec(
        run_id=controls.run_id,
        seed=controls.seed,
        backend_name=backend.name,
        backend_version=backend.version,
        participant_component_key="red-policy",
        participant_identity_name=red.identity.name,
        participant_identity_version=red.identity.version,
        participant_identity_json=red.identity.model_dump(mode="json"),
        compatibility_declarations=[
            {
                "ref_kind": "profile",
                "ref_id": f"nasim-tiny-static-benchmark-{source_revision[:7]}",
                "ref_version": source_revision,
            }
        ],
        configuration_parameters=[
            {
                "name": "red-action-contract",
                "value": _red_action_contract(controls.red_configuration),
                "value_kind": "protocol",
            }
        ],
        stochastic_seed_control_id="nasim-gym-reset-seed",
        clock_id=NASIM_CLOCK,
        clock_authority="nasim-tiny runtime",
        measurement_channel_ref_id="nasim-reward-projection",
        known_limitations=[
            {
                "category": "apparatus",
                "note": "Native internals are withheld at the adapter boundary.",
            },
            {
                "category": "internal",
                "note": (
                    "Action success is drawn from the unbound global NumPy stream; a bound "
                    "seed is not a deterministic-replay claim (ADR-069)."
                ),
            },
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

    return build_single_participant_archival_run(
        episode,
        evidence_artifact,
        scenario_digest,
        task,
        apparatus_context=lambda captured_at, setup_artifact: _apparatus_context(
            controls, captured_at, setup_artifact
        ),
        provenance=lambda run_id: red_implementation_provenance(
            run_id, controls.red_selection
        ).model_dump(mode="json"),
        spec=ArchivalRunSpec(
            parameter_set=[
                {
                    "name": "red-implementation",
                    "value": controls.red_manifest.identity.name,
                    "value_kind": "apparatus",
                },
                {"name": "trial-length", "value": controls.max_steps, "value_kind": "protocol"},
            ],
            seed=controls.seed,
            stochastic_seed_control_id="nasim-gym-reset-seed",
            clock_id=NASIM_CLOCK,
            clock_authority="nasim-tiny runtime",
            result_summary_key="nasim-cumulative-attacker-reward-result",
            metric_id="cumulative_attacker_reward",
        ),
    )


def archival_collection(
    task: ExperimentTaskModel, runs: Sequence[ExperimentRunModel], study_id: str
) -> ExperimentStudyModel:
    """Group a declared run batch without introducing a scientific claim."""

    return build_archival_collection(
        task, runs, study_id, title="NASim tiny declared run collection"
    )


def _red_action_contract(configuration: ParticipantConfigurationResultModel) -> str:
    """Return the executable action selected by an admitted configuration."""

    values = {
        item.target_id: item.value.value
        for item in configuration.configuration.values
        if item.value.kind == "literal"
    }
    selected = values.get(_ACTION_CONTRACT_TARGET)
    if not isinstance(selected, str) or selected != _SERVICE_EXPLOIT:
        raise ValueError("red participant configuration has no installed executable behavior")
    return selected


def _red_action_request(
    action_instance_id: str, controls: RunControls
) -> ParticipantActionAdmissionRequest:
    """Build one action request bound to the selected red implementation."""

    action_contract = _red_action_contract(controls.red_configuration)
    return ParticipantActionAdmissionRequest(
        participant_address=_RED,
        action_contract_address=action_contract,
        observation_boundary_address=_OBSERVATION_BOUNDARY,
        action_instance_id=action_instance_id,
        implementation_manifest=controls.red_manifest,
        implementation_selection=controls.red_selection,
        visible_refs=(_OBSERVATION_BOUNDARY,),
        disclosed_refs=(_OBSERVATION_BOUNDARY,),
        validated_selection=ParticipantValidatedActionSelection(
            action_contract_address=action_contract,
            argument_shape_ref=_ACTION_ARGUMENT_SHAPE,
            proposal_ref=f"proposal:{action_instance_id}",
            normalized_arguments=(),
            loss_disclosure_refs=("loss-observation-abstraction",),
        ),
        requires_terminal_outcome=True,
    )


def _orchestration_plan(controls: RunControls) -> OrchestrationPlan:
    """Return the bounded single-attacker workflow for one admitted run."""

    workflow = f"orchestration.workflow.{controls.run_id}"
    return nasim_orchestration_plan(
        workflow=workflow,
        name="nasim-tiny-research-run",
        max_steps=controls.max_steps,
    )


def _start_runtime(
    target: RuntimeTarget, scenario: object, controls: RunControls
) -> tuple[RuntimeSnapshot, list[DiagnosticModel]]:
    """Realize the scenario topology and start the bounded single-attacker workflow.

    The selected NASim backend ships no time-runtime component and its driver
    resets only through the participant lifecycle (not at construction). The
    scenario objective is therefore evaluated at the end of the episode through
    the researcher's own evaluation plan rather than projected at scenario apply,
    so only the compiled provisioning sub-plan is applied here.
    """

    return start_single_participant_runtime(target, scenario, _orchestration_plan(controls))


def _initialize_participant(
    target: RuntimeTarget,
    snapshot: RuntimeSnapshot,
    controls: RunControls,
    diagnostics: list[DiagnosticModel],
) -> RuntimeSnapshot:
    """Initialize the single red participant through the published runtime."""

    return initialize_single_participant(
        target,
        snapshot,
        _RED,
        f"{controls.run_id}-red",
        diagnostics,
    )


def _execute_steps(
    target: RuntimeTarget,
    snapshot: RuntimeSnapshot,
    controls: RunControls,
    diagnostics: list[DiagnosticModel],
) -> tuple[RuntimeSnapshot, int]:
    """Execute the admitted action until the declared terminal boundary."""

    if target.participant_runtime is None:
        raise RuntimeError("researcher execution runtime is unavailable")
    completed_steps = 0
    for step in range(1, controls.max_steps + 1):
        action = target.participant_runtime.admit_action(
            _red_action_request(f"{controls.run_id}-red-action-{step}", controls), snapshot
        )
        diagnostics.extend(diagnostic_model(item) for item in action.diagnostics)
        if not action.success:
            raise RuntimeError("researcher participant action failed")
        snapshot = action.snapshot
        completed_steps = step
        if target.participant_runtime.status()["running"] == 0:
            break
    return snapshot, completed_steps


def _evaluate_episode(
    target: RuntimeTarget,
    snapshot: RuntimeSnapshot,
    diagnostics: list[DiagnosticModel],
) -> tuple[
    RuntimeSnapshot,
    tuple[ExperimentEvidenceRecordModel, ...],
    tuple[ExperimentDerivedMeasureModel, ...],
]:
    """Evaluate the final portable snapshot and return published evidence."""

    if target.evaluator is None:
        raise RuntimeError("researcher evaluator is unavailable")
    evaluated = target.evaluator.start(nasim_evaluation_plan(), snapshot)
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
    driver: NasimDriverProtocol | None = None,
) -> EpisodeEvidence:
    """Execute one selected episode and return only validated RAES evidence."""

    target = create_nasim_target(seed=controls.seed, **({"driver": driver} if driver else {}))
    diagnostics: list[DiagnosticModel] = []
    snapshot: RuntimeSnapshot | None = None
    completed_steps = 0
    cleanup_verified = False
    evidence_records: tuple[ExperimentEvidenceRecordModel, ...] = ()
    derived_measures: tuple[ExperimentDerivedMeasureModel, ...] = ()
    try:
        # Startup (provisioning + orchestration) runs inside the cleanup-protected
        # region: a partial start that allocates the target and then fails must
        # still reach verified destroy(), per the always-attempt-cleanup contract.
        snapshot, start_diagnostics = _start_runtime(target, scenario, controls)
        diagnostics.extend(start_diagnostics)
        snapshot = _initialize_participant(target, snapshot, controls, diagnostics)
        snapshot, completed_steps = _execute_steps(target, snapshot, controls, diagnostics)
        snapshot, evidence_records, derived_measures = _evaluate_episode(
            target, snapshot, diagnostics
        )
    finally:
        manager = (
            RuntimeManager(target, initial_snapshot=snapshot)
            if snapshot is not None
            else RuntimeManager(target)
        )
        cleanup = manager.destroy()
        diagnostics.extend(diagnostic_model(item) for item in cleanup.diagnostics)
        cleanup_verified = cleanup.success
    if not cleanup_verified:
        raise RuntimeError("researcher cleanup failed")
    return EpisodeEvidence(
        completed_steps=completed_steps,
        evidence_records=evidence_records,
        derived_measures=derived_measures,
        diagnostics=tuple(diagnostics),
        cleanup_verified=cleanup_verified,
    )


def _supported_profiles() -> list[str]:
    """Return installed profiles fully supported by the NASim manifest."""

    manifest = create_nasim_manifest()
    profiles: list[str] = []
    for path in sorted(backend_profiles_root().glob("*.json")):
        profile = load_backend_profile(path.stem)
        if set(profile.required_contracts) <= set(manifest.supported_contract_versions):
            profiles.append(profile.profile)
    return profiles


def nasim_inspection_payload() -> dict[str, object]:
    """Project installed identities without constructing the native backend."""

    manifest = create_nasim_manifest()
    manifest_payload = backend_manifest_payload(manifest)
    qualification = load_qualification()
    source = qualification["source"]
    try:
        verify_selected_nasim_source()
        native_verified = True
    except Exception:
        native_verified = False
    return {
        "adapter": {
            "distribution": "raes-adapters",
            "version": metadata.version("raes-adapters"),
        },
        "backend": {
            "name": manifest.name,
            "version": manifest.version,
            "manifest_contract": manifest_payload["schema_version"],
            "native_available": native_verified,
        },
        "qualification": {
            "source_commit": source["commit"],
            "source_version": source["version"],
            "source_repository": source["repository"],
            "source_ledger": "/".join(NASIM_TINY.ledger_resource),
        },
        "supported_profiles": _supported_profiles(),
        "examples": ["nasim-tiny"],
    }


_CONFORMANCE_SUITE_SEEDS: dict[str, tuple[int, ...]] = {
    "pr": (PR_CONFORMANCE_SEED,),
    "full": (PR_CONFORMANCE_SEED,),
}


def nasim_conformance_suite(*, suite: str, output_dir: Path) -> dict[str, object]:
    """Run one deterministic tier and return a machine-readable evidence index.

    NASim ships no hermetic probe driver, so this runs the published RAES target
    conformance probe over the installed selected source. It preserves the
    canonical report, source-protocol diagnostics, declared weaknesses, and the
    explicit non-claims without wrapping any of them as an experiment run.
    """

    seeds = _CONFORMANCE_SUITE_SEEDS.get(suite)
    if seeds is None:
        raise ValueError("NASim conformance suite must be 'pr' or 'full'.")
    invocation_root = Path.cwd().resolve()
    output_dir = output_dir.resolve()
    if output_dir == invocation_root or not output_dir.is_relative_to(invocation_root):
        raise ValueError("NASim conformance output must be beneath the invocation directory.")
    diagnostics = nasim_source_protocol_diagnostics()
    reports: list[dict[str, object]] = []
    for seed in seeds:
        report = run_nasim_conformance(seed=seed)
        payload = nasim_backend_conformance_payload(report)
        if (
            report.unsupported_contract_gaps
            or report.unsupported_capability_gaps
            or any(not case.passed for case in report.cases)
        ):
            raise RuntimeError("NASim published conformance cases failed.")
        capability_gaps = nasim_manifest_capability_gaps()
        report_path = write_backend_conformance_report(
            payload,
            output_dir=output_dir,
            run_id=f"nasim-{suite}-seed-{seed}",
        )
        reports.append(
            {
                "seed": seed,
                "execution_basis": "installed-source-probe",
                "native_conformance": report.native_conformance,
                "report_path": report_path.relative_to(output_dir).as_posix(),
                "capability_gaps": list(capability_gaps),
            }
        )
    index: dict[str, object] = {
        "suite": suite,
        "seeds": list(seeds),
        "reports": reports,
        "diagnostics": [diagnostic_payload(item) for item in diagnostics],
        "declared_weaknesses": list(nasim_declared_weaknesses()),
        "explicit_non_claims": [
            "Finite conformance does not establish deterministic replay.",
            "Finite conformance does not establish scientific equivalence.",
            "A probe over the installed source is not a native attacker episode.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.json").write_text(
        json.dumps(index, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return index


__all__ = [
    "EpisodeEvidence",
    "RunControls",
    "archival_collection",
    "archival_run",
    "execute_episode",
    "nasim_conformance_suite",
    "nasim_inspection_payload",
    "red_implementation_provenance",
]
