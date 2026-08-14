"""CyberBattleSim chain researcher workflow over published RAES contracts.

The qualified source ``CredentialCacheExploiter`` selects every attacker action.
Its native proposal stays driver-private until the matching semantic action is
admitted by the participant runtime. The selected public evaluator's incomplete
random-stream binding remains an explicit non-claim.
"""

from __future__ import annotations

import json
import math
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
    ParticipantImplementationManifestModel,
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

from raes_adapters._experiment_evidence import SupplementalJsonArtifact
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
from raes_adapters.cyberbattlesim import load_qualification
from raes_adapters.cyberbattlesim.backend.conformance import (
    cyberbattlesim_backend_conformance_payload,
    cyberbattlesim_declared_weaknesses,
    cyberbattlesim_manifest_capability_gaps,
    cyberbattlesim_source_protocol_diagnostics,
    run_cyberbattlesim_conformance,
)
from raes_adapters.cyberbattlesim.backend.driver import (
    AutonomousActionProposal,
    CyberBattleSimDriver,
    CyberBattleSimDriverProtocol,
    verify_selected_cyberbattlesim_source,
)
from raes_adapters.cyberbattlesim.backend.evaluator import CyberBattleSimEvaluator
from raes_adapters.cyberbattlesim.backend.manifest import create_cyberbattlesim_manifest
from raes_adapters.cyberbattlesim.backend.target import create_cyberbattlesim_target
from raes_adapters.cyberbattlesim.runtime_plans import (
    CYBERBATTLESIM_CLOCK,
    cyberbattlesim_evaluation_plan,
    cyberbattlesim_orchestration_plan,
)
from raes_adapters.cyberbattlesim.scenario_ledger import CYBERBATTLE_CHAIN

_RED = "participant.behavior.red"
_ACTION_CONTRACT_BY_KIND = {
    "connect": "participant.action-contract.connect",
    "local-vulnerability": "participant.action-contract.local-vulnerability",
    "remote-vulnerability": "participant.action-contract.remote-vulnerability",
}
_OBSERVATION_BOUNDARY = "participant.observation-boundary.attacker-view"
_POLICY_IDENTITY_TARGET = "red-policy-identity"
_BACKEND_MANIFEST_REF = "manifest.cyberbattlesim-chain"
_ACTION_ARGUMENT_SHAPE = "participant.action-argument-shape.cyberbattlesim"
_POLICY_IDENTITY = "CredentialCacheExploiter"
PR_CONFORMANCE_SEED = 20260729


@dataclass(frozen=True)
class RunControls(RedParticipantRunControls):
    """Internal, non-portable selection of already published run controls.

    Bound to the single qualified credential-cache attacker and source controls.
    """

    epsilon_step_offset: int = 0

    def __post_init__(self) -> None:
        """Reject controls not bound to the selected published contracts."""

        self.validate_common(_RED)
        _red_policy_identity(self.red_configuration)
        if type(self.epsilon_step_offset) is not int or self.epsilon_step_offset < 0:
            raise ValueError("epsilon step offset is outside the supported range")


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

    backend = create_cyberbattlesim_manifest()
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
                "ref_id": f"cyberbattlesim-chain-public-{source_revision[:7]}",
                "ref_version": source_revision,
            }
        ],
        configuration_parameters=[
            {
                "name": "red-policy",
                "value": _red_policy_identity(controls.red_configuration),
                "value_kind": "apparatus",
            }
        ],
        stochastic_seed_control_id="cyberbattlesim-gym-reset-seed",
        clock_id=CYBERBATTLESIM_CLOCK,
        clock_authority="cyberbattlesim-chain runtime",
        measurement_channel_ref_id="cyberbattlesim-reward-projection",
        known_limitations=[
            {
                "category": "apparatus",
                "note": "Native internals are withheld at the adapter boundary.",
            },
            {
                "category": "internal",
                "note": (
                    "The public evaluator leaves Python and global NumPy streams unbound; "
                    "the recorded seed is not a deterministic-replay claim."
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
                {
                    "name": "epsilon-step-offset",
                    "value": controls.epsilon_step_offset,
                    "value_kind": "protocol",
                },
            ],
            seed=controls.seed,
            stochastic_seed_control_id="cyberbattlesim-gym-reset-seed",
            clock_id=CYBERBATTLESIM_CLOCK,
            clock_authority="cyberbattlesim-chain runtime",
            result_summary_key="cyberbattlesim-cumulative-attacker-reward-result",
            metric_id="cumulative_attacker_reward",
        ),
    )


def archival_collection(
    task: ExperimentTaskModel, runs: Sequence[ExperimentRunModel], study_id: str
) -> ExperimentStudyModel:
    """Group a declared run batch without introducing a scientific claim."""

    return build_archival_collection(
        task, runs, study_id, title="CyberBattleSim chain declared run collection"
    )


