"""Contract-level behavior for the CyberBattleSim backend."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import SimpleNamespace

import pytest
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
from raes_runtime.registry import RuntimeTarget

from raes_adapters.base import run_conformance_probe
from raes_adapters.cyberbattlesim.backend import (
    ACTION_EVIDENCE_REF,
    CYBERBATTLESIM_BACKEND_NAME,
    CyberBattleSimDriver,
    CyberBattleSimEvaluator,
    CyberBattleSimParticipantRuntime,
    CyberBattleSimProvisioner,
    DriverCleanupReport,
    DriverEvaluation,
    DriverResetReport,
    DriverStep,
    create_cyberbattlesim_manifest,
    create_cyberbattlesim_target,
    execute_cyberbattlesim_cleanup,
)
from tests._gym_fixtures import GymFixtureConfig, action_request, cleanup_plan

PARTICIPANT = "participant.behavior.attacker"
OBSERVATION_BOUNDARY = "participant.observation-boundary.attacker-view"
LOCAL_ACTION = "participant.action-contract.local-vulnerability"


@dataclass
class FakeDriver:
    """Deterministic injected driver that retains deliberately private native state."""

    steps: list[DriverStep] = field(default_factory=list)
    evaluation: DriverEvaluation = field(
        default_factory=lambda: DriverEvaluation(
            step_count=0,
            cumulative_reward=0.0,
            terminated=False,
            truncated=False,
            terminal_cause=None,
        )
    )
    construct_calls: int = 0
    reset_calls: list[int | None] = field(default_factory=list)
    step_calls: list[str] = field(default_factory=list)
    evaluate_calls: int = 0
    close_calls: int = 0
    closed: bool = False
    fail_close: bool = False
    fail_step: bool = False
    native_observation: object = field(
        default_factory=lambda: {
            "_explored_network": "must-not-cross",
            "credential_cache": "must-not-cross",
            "action_mask": "must-not-cross",
            "reward_vector": [14.0, -1.0],
        }
    )

    def construct(self) -> None:
        self.construct_calls += 1
        self.closed = False

    def reset(self, seed: int | None) -> DriverResetReport:
        self.reset_calls.append(seed)
        self.closed = False
        return DriverResetReport(
            operation_ref=f"driver.reset.{len(self.reset_calls)}",
            applied_streams=("gym-environment", "gym-action-space"),
            unbound_streams=("python-random", "numpy-global"),
        )

    def step(self, action_kind: str) -> DriverStep:
        self.step_calls.append(action_kind)
        if self.fail_step:
            raise RuntimeError("private native step failure with secret-token")
        if self.steps:
            return self.steps.pop(0)
        return DriverStep(
            operation_ref=f"driver.step.{len(self.step_calls)}",
            step_number=len(self.step_calls),
            source_transition=True,
            processed=True,
            terminated=False,
            truncated=False,
            terminal_cause=None,
        )

    def evaluate(self) -> DriverEvaluation:
        self.evaluate_calls += 1
        return replace(
            self.evaluation,
            projection_ref=(f"{self.evaluation.execution_ref}.evaluation.{self.evaluate_calls}"),
        )

    def close(self) -> DriverCleanupReport:
        self.close_calls += 1
        if self.fail_close:
            raise RuntimeError("private native close failure with secret-token")
        already_closed = self.closed
        self.closed = True
        return DriverCleanupReport(
            operation_ref=f"driver.close.{self.close_calls}",
            closed=True,
            verified=True,
            already_closed=already_closed,
        )

    def verify_closed(self) -> bool:
        return self.closed


_CONFIG = GymFixtureConfig(
    name="cyberbattlesim",
    backend_name=CYBERBATTLESIM_BACKEND_NAME,
    participant_address=PARTICIPANT,
    observation_boundary=OBSERVATION_BOUNDARY,
    action_evidence_ref=ACTION_EVIDENCE_REF,
    implementation_name="cyberbattlesim-credential-cache-policy",
    participant_runtime_name="cyberbattlesim-participant-runtime",
)


def _action_request(
    action_contract_address: str = LOCAL_ACTION,
    *,
    action_instance_id: str = "action-1",
    disclose_action_evidence: bool = True,
    target_addresses: tuple[str, ...] = ("provision.node.entry-client",),
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
                "import sys; import raes_adapters.cyberbattlesim.backend; "
                "assert 'cyberbattle' not in sys.modules; "
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
    manifest = create_cyberbattlesim_manifest()
    target = create_cyberbattlesim_target(driver=driver, seed=20260729)

    assert isinstance(manifest, BackendManifest)
    assert manifest.name == CYBERBATTLESIM_BACKEND_NAME
    assert manifest.has_orchestrator
    assert manifest.has_evaluator
    assert manifest.has_participant_runtime
    assert manifest.has_cleanup
    assert not manifest.has_observation
    assert not manifest.has_time
    assert manifest.participant_runtime is not None
    assert manifest.participant_runtime.supports_bounded_concurrency is False
    assert manifest.participant_runtime.supported_interaction_features == frozenset(
        {"interference"}
    )
    assert manifest.participant_runtime.feature_support[0].support_level.value == ("disclosed_weak")
    assert manifest.constraints["outcome_reproduction"] == "stochastic-bounded"
    assert (
        manifest.constraints["source_identity"]
        == "qualified-complete-runtime-artifact-roots-attested"
    )
    assert manifest.provisioner.supported_content_types == frozenset()
    assert manifest.evaluator.supported_evidence_channels == frozenset({"api_response"})
    assert manifest.evaluator.supported_time_domains == frozenset({"wall_clock"})
    assert {
        "participant-control-occurrence-v1",
        "participant-crossing-occurrence-v1",
        "participant-lifecycle-event-v1",
    } <= manifest.supported_contract_versions
    assert backend_manifest_v2_model(manifest).identity.name == CYBERBATTLESIM_BACKEND_NAME
    assert isinstance(target, RuntimeTarget)
    assert target.name == CYBERBATTLESIM_BACKEND_NAME


def test_provisioner_reconciles_live_driver_and_orchestrator_never_steps_driver() -> None:
    driver = FakeDriver()
    provisioner = CyberBattleSimProvisioner(driver)
    snapshot = RuntimeSnapshot()
    plan = ProvisioningPlan(
        operations=[
            ProvisionOp(
                action=ChangeAction.CREATE,
                address="provision.node.entry-client",
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
    assert applied.snapshot.entries["provision.node.entry-client"].status == "applied"

    target = create_cyberbattlesim_target(driver=driver)
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

    cleaned = execute_cyberbattlesim_cleanup(
        _cleanup_plan(),
        create_cyberbattlesim_manifest(),
        driver,
        receipt_id="cleanup-receipt-reuse",
        execution_attempt_id="cleanup-attempt-reuse",
        trial_outcome="succeeded",
    )
    recreated = provisioner.apply(plan, started.snapshot)

    assert cleaned.cleanup_status == "succeeded"
    assert recreated.success
    assert driver.construct_calls == 3
    assert not driver.closed


def test_unchanged_operations_preserve_snapshots_and_component_state() -> None:
    driver = FakeDriver(
        evaluation=DriverEvaluation(
            step_count=1,
            cumulative_reward=7.0,
            terminated=False,
            truncated=False,
            terminal_cause=None,
        )
    )
    provisioner = CyberBattleSimProvisioner(driver)
    created_provisioning = provisioner.apply(
        ProvisioningPlan(
            operations=[
                ProvisionOp(
                    action=ChangeAction.CREATE,
                    address="provision.node.entry-client",
                    resource_type="node",
                    payload={"node_type": "vm", "os_family": "linux"},
                )
            ]
        ),
        RuntimeSnapshot(),
    )
    unchanged_provisioning = provisioner.apply(
        ProvisioningPlan(
            operations=[
                ProvisionOp(
                    action=ChangeAction.UNCHANGED,
                    address="provision.node.entry-client",
                    resource_type="node",
                    payload={"node_type": "vm", "os_family": "windows"},
                )
            ]
        ),
        created_provisioning.snapshot,
    )
    assert unchanged_provisioning.snapshot is created_provisioning.snapshot
    assert unchanged_provisioning.changed_addresses == []
    assert driver.construct_calls == 1

    orchestrator = create_cyberbattlesim_target(driver=driver).orchestrator
    created_orchestration = orchestrator.start(
        OrchestrationPlan(
            operations=[
                OrchestrationOp(
                    action=ChangeAction.CREATE,
                    address="orchestration.workflow.episode",
                    resource_type="workflow",
                    payload={
                        "name": "episode",
                        "result_contract": {
                            "observable_steps": {"participant-action": {}},
                        },
                    },
                )
            ]
        ),
        created_provisioning.snapshot,
    )
    orchestration_status = orchestrator.status()
    unchanged_orchestration = orchestrator.start(
        OrchestrationPlan(
            operations=[
                OrchestrationOp(
                    action=ChangeAction.UNCHANGED,
                    address="orchestration.workflow.episode",
                    resource_type="workflow",
                    payload={"name": "replacement-must-not-apply"},
                )
            ]
        ),
        created_orchestration.snapshot,
    )
    assert unchanged_orchestration.snapshot is created_orchestration.snapshot
    assert unchanged_orchestration.changed_addresses == []
    assert orchestrator.status() == orchestration_status

    evaluator = CyberBattleSimEvaluator(driver)
    created_evaluation = evaluator.start(
        EvaluationPlan(
            operations=[
                EvaluationOp(
                    action=ChangeAction.CREATE,
                    address="evaluation.objective.own-network",
                    resource_type="objective",
                    payload={
                        "result_contract": {
                            "resource_type": "objective",
                            "supports_score": True,
                            "fixed_max_score": 5000,
                        }
                    },
                )
            ]
        ),
        created_orchestration.snapshot,
    )
    evaluation_status = evaluator.status()
    unchanged_evaluation = evaluator.start(
        EvaluationPlan(
            operations=[
                EvaluationOp(
                    action=ChangeAction.UNCHANGED,
                    address="evaluation.objective.own-network",
                    resource_type="objective",
                    payload={
                        "result_contract": {
                            "resource_type": "objective",
                            "supports_score": True,
                            "fixed_max_score": 1,
                        }
                    },
                )
            ]
        ),
        created_evaluation.snapshot,
    )
    assert unchanged_evaluation.snapshot is created_evaluation.snapshot
    assert unchanged_evaluation.changed_addresses == []
    assert evaluator.status() == evaluation_status
    assert driver.evaluate_calls == 1


def test_each_admitted_action_has_one_driver_operation_and_typed_terminal_result() -> None:
    driver = FakeDriver()
    runtime = CyberBattleSimParticipantRuntime(driver, seed=20260729)
    initialized = runtime.initialize(
        ParticipantEpisodeInitializeRequest(
            participant_address=PARTICIPANT,
            episode_id="episode-1",
        ),
        RuntimeSnapshot(),
    )

    result = runtime.admit_action(_action_request(), initialized.snapshot)

    assert result.success
    assert driver.step_calls == ["local-vulnerability"]
    assert isinstance(result.action_result, ParticipantActionResultModel)
    assert result.action_result.status == "succeeded"
    assert result.action_result.participant_address == PARTICIPANT
    assert result.action_result.episode_id == "episode-1"
    assert result.action_result.action_instance_id == "action-1"
    assert result.action_result.action_contract_address == LOCAL_ACTION
    assert result.action_result.evidence_refs == [ACTION_EVIDENCE_REF]
    assert result.action_result.effects[0].target_refs == []
    assert runtime.driver_operation_ref("action-1") == "driver.step.1"
    observations = runtime.observations(PARTICIPANT)
    assert len(observations) == 1
    assert observations[0].participant_address == PARTICIPANT
    assert observations[0].hidden_state_refs == []
    assert observations[0].centralized_state_refs == []
    portable = str(
        {
            "result": result.action_result.model_dump(mode="json"),
            "observation": observations[0].model_dump(mode="json"),
            "snapshot": result.snapshot.participant_behavior_history,
        }
    )
    for forbidden in (
        "_explored_network",
        "credential_cache",
        "action_mask",
        "reward_vector",
        "must-not-cross",
        "driver.step.1",
    ):
        assert forbidden not in portable
    assert runtime.observations("participant.agent.defender") == ()


def test_unsupported_action_is_rejected_before_native_mutation() -> None:
    driver = FakeDriver()
    runtime = CyberBattleSimParticipantRuntime(driver)
    initialized = runtime.initialize(
        ParticipantEpisodeInitializeRequest(
            participant_address=PARTICIPANT,
            episode_id="episode-unsupported",
        ),
        RuntimeSnapshot(),
    )

    result = runtime.admit_action(
        _action_request(
            "participant.action-contract.scan-and-reimage",
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
    runtime = CyberBattleSimParticipantRuntime(driver)
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

    failing_runtime = CyberBattleSimParticipantRuntime(FakeDriver(fail_step=True))
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

    result = CyberBattleSimProvisioner(driver).apply(plan, RuntimeSnapshot())

    assert not result.success
    assert driver.construct_calls == 0
    assert result.diagnostics[0].code == "cyberbattlesim.provisioning.unsupported-resource"


def test_evaluator_reads_distinct_facts_without_advancing_or_leaking_to_participant() -> None:
    driver = FakeDriver(
        evaluation=DriverEvaluation(
            step_count=1,
            cumulative_reward=14.0,
            terminated=False,
            truncated=False,
            terminal_cause=None,
        )
    )
    runtime = CyberBattleSimParticipantRuntime(driver)
    initialized = runtime.initialize(
        ParticipantEpisodeInitializeRequest(
            participant_address=PARTICIPANT,
            episode_id="episode-evaluation",
        ),
        RuntimeSnapshot(),
    )
    action = runtime.admit_action(_action_request(), initialized.snapshot)
    evaluator = CyberBattleSimEvaluator(driver)
    evaluation_plan = EvaluationPlan(
        operations=[
            EvaluationOp(
                action=ChangeAction.CREATE,
                address="evaluation.objective.own-network",
                resource_type="objective",
                payload={
                    "result_contract": {
                        "resource_type": "objective",
                        "supports_score": True,
                        "fixed_max_score": 5000,
                    }
                },
            )
        ],
        startup_order=["evaluation.objective.own-network"],
    )

    evaluated = evaluator.start(evaluation_plan, action.snapshot)

    assert evaluated.success
    assert driver.step_calls == ["local-vulnerability"]
    assert driver.evaluate_calls == 1
    assert evaluator.results()["evaluation.objective.own-network"]["score"] == 14.0
    assert "14.0" not in str(action.action_result.model_dump(mode="json"))
    assert ACTION_EVIDENCE_REF not in str(evaluator.results())
    evidence_records = evaluator.evidence_records()
    derived_measures = evaluator.derived_measures()
    capture_spec = evaluator.capture_spec()
    assert isinstance(capture_spec, ExperimentCaptureSpecModel)
    assert len(evidence_records) == len(derived_measures) == 1
    assert isinstance(evidence_records[0], ExperimentEvidenceRecordModel)
    assert isinstance(derived_measures[0], ExperimentDerivedMeasureModel)
    assert evidence_records[0].capture_spec_ref.ref_id == capture_spec.capture_spec_id
    assert derived_measures[0].value == 14.0
    assert derived_measures[0].limitations
    assert "deterministic replay" in derived_measures[0].limitations[0]
    raw_content = evidence_records[0].raw_content
    assert raw_content.payload_summary is not None
    assert raw_content.content_checksum is not None
    assert raw_content.content_checksum.algorithm == "sha256"
    assert (
        raw_content.content_checksum.value
        == hashlib.sha256(raw_content.payload_summary.encode("utf-8")).hexdigest()
    )
    portable_evaluation = str(
        {
            "evidence": evidence_records[0].model_dump(mode="json"),
            "measure": derived_measures[0].model_dump(mode="json"),
        }
    )
    for forbidden in (
        "_explored_network",
        "credential_cache",
        "action_mask",
        "reward_vector",
        "must-not-cross",
    ):
        assert forbidden not in portable_evaluation

    first_evidence = evidence_records[0]
    first_measure = derived_measures[0]
    first_capture_spec = capture_spec
    driver.evaluation = replace(driver.evaluation, cumulative_reward=21.0)
    reevaluated = evaluator.start(evaluation_plan, evaluated.snapshot)
    second_evidence = evaluator.evidence_records()[0]
    second_measure = evaluator.derived_measures()[0]
    second_capture_spec = evaluator.capture_spec()

    assert reevaluated.success
    assert isinstance(second_capture_spec, ExperimentCaptureSpecModel)
    assert first_evidence.evidence_record_id != second_evidence.evidence_record_id
    assert first_measure.derived_measure_id != second_measure.derived_measure_id
    assert first_capture_spec.capture_spec_id != second_capture_spec.capture_spec_id
    assert (
        first_capture_spec.capture_windows[0].window_id
        != second_capture_spec.capture_windows[0].window_id
    )
    assert second_measure.value == 21.0
    assert second_evidence.run_ref.ref_id == driver.evaluation.execution_ref
    assert (
        reevaluated.snapshot.evaluation_results["evaluation.objective.own-network"]["run_id"]
        == second_evidence.run_ref.ref_id
    )
    assert second_evidence.capture_spec_ref.ref_id == second_capture_spec.capture_spec_id
    assert second_evidence.capture_window_ref == second_capture_spec.capture_windows[0].window_id
    assert second_measure.source_evidence_refs[0].ref_id == second_evidence.evidence_record_id
    assert reevaluated.snapshot.evaluation_results["evaluation.objective.own-network"][
        "evidence_refs"
    ] == [second_evidence.evidence_record_id]


def test_source_termination_closes_episode_and_restart_resets_same_seed() -> None:
    driver = FakeDriver(
        steps=[
            DriverStep(
                operation_ref="driver.step.terminal",
                step_number=1,
                source_transition=True,
                processed=True,
                terminated=True,
                truncated=False,
                terminal_cause="source-terminated",
            )
        ]
    )
    runtime = CyberBattleSimParticipantRuntime(driver, seed=20260729)
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
    assert driver.reset_calls == [20260729, 20260729]
    assert restarted.snapshot.participant_episode_results[PARTICIPANT]["previous_episode_id"] == (
        "episode-terminal"
    )


def test_cleanup_is_idempotent_verified_and_preserves_bounded_failure() -> None:
    driver = FakeDriver()
    manifest = create_cyberbattlesim_manifest()
    plan = _cleanup_plan()

    first = execute_cyberbattlesim_cleanup(
        plan,
        manifest,
        driver,
        receipt_id="cleanup-receipt-1",
        execution_attempt_id="cleanup-attempt-1",
        trial_outcome="succeeded",
    )
    second = execute_cyberbattlesim_cleanup(
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
    assert all(result.status == "succeeded" for result in second.obligation_results.values())

    failing_driver = FakeDriver(fail_close=True)
    failed = execute_cyberbattlesim_cleanup(
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
        / "cyberbattlesim"
        / "scenario"
        / "cyberbattle-chain.sdl.yaml"
    )
    driver = FakeDriver(
        evaluation=DriverEvaluation(
            step_count=1,
            cumulative_reward=7.0,
            terminated=False,
            truncated=False,
            terminal_cause=None,
        )
    )
    target = create_cyberbattlesim_target(driver=driver, seed=20260729)
    realized = ReferenceProcessor.realize(
        scenario,
        target.manifest,
        parameters={"chain_size": 10},
        target_name=CYBERBATTLESIM_BACKEND_NAME,
    )

    assert realized.is_valid
    assert realized.diagnostics == ()
    assert len(realized.execution_plan.provisioning.operations) == 7
    assert len(realized.execution_plan.evaluation.operations) == 6

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
    orchestration_receipt = control_plane.submit_orchestration(
        realized.execution_plan.orchestration,
        idempotency_key="selected-scenario-orchestration",
        request_fingerprint="selected-scenario-orchestration-v1",
    )

    receipts = (
        provisioning_receipt,
        initialize_receipt,
        action_receipt,
        evaluation_receipt,
        orchestration_receipt,
    )
    assert all(receipt.accepted for receipt in receipts)
    assert all(
        control_plane.get_operation(receipt.operation_id).state == OperationState.SUCCEEDED
        for receipt in receipts
    )
    assert repeated_action_receipt.operation_id == action_receipt.operation_id
    truth_results = control_plane.snapshot.proposition_truth_results
    assert set(truth_results) == {
        "evaluation.assertion.ownership-postcondition",
        "evaluation.assertion.sla-invariant",
    }
    assert {result["proposition_outcome"] for result in truth_results.values()} == {"unknown"}
    objective_results = control_plane.snapshot.evaluation_results
    assert {
        objective_results["evaluation.objective.own-network"]["status"],
        objective_results["evaluation.objective.maintain-availability"]["status"],
    } == {"running"}
    assert all(result["passed"] is None for result in objective_results.values())
    assert driver.step_calls == ["local-vulnerability"]
    assert driver.evaluate_calls == 1

    cleaned = execute_cyberbattlesim_cleanup(
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
    report = run_conformance_probe(
        create_cyberbattlesim_target(driver=FakeDriver()),
    )

    assert report.passed
    assert report.unsupported_contract_gaps == ()
    assert report.unsupported_capability_gaps == ()
    assert all(case.passed for case in report.cases)


def test_live_driver_is_lazy_seed_bounded_and_performs_exactly_one_native_step(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class NumericRuntime:
        int32 = "int32"

        @staticmethod
        def argwhere(mask: list[tuple[int, int]]) -> list[tuple[int, int]]:
            return mask

        @staticmethod
        def asarray(
            value: tuple[int, int],
            *,
            dtype: object,
        ) -> tuple[int, int]:
            assert dtype == NumericRuntime.int32
            return value

    class NativeEnvironment:
        def __init__(self) -> None:
            self.action_space = SimpleNamespace(seed=self.seed_action_space)
            self.action_space_seeds: list[int] = []
            self.reset_seeds: list[int | None] = []
            self.native_steps: list[dict[str, object]] = []
            self.close_calls = 0

        def seed_action_space(self, seed: int) -> None:
            self.action_space_seeds.append(seed)

        def reset(self, *, seed: int | None) -> tuple[dict[str, object], dict[str, object]]:
            self.reset_seeds.append(seed)
            return (
                {
                    "action_mask": {
                        "connect": [(0, 0)],
                        "local_vulnerability": [(0, 1)],
                        "remote_vulnerability": [(0, 0)],
                    },
                    "credential_cache": ["native-secret"],
                },
                {"native-info": "must-not-cross"},
            )

        def step(
            self,
            action: dict[str, object],
        ) -> tuple[dict[str, object], float, bool, bool, dict[str, object]]:
            self.native_steps.append(action)
            observation, _ = self.reset(seed=None)
            return observation, -3.5, False, False, {"native-info": "must-not-cross"}

        def close(self) -> None:
            self.close_calls += 1

    environment = NativeEnvironment()
    selected_configuration: dict[str, object] = {}
    source_content = {
        "cyberbattle/__init__.py": b"selected cyberbattle package",
        "cyberbattle/_env/cyberbattle_env.py": b"selected cyberbattle environment",
        "cyberbattle/_env/defender.py": b"selected defender",
        "cyberbattle/_env/cyberbattle_chain.py": b"selected chain registration",
        "cyberbattle/samples/chainpattern/chainpattern.py": b"selected chain generator",
        "cyberbattle/simulation/model.py": b"selected transitive runtime module",
    }
    source_root = tmp_path / "selected-distribution"
    for source_path, content in source_content.items():
        installed_source = source_root / source_path
        installed_source.parent.mkdir(parents=True, exist_ok=True)
        installed_source.write_bytes(content)

    class SelectedDistribution:
        def __init__(
            self,
            version: str,
            root: Path,
            files: tuple[str, ...],
        ) -> None:
            self.version = version
            self.root = root
            self.files = files
            self.direct_url_text: str | None = None

        def locate_file(self, path: str) -> Path:
            return self.root / path

        def read_text(self, filename: str) -> str | None:
            if filename == "direct_url.json":
                return self.direct_url_text
            return None

    dependency_roots = {
        "gymnasium": tmp_path / "gymnasium-distribution",
        "numpy": tmp_path / "numpy-distribution",
    }
    for package_name, dependency_root in dependency_roots.items():
        package_init = dependency_root / package_name / "__init__.py"
        package_init.parent.mkdir(parents=True)
        package_init.write_bytes(f"selected {package_name}".encode())
    distributions = {
        "cyberbattlesim": SelectedDistribution(
            "0.1.0",
            source_root,
            tuple(source_content),
        ),
        "gymnasium": SelectedDistribution(
            "0.29.1",
            dependency_roots["gymnasium"],
            ("gymnasium/__init__.py",),
        ),
        "numpy": SelectedDistribution(
            "1.26.4",
            dependency_roots["numpy"],
            ("numpy/__init__.py",),
        ),
    }
    module_origins = {
        "cyberbattle": source_root / "cyberbattle/__init__.py",
        "cyberbattle._env.cyberbattle_env": (source_root / "cyberbattle/_env/cyberbattle_env.py"),
        "cyberbattle._env.defender": source_root / "cyberbattle/_env/defender.py",
        "gymnasium": dependency_roots["gymnasium"] / "gymnasium/__init__.py",
        "numpy": dependency_roots["numpy"] / "numpy/__init__.py",
    }

    def make_environment(name: str, **kwargs: object) -> SimpleNamespace:
        selected_configuration["name"] = name
        selected_configuration.update(kwargs)
        return SimpleNamespace(unwrapped=environment)

    class Configuration:
        def __init__(self, **kwargs: object) -> None:
            self.values = kwargs

    modules = {
        "cyberbattle": SimpleNamespace(),
        "gymnasium": SimpleNamespace(make=make_environment),
        "numpy": NumericRuntime,
        "cyberbattle._env.cyberbattle_env": SimpleNamespace(
            AttackerGoal=Configuration,
            DefenderConstraint=Configuration,
        ),
        "cyberbattle._env.defender": SimpleNamespace(
            ScanAndReimageCompromisedMachines=Configuration,
        ),
    }
    imported_modules: list[str] = []

    def import_selected_module(name: str) -> object:
        imported_modules.append(name)
        return modules[name]

    runtime_tree_digest = hashlib.sha256()
    for source_path, content in sorted(source_content.items()):
        runtime_tree_digest.update(source_path.encode())
        runtime_tree_digest.update(b"\0")
        runtime_tree_digest.update(hashlib.sha256(content).hexdigest().encode())
        runtime_tree_digest.update(b"\n")

    def runtime_root_record(
        root_path: str,
        content_by_path: dict[str, bytes],
    ) -> dict[str, object]:
        digest = hashlib.sha256()
        selected_paths = sorted(
            path
            for path in content_by_path
            if path == root_path or path.startswith(f"{root_path}/")
        )
        for selected_path in selected_paths:
            digest.update(selected_path.encode())
            digest.update(b"\0")
            digest.update(hashlib.sha256(content_by_path[selected_path]).hexdigest().encode())
            digest.update(b"\n")
        return {
            "path": root_path,
            "file_count": len(selected_paths),
            "sha256": digest.hexdigest(),
        }

    dependency_content = {
        package_name: {f"{package_name}/__init__.py": f"selected {package_name}".encode()}
        for package_name in dependency_roots
    }
    monkeypatch.setattr(
        "raes_adapters._source_admission.distribution",
        lambda name: distributions[name],
    )
    monkeypatch.setattr(
        "raes_adapters._source_admission.find_spec",
        lambda name: SimpleNamespace(origin=str(module_origins[name])),
    )
    selected_qualification = {
        "source": {
            "package": "cyberbattlesim",
            "version": "0.1.0",
        },
        "source_files": [
            {
                "path": path,
                "sha256": hashlib.sha256(content).hexdigest(),
            }
            for path, content in source_content.items()
        ],
        "runtime_source_tree": {
            "file_count": len(source_content),
            "sha256": runtime_tree_digest.hexdigest(),
        },
        "runtime_artifacts": [
            {
                "name": "cyberbattlesim",
                "version": "0.1.0",
                "artifact": {
                    "filename": "cyberbattlesim-0.1.0-py3-none-any.whl",
                    "sha256": "1" * 64,
                    "require_direct_archive_sha256": False,
                    "runtime_identity": "complete-root-tree",
                },
                "roots": [runtime_root_record("cyberbattle", source_content)],
            },
            {
                "name": "gymnasium",
                "version": "0.29.1",
                "artifact": {
                    "filename": "gymnasium-0.29.1-py3-none-any.whl",
                    "sha256": "2" * 64,
                    "require_direct_archive_sha256": True,
                    "runtime_identity": "complete-root-tree",
                },
                "roots": [
                    runtime_root_record(
                        "gymnasium",
                        dependency_content["gymnasium"],
                    )
                ],
            },
            {
                "name": "numpy",
                "version": "1.26.4",
                "artifact": {
                    "filename": "numpy-1.26.4-cp312-manylinux.whl",
                    "sha256": "3" * 64,
                    "require_direct_archive_sha256": True,
                    "runtime_identity": "complete-root-tree",
                },
                "roots": [
                    runtime_root_record(
                        "numpy",
                        dependency_content["numpy"],
                    )
                ],
            },
        ],
        "dependencies": [
            {"name": "cyberbattlesim", "version": "0.1.0"},
            {"name": "gymnasium", "version": "0.29.1"},
            {"name": "numpy", "version": "1.26.4"},
        ],
        "protocol": {
            "selection": {
                "scenario": {
                    "gym_id": "CyberBattleChain-v0",
                    "size": 10,
                },
                "termination": {
                    "attacker_own_atleast": 0,
                    "attacker_own_atleast_percent": 1.0,
                    "defender_maintain_sla": 0.8,
                    "evaluator_cutoff_steps": 1,
                },
                "defender": {
                    "probability": 0.6,
                    "scan_capacity": 2,
                    "scan_frequency": 5,
                },
            }
        },
    }
    monkeypatch.setattr(
        "raes_adapters.cyberbattlesim.backend.driver.load_qualification",
        lambda: selected_qualification,
    )
    monkeypatch.setattr(
        "raes_adapters.cyberbattlesim.backend.driver.importlib.import_module",
        import_selected_module,
    )
    driver = CyberBattleSimDriver()

    reset = driver.reset(20260729)
    step = driver.step("local-vulnerability")
    evaluation = driver.evaluate()
    first_close = driver.close()
    second_close = driver.close()

    assert selected_configuration["name"] == "CyberBattleChain-v0"
    assert selected_configuration["size"] == 10
    assert reset.applied_streams == ("gym-environment", "gym-action-space")
    assert reset.unbound_streams == ("python-random", "numpy-global")
    assert environment.reset_seeds[0] == 20260729
    assert environment.action_space_seeds == [20260729]
    assert len(environment.native_steps) == 1
    assert tuple(environment.native_steps[0]) == ("local_vulnerability",)
    assert step.source_transition
    assert step.processed
    assert step.step_number == 1
    assert step.terminal_cause == "evaluator-cutoff"
    assert evaluation.cumulative_reward == -3.5
    assert evaluation.terminal_cause == "evaluator-cutoff"
    assert evaluation.execution_ref == reset.operation_ref
    assert evaluation.projection_ref == f"{reset.operation_ref}.evaluation.1"
    assert first_close.verified
    assert not first_close.already_closed
    assert second_close.verified
    assert second_close.already_closed
    assert environment.close_calls == 1

    imported_modules.clear()
    transitive_source = source_root / "cyberbattle/simulation/model.py"
    transitive_source.write_bytes(b"tampered transitive runtime module")
    tampered_driver = CyberBattleSimDriver()
    with pytest.raises(
        RuntimeError,
        match="selected simulator dependency identity could not be verified",
    ):
        tampered_driver.construct()
    assert imported_modules == []

    transitive_source.write_bytes(source_content["cyberbattle/simulation/model.py"])
    injected_extension = source_root / "cyberbattle/_env/cyberbattle_env.so"
    injected_extension.write_bytes(b"unqualified native extension")
    injected_driver = CyberBattleSimDriver()
    with pytest.raises(
        RuntimeError,
        match="selected simulator dependency identity could not be verified",
    ):
        injected_driver.construct()
    assert imported_modules == []

    injected_extension.unlink()
    distributions[
        "cyberbattlesim"
    ].direct_url_text = '{"dir_info":{"editable":true},"url":"file:///unqualified/source"}'
    editable_driver = CyberBattleSimDriver()
    with pytest.raises(
        RuntimeError,
        match="selected simulator dependency identity could not be verified",
    ):
        editable_driver.construct()
    assert imported_modules == []

    distributions["cyberbattlesim"].direct_url_text = None
    module_origins["cyberbattle"] = tmp_path / "unselected/cyberbattle/__init__.py"
    unselected_driver = CyberBattleSimDriver()
    with pytest.raises(
        RuntimeError,
        match="selected simulator module origin could not be verified",
    ):
        unselected_driver.construct()
    assert imported_modules == []
