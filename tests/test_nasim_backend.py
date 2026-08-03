"""Contract-level behavior for the NASim backend."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path

from raes_backend_protocols.backend_manifest import BackendManifest
from raes_backend_protocols.manifest import backend_manifest_v2_model
from raes_contracts.contracts import (
    ExperimentCaptureSpecModel,
    ExperimentDerivedMeasureModel,
    ExperimentEvidenceRecordModel,
    ParticipantActionResultModel,
    TrialCleanupPlanModel,
)
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest
from raes_contracts.participant_episode import (
    ParticipantEpisodeInitializeRequest,
    ParticipantEpisodeRestartRequest,
)
from raes_contracts.planning import (
    ChangeAction,
    EvaluationOp,
    EvaluationPlan,
    OrchestrationOp,
    OrchestrationPlan,
    ProvisioningPlan,
    ProvisionOp,
)
from raes_contracts.runtime_state import OperationState, RuntimeSnapshot
from raes_processor.reference import ReferenceProcessor
from raes_runtime import RuntimeControlPlane

from raes_adapters.base import run_conformance_probe
from raes_adapters.nasim.backend import (
    ACTION_EVIDENCE_REF,
    NASIM_BACKEND_NAME,
    NasimCleanupReport,
    NasimEvaluation,
    NasimEvaluator,
    NasimParticipantRuntime,
    NasimProvisioner,
    NasimResetReport,
    NasimStep,
    create_nasim_manifest,
    create_nasim_target,
    execute_nasim_cleanup,
)
from tests._gym_fixtures import GymFixtureConfig, action_request, cleanup_plan

PARTICIPANT = "participant.behavior.attacker"
OBSERVATION_BOUNDARY = "participant.observation-boundary.attacker-view"
EXPLOIT_ACTION = "participant.action-contract.service-exploit"


@dataclass
class FakeDriver:
    """Deterministic injected driver that retains deliberately private native state."""

    steps: list[NasimStep] = field(default_factory=list)
    evaluation: NasimEvaluation = field(
        default_factory=lambda: NasimEvaluation(
            step_count=0,
            cumulative_reward=0.0,
            terminated=False,
            truncated=False,
            terminal_cause=None,
        )
    )
    construct_calls: int = 0
    reset_calls: list[int | None] = field(default_factory=list)
    step_calls: list[tuple[str, str | None]] = field(default_factory=list)
    evaluate_calls: int = 0
    close_calls: int = 0
    closed: bool = False
    fail_close: bool = False
    fail_step: bool = False
    applied_streams: tuple[str, ...] = ("numpy-global-action-success", "gym-environment-reset")
    unbound_streams: tuple[str, ...] = ()
    native_observation: object = field(
        default_factory=lambda: {
            "flat_observation_vector": "must-not-cross",
            "flat_action_index": "must-not-cross",
            "native_host_state": "must-not-cross",
            "native_info": "must-not-cross",
        }
    )

    def construct(self) -> None:
        self.construct_calls += 1
        self.closed = False

    def reset(self, seed: int | None) -> NasimResetReport:
        self.reset_calls.append(seed)
        self.closed = False
        return NasimResetReport(
            operation_ref=f"driver.reset.{len(self.reset_calls)}",
            applied_streams=self.applied_streams,
            unbound_streams=self.unbound_streams,
        )

    def step(self, action_kind: str, target_ref: str | None = None) -> NasimStep:
        self.step_calls.append((action_kind, target_ref))
        if self.fail_step:
            raise RuntimeError("private native step failure with secret-token")
        if self.steps:
            return self.steps.pop(0)
        return NasimStep(
            operation_ref=f"driver.step.{len(self.step_calls)}",
            step_number=len(self.step_calls),
            source_transition=True,
            processed=True,
            terminated=False,
            truncated=False,
            terminal_cause=None,
        )

    def evaluate(self) -> NasimEvaluation:
        self.evaluate_calls += 1
        return replace(
            self.evaluation,
            projection_ref=(f"{self.evaluation.execution_ref}.evaluation.{self.evaluate_calls}"),
        )

    def close(self) -> NasimCleanupReport:
        self.close_calls += 1
        if self.fail_close:
            raise RuntimeError("private native close failure with secret-token")
        already_closed = self.closed
        self.closed = True
        return NasimCleanupReport(
            operation_ref=f"driver.close.{self.close_calls}",
            closed=True,
            verified=True,
            already_closed=already_closed,
        )

    def verify_closed(self) -> bool:
        return self.closed


_CONFIG = GymFixtureConfig(
    name="nasim",
    backend_name=NASIM_BACKEND_NAME,
    participant_address=PARTICIPANT,
    observation_boundary=OBSERVATION_BOUNDARY,
    action_evidence_ref=ACTION_EVIDENCE_REF,
    implementation_name="nasim-bruteforce-policy",
    participant_runtime_name="nasim-participant-runtime",
)


def _action_request(
    action_contract_address: str = EXPLOIT_ACTION,
    *,
    action_instance_id: str = "action-1",
    disclose_action_evidence: bool = True,
    target_addresses: tuple[str, ...] = ("provision.node.host-2-0",),
) -> ParticipantActionAdmissionRequest:
    return action_request(
        _CONFIG,
        action_contract_address,
        action_instance_id=action_instance_id,
        disclose_action_evidence=disclose_action_evidence,
        target_addresses=target_addresses,
    )


def _cleanup_plan(*, required: bool = True) -> TrialCleanupPlanModel:
    return cleanup_plan(_CONFIG, required=required)


def test_backend_import_is_dependency_light_and_lazy() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            (
                "import sys; import raes_adapters.nasim.backend; "
                "assert 'nasim' not in sys.modules; "
                "assert 'gymnasium' not in sys.modules"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_manifest_and_target_claim_exact_implemented_surfaces() -> None:
    driver = FakeDriver()
    manifest = create_nasim_manifest()
    target = create_nasim_target(driver=driver, seed=20260802)

    assert isinstance(manifest, BackendManifest)
    assert manifest.name == NASIM_BACKEND_NAME
    assert manifest.has_orchestrator
    assert manifest.has_evaluator
    assert manifest.has_participant_runtime
    assert manifest.has_cleanup
    assert not manifest.has_observation
    assert manifest.participant_runtime is not None
    assert manifest.participant_runtime.supports_bounded_concurrency is False
    assert manifest.participant_runtime.supported_interaction_features == frozenset(
        {"shared_state_change"}
    )
    assert manifest.constraints["outcome_reproduction"] == "stochastic-bounded"
    assert (
        manifest.constraints["source_identity"]
        == "qualified-complete-runtime-artifact-roots-attested"
    )
    # The native source is fully observed; the manifest must disclose the
    # narrower lossy participant projection rather than call it partial.
    assert "fully-observed" in manifest.constraints["native_observability"]
    assert "fully observed" in manifest.participant_runtime.constraints["native_observation"]
    assert manifest.provisioner.supported_os_families == frozenset({"linux"})
    assert manifest.evaluator.supported_evidence_channels == frozenset({"api_response"})
    assert {
        "participant-control-occurrence-v1",
        "participant-crossing-occurrence-v1",
        "participant-lifecycle-event-v1",
    } <= manifest.supported_contract_versions
    assert backend_manifest_v2_model(manifest).identity.name == NASIM_BACKEND_NAME
    assert target.name == NASIM_BACKEND_NAME


def test_provisioner_reconciles_live_driver_and_orchestrator_never_steps_driver() -> None:
    driver = FakeDriver()
    provisioner = NasimProvisioner(driver)
    snapshot = RuntimeSnapshot()
    plan = ProvisioningPlan(
        operations=[
            ProvisionOp(
                action=ChangeAction.CREATE,
                address="provision.node.host-1-0",
                resource_type="node",
                payload={"node_type": "vm", "os_family": "linux"},
            )
        ]
    )

    applied = provisioner.apply(plan, snapshot)
    repeated = provisioner.apply(plan, applied.snapshot)

    assert applied.success
    assert repeated.success
    assert driver.construct_calls == 2
    assert applied.snapshot.entries["provision.node.host-1-0"].status == "applied"

    target = create_nasim_target(driver=driver)
    orchestration = OrchestrationPlan(
        operations=[
            OrchestrationOp(
                action=ChangeAction.CREATE,
                address="orchestration.workflow.episode",
                resource_type="workflow",
                payload={
                    "name": "episode",
                    "execution_contract": {"start_step": "participant-action"},
                    "result_contract": {
                        "state_schema_version": "workflow-step-state/v1",
                        "observable_steps": {"participant-action": {}},
                    },
                },
            )
        ],
        startup_order=["orchestration.workflow.episode"],
    )
    started = target.orchestrator.start(orchestration, repeated.snapshot)

    assert started.success
    assert (
        started.snapshot.orchestration_results["orchestration.workflow.episode"]["workflow_status"]
        == "running"
    )
    assert driver.step_calls == []


def test_unsupported_provisioning_is_rejected_before_construction() -> None:
    driver = FakeDriver()
    plan = ProvisioningPlan(
        operations=[
            ProvisionOp(
                action=ChangeAction.CREATE,
                address="provision.persistent-volume.unsupported",
                resource_type="persistent-volume",
                payload={},
            )
        ]
    )

    result = NasimProvisioner(driver).apply(plan, RuntimeSnapshot())

    assert not result.success
    assert driver.construct_calls == 0
    assert result.diagnostics[0].code == "nasim.provisioning.unsupported-resource"


def test_each_admitted_action_joins_one_driver_operation_and_withholds_native_state() -> None:
    driver = FakeDriver()
    runtime = NasimParticipantRuntime(driver, seed=20260802)
    initialized = runtime.initialize(
        ParticipantEpisodeInitializeRequest(
            participant_address=PARTICIPANT,
            episode_id="episode-1",
        ),
        RuntimeSnapshot(),
    )

    result = runtime.admit_action(_action_request(), initialized.snapshot)

    assert result.success
    assert driver.step_calls == [("service-exploit", "provision.node.host-2-0")]
    assert isinstance(result.action_result, ParticipantActionResultModel)
    assert result.action_result.status == "succeeded"
    assert result.action_result.episode_id == "episode-1"
    assert result.action_result.action_instance_id == "action-1"
    assert result.action_result.evidence_refs == [ACTION_EVIDENCE_REF]
    assert result.action_result.effects[0].target_refs == []
    assert runtime.driver_operation_ref("action-1") == "driver.step.1"
    observations = runtime.observations(PARTICIPANT)
    assert len(observations) == 1
    assert observations[0].information_guarantee == "lossy_projection"
    portable = str(
        {
            "result": result.action_result.model_dump(mode="json"),
            "observation": observations[0].model_dump(mode="json"),
            "snapshot": result.snapshot.participant_behavior_history,
        }
    )
    for forbidden in (
        "flat_observation_vector",
        "flat_action_index",
        "native_host_state",
        "native_info",
        "must-not-cross",
        "driver.step.1",
    ):
        assert forbidden not in portable
    assert runtime.observations("participant.agent.defender") == ()


def test_unsupported_action_is_rejected_before_native_mutation() -> None:
    driver = FakeDriver()
    runtime = NasimParticipantRuntime(driver)
    initialized = runtime.initialize(
        ParticipantEpisodeInitializeRequest(
            participant_address=PARTICIPANT,
            episode_id="episode-unsupported",
        ),
        RuntimeSnapshot(),
    )

    result = runtime.admit_action(
        _action_request(
            "participant.action-contract.deploy-defender",
            action_instance_id="action-unsupported",
        ),
        initialized.snapshot,
    )

    assert not result.success
    assert driver.step_calls == []
    assert result.action_result is not None
    assert result.action_result.status == "rejected"
    assert result.action_result.failure_class == "unsupported_action"


def test_action_boundary_withholds_unrequested_evidence_and_native_failures() -> None:
    driver = FakeDriver()
    runtime = NasimParticipantRuntime(driver)
    initialized = runtime.initialize(
        ParticipantEpisodeInitializeRequest(
            participant_address=PARTICIPANT,
            episode_id="episode-boundary",
        ),
        RuntimeSnapshot(),
    )

    undisclosed = runtime.admit_action(
        _action_request(disclose_action_evidence=False),
        initialized.snapshot,
    )

    assert undisclosed.success
    assert undisclosed.action_result is not None
    assert undisclosed.action_result.evidence_refs == []
    assert undisclosed.action_result.effects[0].evidence_refs == []
    assert runtime.observations(PARTICIPANT)[0].evidence_refs == []

    failing_runtime = NasimParticipantRuntime(FakeDriver(fail_step=True))
    failing_initialized = failing_runtime.initialize(
        ParticipantEpisodeInitializeRequest(
            participant_address=PARTICIPANT,
            episode_id="episode-failure",
        ),
        RuntimeSnapshot(),
    )
    failed = failing_runtime.admit_action(
        _action_request(action_instance_id="action-failure"),
        failing_initialized.snapshot,
    )
    portable = str(
        {
            "diagnostics": [diagnostic.message for diagnostic in failed.diagnostics],
            "action_result": failed.action_result.model_dump(mode="json")
            if failed.action_result is not None
            else None,
        }
    )

    assert not failed.success
    assert failed.action_result is not None
    assert failed.action_result.status == "failed"
    assert "secret-token" not in portable


def test_seed_streams_are_reported_separately() -> None:
    unbound_driver = FakeDriver(
        applied_streams=(), unbound_streams=("numpy-global-action-success",)
    )
    runtime = NasimParticipantRuntime(unbound_driver, seed=None)
    initialized = runtime.initialize(
        ParticipantEpisodeInitializeRequest(
            participant_address=PARTICIPANT,
            episode_id="episode-unbound",
        ),
        RuntimeSnapshot(),
    )
    codes = {diagnostic.code for diagnostic in initialized.diagnostics}
    assert "nasim.seed.unbound" in codes
    assert "nasim.seed.applied" not in codes

    bound_driver = FakeDriver(
        applied_streams=("numpy-global-action-success", "gym-environment-reset"),
        unbound_streams=(),
    )
    bound_runtime = NasimParticipantRuntime(bound_driver, seed=20260802)
    bound = bound_runtime.initialize(
        ParticipantEpisodeInitializeRequest(
            participant_address=PARTICIPANT,
            episode_id="episode-bound",
        ),
        RuntimeSnapshot(),
    )
    bound_codes = [diagnostic.code for diagnostic in bound.diagnostics]
    assert bound_codes.count("nasim.seed.applied") == 2
    assert "nasim.seed.unbound" not in bound_codes


def test_goal_and_step_limit_are_retained_as_distinct_terminal_facts() -> None:
    both_true = FakeDriver(
        steps=[
            NasimStep(
                operation_ref="driver.step.terminal",
                step_number=1,
                source_transition=True,
                processed=True,
                terminated=True,
                truncated=True,
                terminal_cause="goal",
            )
        ]
    )
    runtime = NasimParticipantRuntime(both_true, seed=20260802)
    initialized = runtime.initialize(
        ParticipantEpisodeInitializeRequest(
            participant_address=PARTICIPANT,
            episode_id="episode-both",
        ),
        RuntimeSnapshot(),
    )
    result = runtime.admit_action(_action_request(), initialized.snapshot)

    # Goal precedence for participant completion; truncation is not erased.
    assert result.success
    episode = result.snapshot.participant_episode_results[PARTICIPANT]
    assert episode["status"] == "terminated"
    assert episode["terminal_reason"] == "completed"

    only_truncated = FakeDriver(
        steps=[
            NasimStep(
                operation_ref="driver.step.limit",
                step_number=1,
                source_transition=True,
                processed=True,
                terminated=False,
                truncated=True,
                terminal_cause="step-limit",
            )
        ]
    )
    truncated_runtime = NasimParticipantRuntime(only_truncated)
    truncated_initialized = truncated_runtime.initialize(
        ParticipantEpisodeInitializeRequest(
            participant_address=PARTICIPANT,
            episode_id="episode-limit",
        ),
        RuntimeSnapshot(),
    )
    truncated = truncated_runtime.admit_action(
        _action_request(action_instance_id="action-limit"),
        truncated_initialized.snapshot,
    )
    assert truncated.success
    limit_episode = truncated.snapshot.participant_episode_results[PARTICIPANT]
    assert limit_episode["terminal_reason"] == "truncated"


def test_evaluator_reads_distinct_facts_without_advancing_or_leaking_to_participant() -> None:
    driver = FakeDriver(
        evaluation=NasimEvaluation(
            step_count=1,
            cumulative_reward=14.0,
            terminated=False,
            truncated=False,
            terminal_cause=None,
        )
    )
    runtime = NasimParticipantRuntime(driver)
    initialized = runtime.initialize(
        ParticipantEpisodeInitializeRequest(
            participant_address=PARTICIPANT,
            episode_id="episode-evaluation",
        ),
        RuntimeSnapshot(),
    )
    action = runtime.admit_action(_action_request(), initialized.snapshot)
    evaluator = NasimEvaluator(driver)
    evaluation_plan = EvaluationPlan(
        operations=[
            EvaluationOp(
                action=ChangeAction.CREATE,
                address="evaluation.objective.compromise-sensitive-hosts",
                resource_type="objective",
                payload={
                    "result_contract": {
                        "resource_type": "objective",
                        "supports_score": True,
                        "fixed_max_score": 500,
                    }
                },
            )
        ],
        startup_order=["evaluation.objective.compromise-sensitive-hosts"],
    )

    evaluated = evaluator.start(evaluation_plan, action.snapshot)

    assert evaluated.success
    assert driver.evaluate_calls == 1
    assert evaluator.results()["evaluation.objective.compromise-sensitive-hosts"]["score"] == 14.0
    assert "14.0" not in str(action.action_result.model_dump(mode="json"))
    evidence_records = evaluator.evidence_records()
    derived_measures = evaluator.derived_measures()
    capture_spec = evaluator.capture_spec()
    assert isinstance(capture_spec, ExperimentCaptureSpecModel)
    assert len(evidence_records) == len(derived_measures) == 1
    assert isinstance(evidence_records[0], ExperimentEvidenceRecordModel)
    assert isinstance(derived_measures[0], ExperimentDerivedMeasureModel)
    assert derived_measures[0].value == 14.0
    assert any("truncation" in note for note in derived_measures[0].limitations)
    raw_content = evidence_records[0].raw_content
    assert (
        raw_content.content_checksum.value
        == hashlib.sha256(raw_content.payload_summary.encode("utf-8")).hexdigest()
    )
    # The per-run terminal facts are retained as evaluator evidence, not only as
    # a static limitation.
    assert "terminated=False" in raw_content.payload_summary
    assert "truncated=False" in raw_content.payload_summary
    portable_evaluation = str(
        {
            "evidence": evidence_records[0].model_dump(mode="json"),
            "measure": derived_measures[0].model_dump(mode="json"),
        }
    )
    for forbidden in ("flat_observation_vector", "flat_action_index", "must-not-cross"):
        assert forbidden not in portable_evaluation


def test_source_termination_closes_episode_and_restart_resets_same_seed() -> None:
    driver = FakeDriver(
        steps=[
            NasimStep(
                operation_ref="driver.step.terminal",
                step_number=1,
                source_transition=True,
                processed=True,
                terminated=True,
                truncated=False,
                terminal_cause="goal",
            )
        ]
    )
    runtime = NasimParticipantRuntime(driver, seed=20260802)
    initialized = runtime.initialize(
        ParticipantEpisodeInitializeRequest(
            participant_address=PARTICIPANT,
            episode_id="episode-terminal",
        ),
        RuntimeSnapshot(),
    )
    terminal = runtime.admit_action(_action_request(), initialized.snapshot)

    assert terminal.success
    assert terminal.snapshot.participant_episode_results[PARTICIPANT]["status"] == "terminated"
    restarted = runtime.restart(
        ParticipantEpisodeRestartRequest(
            participant_address=PARTICIPANT,
            episode_id="episode-restarted",
        ),
        terminal.snapshot,
    )
    assert restarted.success
    assert driver.reset_calls == [20260802, 20260802]


def test_cleanup_is_idempotent_verified_and_preserves_bounded_failure() -> None:
    driver = FakeDriver()
    manifest = create_nasim_manifest()
    plan = _cleanup_plan()

    first = execute_nasim_cleanup(
        plan,
        manifest,
        driver,
        receipt_id="cleanup-receipt-1",
        execution_attempt_id="cleanup-attempt-1",
        trial_outcome="succeeded",
    )
    second = execute_nasim_cleanup(
        plan,
        manifest,
        driver,
        receipt_id="cleanup-receipt-2",
        execution_attempt_id="cleanup-attempt-2",
        trial_outcome="succeeded",
    )

    assert first.cleanup_status == second.cleanup_status == "succeeded"
    assert driver.close_calls == 2
    assert driver.closed

    failing_driver = FakeDriver(fail_close=True)
    failed = execute_nasim_cleanup(
        _cleanup_plan(required=False),
        manifest,
        failing_driver,
        receipt_id="cleanup-receipt-failed",
        execution_attempt_id="cleanup-attempt-failed",
        trial_outcome="failed",
    )
    assert failed.cleanup_status == "failed"
    assert failed.obligation_results["destroy-environment"].status == "failed"
    assert "secret-token" not in str(failed.model_dump(mode="json"))


def test_selected_scenario_realizes_and_runs_across_applicable_surfaces() -> None:
    scenario = (
        Path(__file__).parents[1]
        / "src"
        / "raes_adapters"
        / "nasim"
        / "scenario"
        / "nasim-tiny.sdl.yaml"
    )
    driver = FakeDriver(
        evaluation=NasimEvaluation(
            step_count=1,
            cumulative_reward=7.0,
            terminated=False,
            truncated=False,
            terminal_cause=None,
        )
    )
    target = create_nasim_target(driver=driver, seed=20260802)
    realized = ReferenceProcessor.realize(
        scenario,
        target.manifest,
        parameters={},
        target_name=NASIM_BACKEND_NAME,
    )

    assert realized.is_valid
    assert realized.diagnostics == ()
    assert len(realized.execution_plan.provisioning.operations) == 8
    assert len(realized.execution_plan.evaluation.operations) == 3

    control_plane = RuntimeControlPlane(target)
    provisioning_receipt = control_plane.submit_provisioning(
        realized.execution_plan.provisioning,
        idempotency_key="selected-scenario-provisioning",
        request_fingerprint="selected-scenario-provisioning-v1",
    )
    initialize_receipt = control_plane.initialize_participant_episode(
        PARTICIPANT,
        episode_id="episode-selected-scenario",
        idempotency_key="selected-scenario-initialize",
        request_fingerprint="selected-scenario-initialize-v1",
    )
    participant_behavior = realized.runtime_model.participant_behaviors[PARTICIPANT]
    action_receipt = control_plane.admit_participant_action(
        participant_behavior,
        _action_request(),
        idempotency_key="selected-scenario-action",
        request_fingerprint="selected-scenario-action-v1",
    )
    repeated_action_receipt = control_plane.admit_participant_action(
        participant_behavior,
        _action_request(),
        idempotency_key="selected-scenario-action",
        request_fingerprint="selected-scenario-action-v1",
    )
    evaluation_receipt = control_plane.submit_evaluation(
        realized.execution_plan.evaluation,
        idempotency_key="selected-scenario-evaluation",
        request_fingerprint="selected-scenario-evaluation-v1",
    )

    receipts = (
        provisioning_receipt,
        initialize_receipt,
        action_receipt,
        evaluation_receipt,
    )
    assert all(receipt.accepted for receipt in receipts)
    assert all(
        control_plane.get_operation(receipt.operation_id).state == OperationState.SUCCEEDED
        for receipt in receipts
    )
    assert repeated_action_receipt.operation_id == action_receipt.operation_id
    truth_results = control_plane.snapshot.proposition_truth_results
    assert set(truth_results) == {"evaluation.assertion.ownership-postcondition"}
    assert {result["proposition_outcome"] for result in truth_results.values()} == {"unknown"}
    objective_results = control_plane.snapshot.evaluation_results
    assert (
        objective_results["evaluation.objective.compromise-sensitive-hosts"]["status"] == "running"
    )
    assert all(result["passed"] is None for result in objective_results.values())
    assert driver.step_calls == [("service-exploit", "provision.node.host-2-0")]
    assert driver.evaluate_calls == 1

    cleaned = execute_nasim_cleanup(
        _cleanup_plan(),
        target.manifest,
        driver,
        receipt_id="cleanup-selected-scenario",
        execution_attempt_id="cleanup-selected-scenario-attempt",
        trial_outcome="succeeded",
    )
    assert cleaned.cleanup_status == "succeeded"
    assert driver.closed


def test_target_passes_canonical_backend_conformance_probe() -> None:
    report = run_conformance_probe(create_nasim_target(driver=FakeDriver()))

    assert report.passed
    assert report.unsupported_contract_gaps == ()
    assert report.unsupported_capability_gaps == ()
    assert all(case.passed for case in report.cases)


def test_orchestrator_rejects_unsupported_resource_and_stop_clears_state() -> None:
    orchestrator = create_nasim_target(driver=FakeDriver()).orchestrator
    unsupported = orchestrator.start(
        OrchestrationPlan(
            operations=[
                OrchestrationOp(
                    action=ChangeAction.CREATE,
                    address="orchestration.script.unsupported",
                    resource_type="script",
                    payload={},
                )
            ]
        ),
        RuntimeSnapshot(),
    )
    assert not unsupported.success
    assert unsupported.diagnostics[0].code == "nasim.orchestration.unsupported-resource"

    created = orchestrator.start(
        OrchestrationPlan(
            operations=[
                OrchestrationOp(
                    action=ChangeAction.CREATE,
                    address="orchestration.workflow.episode",
                    resource_type="workflow",
                    payload={
                        "name": "episode",
                        "result_contract": {"observable_steps": {"participant-action": {}}},
                    },
                )
            ],
            startup_order=["orchestration.workflow.episode"],
        ),
        RuntimeSnapshot(),
    )
    assert orchestrator.status()["running"] is True
    assert set(orchestrator.results()) == {"orchestration.workflow.episode"}
    assert orchestrator.history()["orchestration.workflow.episode"]

    stopped = orchestrator.stop(created.snapshot)
    assert stopped.success
    assert orchestrator.status()["running"] is False
    assert orchestrator.results() == {}

    deleted = orchestrator.start(
        OrchestrationPlan(
            operations=[
                OrchestrationOp(
                    action=ChangeAction.DELETE,
                    address="orchestration.workflow.episode",
                    resource_type="workflow",
                    payload={},
                )
            ]
        ),
        created.snapshot,
    )
    assert deleted.success
    assert "orchestration.workflow.episode" not in deleted.snapshot.entries


def test_evaluator_metadata_only_and_stop() -> None:
    driver = FakeDriver()
    evaluator = NasimEvaluator(driver)

    # A proposition-only change needs no source projection: the evaluator must
    # not read driver facts and must clear evaluator evidence.
    metadata_only = evaluator.start(
        EvaluationPlan(
            operations=[
                EvaluationOp(
                    action=ChangeAction.CREATE,
                    address="evaluation.proposition.sensitive-hosts-owned",
                    resource_type="proposition",
                    payload={"evaluation_basis": "declared_state"},
                )
            ],
            startup_order=["evaluation.proposition.sensitive-hosts-owned"],
        ),
        RuntimeSnapshot(),
    )
    assert metadata_only.success
    assert driver.evaluate_calls == 0
    assert evaluator.capture_spec() is None
    assert evaluator.evidence_records() == ()

    stopped = evaluator.stop(metadata_only.snapshot)
    assert stopped.success
    assert evaluator.results() == {}