def _red_policy_identity(configuration: ParticipantConfigurationResultModel) -> str:
    """Return the exact source policy selected by an admitted configuration."""

    values = {
        item.target_id: item.value.value
        for item in configuration.configuration.values
        if item.value.kind == "literal"
    }
    selected = values.get(_POLICY_IDENTITY_TARGET)
    if selected != _POLICY_IDENTITY:
        raise ValueError("red participant configuration has no installed executable behavior")
    return _POLICY_IDENTITY


def _red_action_request(
    action_instance_id: str,
    controls: RunControls,
    proposal: AutonomousActionProposal,
) -> ParticipantActionAdmissionRequest:
    """Bind one private source-policy proposal to its portable semantic action."""

    try:
        action_contract = _ACTION_CONTRACT_BY_KIND[proposal.action_kind]
    except KeyError as error:
        raise ValueError("source policy proposed an unsupported action kind") from error
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
            proposal_ref=proposal.proposal_ref,
            normalized_arguments=(("target_address", proposal.target_address),),
            loss_disclosure_refs=("loss-observation-abstraction",),
        ),
        target_addresses=(proposal.target_address,),
        requires_terminal_outcome=True,
    )


def _orchestration_plan(controls: RunControls) -> OrchestrationPlan:
    """Return the bounded single-attacker workflow for one admitted run."""

    workflow = f"orchestration.workflow.{controls.run_id}"
    return cyberbattlesim_orchestration_plan(
        workflow=workflow,
        name="cyberbattlesim-chain-research-run",
        max_steps=controls.max_steps,
    )


def _start_runtime(
    target: RuntimeTarget, scenario: object, controls: RunControls
) -> tuple[RuntimeSnapshot, list[DiagnosticModel]]:
    """Realize the scenario topology and start the bounded single-attacker workflow.

    The selected CyberBattleSim backend ships no time-runtime component and its driver
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
    driver: CyberBattleSimDriverProtocol,
) -> tuple[RuntimeSnapshot, int]:
    """Admit each exact source-policy proposal before its native transition."""

    if target.participant_runtime is None:
        raise RuntimeError("researcher execution runtime is unavailable")
    completed_steps = 0
    for step in range(1, controls.max_steps + 1):
        epsilon = _epsilon_for_step(controls.epsilon_step_offset + step - 1)
        proposal = driver.propose_autonomous_action(epsilon=epsilon)
        action = target.participant_runtime.admit_action(
            _red_action_request(f"{controls.run_id}-red-action-{step}", controls, proposal),
            snapshot,
        )
        diagnostics.extend(diagnostic_model(item) for item in action.diagnostics)
        if not action.success:
            raise RuntimeError("researcher participant action failed")
        snapshot = action.snapshot
        completed_steps = step
        if target.participant_runtime.status()["running"] == 0:
            break
    return snapshot, completed_steps


def _epsilon_for_step(step: int) -> float:
    """Apply the selected upstream evaluator's exponential epsilon schedule."""

    protocol = load_qualification()["protocol"]["selection"]["attacker"]
    initial = float(protocol["epsilon"])
    minimum = float(protocol["epsilon_minimum"])
    decay = float(protocol["epsilon_exponential_decay"])
    return minimum + math.exp(-step / decay) * (initial - minimum)


def _evaluate_episode(
    target: RuntimeTarget,
    snapshot: RuntimeSnapshot,
    diagnostics: list[DiagnosticModel],
) -> tuple[
    RuntimeSnapshot,
    tuple[ExperimentEvidenceRecordModel, ...],
    tuple[ExperimentDerivedMeasureModel, ...],
    tuple[SupplementalJsonArtifact, ...],
]:
    """Evaluate the final portable snapshot and return published evidence."""

    if not isinstance(target.evaluator, CyberBattleSimEvaluator):
        raise RuntimeError("researcher evaluator is unavailable")
    evaluated = target.evaluator.start(cyberbattlesim_evaluation_plan(), snapshot)
    diagnostics.extend(diagnostic_model(item) for item in evaluated.diagnostics)
    if not evaluated.success:
        raise RuntimeError("researcher evaluation failed")
    return (
        evaluated.snapshot,
        target.evaluator.evidence_records(),
        target.evaluator.derived_measures(),
        target.evaluator.supplemental_artifacts(),
    )


def execute_episode(
    scenario: object,
    controls: RunControls,
    *,
    driver: CyberBattleSimDriverProtocol | None = None,
) -> EpisodeEvidence:
    """Execute one selected episode and return only validated RAES evidence."""

    selected_driver = driver if driver is not None else CyberBattleSimDriver()
    target = create_cyberbattlesim_target(
        seed=controls.seed,
        driver=selected_driver,
        participant_manifest=controls.red_manifest,
        participant_selection=controls.red_selection,
        participant_configuration=controls.red_configuration,
    )
    diagnostics: list[DiagnosticModel] = []
    snapshot: RuntimeSnapshot | None = None
    completed_steps = 0
    cleanup_verified = False
    evidence_records: tuple[ExperimentEvidenceRecordModel, ...] = ()
    derived_measures: tuple[ExperimentDerivedMeasureModel, ...] = ()
    supplemental_artifacts: tuple[SupplementalJsonArtifact, ...] = ()
    try:
        # Startup (provisioning + orchestration) runs inside the cleanup-protected
        # region: a partial start that allocates the target and then fails must
        # still reach verified destroy(), per the always-attempt-cleanup contract.
        snapshot, start_diagnostics = _start_runtime(target, scenario, controls)
        diagnostics.extend(start_diagnostics)
        snapshot = _initialize_participant(target, snapshot, controls, diagnostics)
        snapshot, completed_steps = _execute_steps(
            target, snapshot, controls, diagnostics, selected_driver
        )
        snapshot, evidence_records, derived_measures, supplemental_artifacts = _evaluate_episode(
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
        driver_cleanup = selected_driver.close()
        cleanup_verified = (
            cleanup.success
            and driver_cleanup.closed
            and driver_cleanup.verified
            and selected_driver.verify_closed()
        )
    if not cleanup_verified:
        raise RuntimeError("researcher cleanup failed")
    return EpisodeEvidence(
        completed_steps=completed_steps,
        evidence_records=evidence_records,
        derived_measures=derived_measures,
        diagnostics=tuple(diagnostics),
        cleanup_verified=cleanup_verified,
        supplemental_artifacts=tuple(supplemental_artifacts),
    )


def _supported_profiles() -> list[str]:
    """Return installed profiles fully supported by the CyberBattleSim manifest."""

    manifest = create_cyberbattlesim_manifest()
    profiles: list[str] = []
    for path in sorted(backend_profiles_root().glob("*.json")):
        profile = load_backend_profile(path.stem)
        if set(profile.required_contracts) <= set(manifest.supported_contract_versions):
            profiles.append(profile.profile)
    return profiles


def cyberbattlesim_inspection_payload() -> dict[str, object]:
    """Project installed identities without constructing the native backend."""

    manifest = create_cyberbattlesim_manifest()
    manifest_payload = backend_manifest_payload(manifest)
    qualification = load_qualification()
    source = qualification["source"]
    try:
        verify_selected_cyberbattlesim_source()
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
            "source_ledger": "/".join(CYBERBATTLE_CHAIN.ledger_resource),
        },
        "supported_profiles": _supported_profiles(),
        "examples": ["cyberbattlesim-chain (external release asset)"],
    }


_CONFORMANCE_SUITE_SEEDS: dict[str, tuple[int, ...]] = {
    "pr": (PR_CONFORMANCE_SEED,),
    "full": (PR_CONFORMANCE_SEED,),
}


def cyberbattlesim_conformance_suite(
    *,
    suite: str,
    output_dir: Path,
    participant_manifest: ParticipantImplementationManifestModel | None = None,
    participant_selection: ParticipantImplementationSelectionModel | None = None,
    participant_configuration: ParticipantConfigurationResultModel | None = None,
) -> dict[str, object]:
    """Run one deterministic tier and return a machine-readable evidence index.

    CyberBattleSim ships no hermetic probe driver, so this runs the published RAES target
    conformance probe over the installed selected source. It preserves the
    canonical report, source-protocol diagnostics, declared weaknesses, and the
    explicit non-claims without wrapping any of them as an experiment run.
    """

    seeds = _CONFORMANCE_SUITE_SEEDS.get(suite)
    if seeds is None:
        raise ValueError("CyberBattleSim conformance suite must be 'pr' or 'full'.")
    invocation_root = Path.cwd().resolve()
    output_dir = output_dir.resolve()
    if output_dir == invocation_root or not output_dir.is_relative_to(invocation_root):
        raise ValueError(
            "CyberBattleSim conformance output must be beneath the invocation directory."
        )
    diagnostics = cyberbattlesim_source_protocol_diagnostics()
    reports: list[dict[str, object]] = []
    for seed in seeds:
        report = run_cyberbattlesim_conformance(
            seed=seed,
            participant_manifest=participant_manifest,
            participant_selection=participant_selection,
            participant_configuration=participant_configuration,
        )
        payload = cyberbattlesim_backend_conformance_payload(report)
        if (
            report.unsupported_contract_gaps
            or report.unsupported_capability_gaps
            or any(not case.passed for case in report.cases)
        ):
            raise RuntimeError("CyberBattleSim published conformance cases failed.")
        capability_gaps = cyberbattlesim_manifest_capability_gaps()
        report_path = write_backend_conformance_report(
            payload,
            output_dir=output_dir,
            run_id=f"cyberbattlesim-{suite}-seed-{seed}",
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
        "declared_weaknesses": list(cyberbattlesim_declared_weaknesses()),
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
    "cyberbattlesim_conformance_suite",
    "cyberbattlesim_inspection_payload",
    "red_implementation_provenance",
]
