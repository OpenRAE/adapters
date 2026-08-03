"""Contract-level behavior for the PrimAITE backend."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from raes_backend_protocols.backend_manifest import BackendManifest
from raes_backend_protocols.manifest import backend_manifest_v2_model
from raes_contracts.contracts import (
    ApparatusIdentityModel,
    CleanStateRequirementModel,
    CleanupObligationModel,
    CleanupResourceBoundaryModel,
    ExecutionRetryPolicyModel,
    ExperimentEvidenceRecordModel,
    ParticipantActionResultModel,
    ParticipantExposurePolicyModel,
    ParticipantImplementationCapabilitiesModel,
    ParticipantImplementationCompatibilityModel,
    ParticipantImplementationManifestModel,
    ParticipantImplementationSelectionModel,
    TrialCleanupPlanModel,
)
from raes_contracts.participant_action_arguments import ParticipantValidatedActionSelection
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest
from raes_contracts.participant_episode import ParticipantEpisodeInitializeRequest
from raes_contracts.planning import (
    ChangeAction,
    EvaluationOp,
    EvaluationPlan,
    OrchestrationOp,
    OrchestrationPlan,
    ProvisioningPlan,
    ProvisionOp,
)
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_runtime.registry import RuntimeTarget

from raes_adapters.primaite.backend import (
    ACTION_EVIDENCE_REF,
    PRIMAITE_BACKEND_NAME,
    DriverCleanupReport,
    DriverEvaluation,
    DriverResetReport,
    DriverStep,
    PrimaiteDriver,
    PrimaiteEvaluator,
    PrimaiteOrchestrator,
    PrimaiteParticipantRuntime,
    PrimaiteProvisioner,
    create_primaite_manifest,
    create_primaite_realization_envelope,
    create_primaite_target,
    execute_primaite_cleanup,
    primaite_declared_weaknesses,
    primaite_manifest_capability_evidence,
    primaite_manifest_capability_evidence_gaps,
    primaite_source_protocol_diagnostics,
    run_primaite_conformance,
)

PARTICIPANT = "participant.behavior.blue-defender"
OBSERVATION_BOUNDARY = "participant.observation-boundary.defender-view"
SERVICE_CONTROL = "participant.action-contract.service-control"

_LEAKAGE_MARKERS = (
    "must-not-cross",
    "native_observation_vector",
    "action_mask",
    "reward_components",
    "<primaite",
    "Box(1652)",
    "secret-token",
)


@dataclass
class FakeDriver:
    """Deterministic injected driver retaining deliberately private native state.

    By default ``step`` reports an unrepresentable action (the honest live
    behavior for the current evidence). A representable transition is exercised
    by passing an explicit ``step_result``.
    """

    step_result: DriverStep | None = None
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
    fail_step: bool = False
    fail_close: bool = False
    fail_reset: bool = False
    fail_construct: bool = False
    native_observation: object = field(
        default_factory=lambda: {
            "native_observation_vector": "must-not-cross",
            "action_mask": "must-not-cross",
            "info": "must-not-cross",
            "reward_components": [0.40, 0.25, 0.05],
        }
    )

    def construct(self) -> None:
        self.construct_calls += 1
        if self.fail_construct:
            raise RuntimeError("private native construct failure with secret-token")
        self.closed = False

    def reset(self, seed: int | None) -> DriverResetReport:
        self.reset_calls.append(seed)
        if self.fail_reset:
            raise RuntimeError("private native reset failure with secret-token")
        self.closed = False
        broken = ("gym-reset-seam", "python-random") if seed is not None else ("gym-reset-seam",)
        return DriverResetReport(
            operation_ref=f"driver.reset.{len(self.reset_calls)}",
            applied_streams=(),
            broken_streams=broken,
            absent_streams=("torch",),
            unbound_streams=("numpy-global",),
        )

    def step(self, action_contract: str) -> DriverStep:
        self.step_calls.append(action_contract)
        if self.fail_step:
            raise RuntimeError("private native step failure with secret-token")
        operation_ref = f"driver.step.{len(self.step_calls)}"
        if self.step_result is not None:
            return replace(self.step_result, operation_ref=operation_ref)
        return DriverStep(
            operation_ref=operation_ref,
            step_number=0,
            representable=False,
            source_transition=False,
            processed=False,
            terminated=False,
            truncated=False,
            terminal_cause=None,
            rejection_reason="unrepresentable-action",
        )

    def evaluate(self) -> DriverEvaluation:
        self.evaluate_calls += 1
        return replace(
            self.evaluation,
            projection_ref=f"{self.evaluation.execution_ref}.evaluation.{self.evaluate_calls}",
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
            workspace_removed=True,
        )

    def verify_closed(self) -> bool:
        return self.closed


def _realization_identity() -> object:
    """Return the selected realization envelope identity for provisioning joins."""

    manifest = create_primaite_manifest()
    assert manifest.realization_envelope is not None
    return manifest.realization_envelope.identity


def _provision_plan(operations: list[ProvisionOp]) -> ProvisioningPlan:
    """Build a provisioning plan bound to the selected realization envelope."""

    return ProvisioningPlan(operations=operations, realization_envelope=_realization_identity())


def _representable_step(*, truncated: bool = False) -> DriverStep:
    """A representable aggregate transition for fake-driver mechanics tests."""

    return DriverStep(
        operation_ref="driver.step.pending",
        step_number=1,
        representable=True,
        source_transition=True,
        processed=True,
        terminated=False,
        truncated=truncated,
        terminal_cause="fixed-horizon-truncation" if truncated else None,
    )


def _participant_manifest() -> ParticipantImplementationManifestModel:
    contracts = [
        "participant-implementation-manifest-v1",
        "participant-implementation-provenance-v1",
        "participant-episode-state-envelope-v1",
        "participant-episode-history-event-stream-v1",
        "participant-behavior-history-event-stream-v1",
        "participant-decision-surface-v2",
    ]
    return ParticipantImplementationManifestModel(
        identity=ApparatusIdentityModel(name="primaite-blue-defender-policy", version="1.0.0"),
        implementation_kind="policy",
        supported_contract_versions=contracts,
        compatibility=ParticipantImplementationCompatibilityModel(
            participant_runtimes=["primaite-participant-runtime"],
            backends=[PRIMAITE_BACKEND_NAME],
        ),
        concept_bindings=[
            {"scope": "implementation_kind", "family": "apparatus-declarations"},
            {
                "scope": "capabilities.supported_participant_contracts",
                "family": "apparatus-declarations",
            },
            {
                "scope": "capabilities.supported_decision_surface_modes",
                "family": "apparatus-declarations",
            },
            {"scope": "capabilities.tool_affordance_expectations", "family": "tools-and-artifacts"},
            {"scope": "capabilities.exposure_policy_kinds", "family": "provenance-and-evidence"},
        ],
        capabilities=ParticipantImplementationCapabilitiesModel(
            supported_participant_contracts=[
                "participant-episode-state-envelope-v1",
                "participant-episode-history-event-stream-v1",
                "participant-behavior-history-event-stream-v1",
                "participant-decision-surface-v2",
            ],
            supported_decision_surface_modes=["policy-directed"],
            tool_affordance_expectations=["credential-store"],
            exposure_policy_kinds=["hidden-truth", "observation-stream"],
        ),
    )


def _action_request(
    action_contract_address: str = SERVICE_CONTROL,
    *,
    action_instance_id: str = "action-1",
    disclose_action_evidence: bool = True,
) -> ParticipantActionAdmissionRequest:
    manifest = _participant_manifest()
    exposure_policy = ParticipantExposurePolicyModel(
        policy_id="primaite-defender-view",
        exposure_policy_kinds=["hidden-truth", "observation-stream"],
        disclosed_refs=[OBSERVATION_BOUNDARY],
        withheld_refs=["evidence.primaite.hidden-world"],
        visibility_scope_refs=[PARTICIPANT],
    )
    selection = ParticipantImplementationSelectionModel(
        participant_address=PARTICIPANT,
        implementation_identity=manifest.identity,
        manifest_ref="manifest.primaite.blue-defender-policy",
        manifest_digest="sha256:" + "1" * 64,
        selected_decision_surface_mode="policy-directed",
        participant_contract_versions=[
            "participant-episode-state-envelope-v1",
            "participant-behavior-history-event-stream-v1",
            "participant-decision-surface-v2",
        ],
        exposure_policy=exposure_policy,
    )
    return ParticipantActionAdmissionRequest(
        participant_address=PARTICIPANT,
        action_contract_address=action_contract_address,
        observation_boundary_address=OBSERVATION_BOUNDARY,
        action_instance_id=action_instance_id,
        implementation_manifest=manifest,
        implementation_selection=selection,
        visible_refs=(OBSERVATION_BOUNDARY,),
        disclosed_refs=(OBSERVATION_BOUNDARY,),
        observation_boundary_evidence_refs=(
            (ACTION_EVIDENCE_REF,) if disclose_action_evidence else ()
        ),
        validated_selection=ParticipantValidatedActionSelection(
            action_contract_address=action_contract_address,
            argument_shape_ref="argument-shape.primaite.selected-action",
            proposal_ref=f"proposal.{action_instance_id}",
            normalized_arguments=(),
            loss_disclosure_refs=("loss-abstracted-participant-interface",),
        ),
        target_addresses=("provision.node.database-host",),
        requires_terminal_outcome=True,
    )


def _cleanup_plan(*, required: bool = True) -> TrialCleanupPlanModel:
    boundary = CleanupResourceBoundaryModel(
        boundary_id="primaite-process",
        resource_kind="in-process-simulator",
        owner_ref=PRIMAITE_BACKEND_NAME,
        resource_refs=["runtime.primaite.selected-environment"],
    )
    destroy = CleanupObligationModel(
        obligation_id="destroy-environment",
        boundary_refs=[boundary.boundary_id],
        action_kind="destroy",
        triggers=["success", "failure"],
        requirement="required" if required else "best-effort",
        idempotency="idempotent",
        verification_probe_refs=["probe:primaite-closed"],
        timeout_seconds=5,
    )
    verify = CleanupObligationModel(
        obligation_id="verify-environment-closed",
        boundary_refs=[boundary.boundary_id],
        action_kind="verify",
        triggers=["success", "failure"],
        requirement="best-effort",
        depends_on=[destroy.obligation_id],
        idempotency="idempotent",
        verification_probe_refs=["probe:primaite-closed"],
        timeout_seconds=5,
    )
    return TrialCleanupPlanModel(
        plan_id="primaite-cleanup",
        plan_entry_id="primaite-cleanup-entry",
        run_id="primaite-run",
        clean_state=CleanStateRequirementModel(
            mode="verified-reset",
            boundary_refs=[boundary.boundary_id],
            verification_probe_refs=["probe:primaite-closed"],
        ),
        resource_boundaries={boundary.boundary_id: boundary},
        cleanup_obligations={destroy.obligation_id: destroy, verify.obligation_id: verify},
        retry_policy=ExecutionRetryPolicyModel(max_attempts=1, after_effect_policy="disallow"),
    )


def _initialized_runtime(
    driver: FakeDriver,
    *,
    seed: int | None = None,
    episode_id: str = "episode-1",
) -> tuple[PrimaiteParticipantRuntime, RuntimeSnapshot]:
    runtime = PrimaiteParticipantRuntime(driver, seed=seed)
    initialized = runtime.initialize(
        ParticipantEpisodeInitializeRequest(
            participant_address=PARTICIPANT,
            episode_id=episode_id,
        ),
        RuntimeSnapshot(),
    )
    return runtime, initialized.snapshot


def test_backend_import_is_dependency_light_and_lazy() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            (
                "import sys\n"
                "import raes_adapters.base\n"
                "import raes_adapters.primaite.backend as backend\n"
                "backend.create_primaite_manifest()\n"
                "backend.create_primaite_target()\n"
                "assert 'primaite.session.environment' not in sys.modules\n"
                "assert 'gymnasium' not in sys.modules\n"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_manifest_and_target_claim_exact_surfaces_with_realization_envelope() -> None:
    driver = FakeDriver()
    manifest = create_primaite_manifest()
    target = create_primaite_target(driver=driver, seed=20260802)

    assert isinstance(manifest, BackendManifest)
    assert manifest.name == PRIMAITE_BACKEND_NAME
    assert manifest.has_orchestrator
    assert manifest.has_evaluator
    assert manifest.has_participant_runtime
    assert manifest.has_cleanup
    assert manifest.realization_envelope is not None
    assert manifest.realization_envelope == create_primaite_realization_envelope()
    assert manifest.participant_runtime is not None
    assert manifest.participant_runtime.supported_participant_roles == frozenset({"blue"})
    disclosed = {
        support.feature: support.support_level.value
        for support in manifest.participant_runtime.feature_support
    }
    assert disclosed["action_contracts"] == "disclosed_weak"
    assert manifest.constraints["runtime_claim"] == "live source qualified on CPython 3.11 only"
    assert "realization-envelope-v1" in manifest.supported_contract_versions
    assert backend_manifest_v2_model(manifest).identity.name == PRIMAITE_BACKEND_NAME
    assert isinstance(target, RuntimeTarget)
    assert target.name == PRIMAITE_BACKEND_NAME


def test_provisioner_reconciles_driver_and_orchestrator_never_steps() -> None:
    driver = FakeDriver()
    provisioner = PrimaiteProvisioner(driver, _realization_identity())
    plan = _provision_plan(
        [
            ProvisionOp(
                action=ChangeAction.CREATE,
                address="provision.node.database-host",
                resource_type="node",
                payload={"node_type": "vm", "os_family": "linux"},
            )
        ]
    )

    applied = provisioner.apply(plan, RuntimeSnapshot())
    assert applied.success
    assert driver.construct_calls == 1
    assert applied.snapshot.entries["provision.node.database-host"].status == "applied"
    assert applied.snapshot.realization_envelope == _realization_identity()

    orchestrator = PrimaiteOrchestrator()
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
    started = orchestrator.start(orchestration, applied.snapshot)
    assert started.success
    assert (
        started.snapshot.orchestration_results["orchestration.workflow.episode"]["workflow_status"]
        == "running"
    )
    assert driver.step_calls == []


def test_unsupported_provisioning_is_rejected_before_construction() -> None:
    driver = FakeDriver()
    plan = _provision_plan(
        [
            ProvisionOp(
                action=ChangeAction.CREATE,
                address="provision.persistent-volume.unsupported",
                resource_type="persistent-volume",
                payload={},
            )
        ]
    )

    result = PrimaiteProvisioner(driver, _realization_identity()).apply(plan, RuntimeSnapshot())

    assert not result.success
    assert driver.construct_calls == 0
    assert result.diagnostics[0].code == "primaite.provisioning.unsupported-resource"


def test_provisioner_rejects_plan_that_does_not_join_the_selected_realization() -> None:
    driver = FakeDriver()
    provisioner = PrimaiteProvisioner(driver, _realization_identity())
    node = ProvisionOp(
        action=ChangeAction.CREATE,
        address="provision.node.database-host",
        resource_type="node",
        payload={"node_type": "vm"},
    )

    # A plan with no realization envelope is refused before any construction.
    missing = provisioner.apply(ProvisioningPlan(operations=[node]), RuntimeSnapshot())
    assert not missing.success
    assert driver.construct_calls == 0
    assert missing.diagnostics[0].code == "primaite.provisioning.realization-envelope-missing"


def test_admitted_blue_action_is_rejected_as_unrepresentable_with_join() -> None:
    driver = FakeDriver()  # default step: unrepresentable
    runtime, snapshot = _initialized_runtime(driver, episode_id="episode-unrep")

    result = runtime.admit_action(_action_request(), snapshot)

    assert not result.success
    assert result.action_result is not None
    assert result.action_result.status == "rejected"
    assert result.action_result.failure_class == "unsupported_action"
    # The admitted action still joins to exactly one driver operation and identity.
    assert driver.step_calls == [SERVICE_CONTROL]
    assert runtime.driver_operation_ref("action-1") == "driver.step.1"
    assert result.action_result.participant_address == PARTICIPANT
    assert result.action_result.episode_id == "episode-unrep"
    assert result.diagnostics[0].code == "primaite.participant.unrepresentable-action"
    # No native operation was chosen and no native data leaks.
    assert runtime.observations(PARTICIPANT) == ()
    portable = str(
        {
            "result": result.action_result.model_dump(mode="json"),
            "diagnostics": [d.message for d in result.diagnostics],
        }
    )
    for forbidden in _LEAKAGE_MARKERS:
        assert forbidden not in portable


def test_unknown_action_contract_is_rejected_before_native_step() -> None:
    driver = FakeDriver()
    runtime, snapshot = _initialized_runtime(driver, episode_id="episode-unknown")

    result = runtime.admit_action(
        _action_request(
            "participant.action-contract.exfiltrate",
            action_instance_id="action-unknown",
        ),
        snapshot,
    )

    assert not result.success
    assert driver.step_calls == []
    assert result.action_result.failure_class == "unsupported_action"
    assert result.diagnostics[0].code == "primaite.participant.unsupported-action"


def test_representable_transition_models_observation_without_leaking() -> None:
    driver = FakeDriver(step_result=_representable_step())
    runtime, snapshot = _initialized_runtime(driver, seed=20260802, episode_id="episode-rep")

    result = runtime.admit_action(_action_request(), snapshot)

    assert result.success
    assert isinstance(result.action_result, ParticipantActionResultModel)
    assert result.action_result.status == "succeeded"
    assert result.action_result.evidence_refs == [ACTION_EVIDENCE_REF]
    assert runtime.driver_operation_ref("action-1") == "driver.step.1"
    observations = runtime.observations(PARTICIPANT)
    assert len(observations) == 1
    assert observations[0].participant_address == PARTICIPANT
    assert observations[0].hidden_state_refs == []
    portable = str(
        {
            "result": result.action_result.model_dump(mode="json"),
            "observation": observations[0].model_dump(mode="json"),
        }
    )
    for forbidden in _LEAKAGE_MARKERS:
        assert forbidden not in portable


def test_undisclosed_evidence_and_native_failures_are_withheld() -> None:
    driver = FakeDriver(step_result=_representable_step())
    runtime, snapshot = _initialized_runtime(driver, episode_id="episode-boundary")

    undisclosed = runtime.admit_action(_action_request(disclose_action_evidence=False), snapshot)
    assert undisclosed.success
    assert undisclosed.action_result.evidence_refs == []
    assert runtime.observations(PARTICIPANT)[0].evidence_refs == []

    failing_runtime, failing_snapshot = _initialized_runtime(
        FakeDriver(fail_step=True), episode_id="episode-failure"
    )
    failed = failing_runtime.admit_action(
        _action_request(action_instance_id="action-failure"), failing_snapshot
    )
    portable = str(
        {
            "diagnostics": [d.message for d in failed.diagnostics],
            "action_result": failed.action_result.model_dump(mode="json"),
        }
    )
    assert not failed.success
    assert failed.action_result.status == "failed"
    for forbidden in _LEAKAGE_MARKERS:
        assert forbidden not in portable


def test_source_truncation_terminates_the_episode() -> None:
    driver = FakeDriver(step_result=_representable_step(truncated=True))
    runtime, snapshot = _initialized_runtime(driver, episode_id="episode-truncation")

    result = runtime.admit_action(_action_request(), snapshot)

    assert result.success
    history = result.snapshot.participant_episode_history.get(PARTICIPANT, [])
    rendered = str(history).lower()
    assert "terminat" in rendered or "truncat" in rendered


def test_reset_reports_broken_absent_and_unbound_streams_distinctly() -> None:
    driver = FakeDriver()
    runtime, _snapshot = _initialized_runtime(driver, seed=20260802, episode_id="episode-reset")

    codes = {
        diagnostic.code
        for diagnostic in runtime._reset_diagnostics(
            PARTICIPANT,
            DriverResetReport(
                operation_ref="driver.reset.1",
                applied_streams=(),
                broken_streams=("gym-reset-seam", "python-random"),
                absent_streams=("torch",),
                unbound_streams=("numpy-global",),
            ),
        )
    }
    assert codes == {"primaite.seed.broken", "primaite.seed.absent", "primaite.seed.unbound"}
    assert "primaite.seed.applied" not in codes
    assert driver.reset_calls == [20260802]


def test_reset_failure_restores_baseline_without_leaking() -> None:
    driver = FakeDriver(fail_reset=True)
    runtime = PrimaiteParticipantRuntime(driver)
    result = runtime.initialize(
        ParticipantEpisodeInitializeRequest(
            participant_address=PARTICIPANT,
            episode_id="episode-reset-fail",
        ),
        RuntimeSnapshot(),
    )
    assert not result.success
    assert result.diagnostics[0].code == "primaite.participant.reset-failed"
    assert "secret-token" not in str([d.message for d in result.diagnostics])


def test_evaluator_projects_unknown_truth_and_bounded_evidence_without_leaking() -> None:
    driver = FakeDriver(
        evaluation=DriverEvaluation(
            execution_ref="driver.reset.1",
            step_count=3,
            cumulative_reward=-57.05,
            terminated=False,
            truncated=True,
            terminal_cause="fixed-horizon-truncation",
        )
    )
    evaluator = PrimaiteEvaluator(driver)
    plan = EvaluationPlan(
        operations=[
            EvaluationOp(
                action=ChangeAction.CREATE,
                address="evaluation.objective.preserve-data-services",
                resource_type="objective",
                payload={
                    "result_contract": {
                        "resource_type": "objective",
                        "supports_score": True,
                        "supports_passed": False,
                        "fixed_max_score": None,
                    }
                },
            ),
            EvaluationOp(
                action=ChangeAction.CREATE,
                address="evaluation.proposition.data-integrity-maintained",
                resource_type="proposition",
                payload={"evaluation_basis": "declared_state"},
            ),
            EvaluationOp(
                action=ChangeAction.CREATE,
                address="evaluation.assertion.integrity-invariant",
                resource_type="assertion",
                payload={
                    "proposition_address": "evaluation.proposition.data-integrity-maintained",
                    "polarity": "positive",
                },
            ),
        ]
    )

    started = evaluator.start(plan, RuntimeSnapshot())

    assert started.success
    assert driver.evaluate_calls == 1
    truth = started.snapshot.proposition_truth_results["evaluation.assertion.integrity-invariant"]
    assert truth["assertion_outcome"] == "unknown"
    assert truth["proposition_outcome"] == "unknown"
    records = evaluator.evidence_records()
    # No reward score/measure is projected: the reward is withheld pending closure.
    assert evaluator.derived_measures() == ()
    assert isinstance(records[0], ExperimentEvidenceRecordModel)
    record_json = records[0].model_dump(mode="json")
    assert "withheld" in str(record_json).lower()
    result_state = evaluator.results()["evaluation.objective.preserve-data-services"]
    assert result_state["score"] is None
    portable = str(
        {
            "results": evaluator.results(),
            "truth": truth,
            "record": record_json,
        }
    )
    for forbidden in _LEAKAGE_MARKERS:
        assert forbidden not in portable
    # The withdrawn reward value never reaches a portable artifact.
    assert "-57.05" not in portable


def test_cleanup_is_idempotent_verified_and_preserves_bounded_failure() -> None:
    driver = FakeDriver()
    driver.construct()
    receipt = execute_primaite_cleanup(
        _cleanup_plan(),
        create_primaite_manifest(),
        driver,
        receipt_id="cleanup-receipt-1",
        execution_attempt_id="cleanup-attempt-1",
        trial_outcome="succeeded",
    )
    assert receipt.cleanup_status == "succeeded"
    assert driver.close_calls == 1

    failing = FakeDriver(fail_close=True)
    failing.construct()
    failed = execute_primaite_cleanup(
        _cleanup_plan(required=False),
        create_primaite_manifest(),
        failing,
        receipt_id="cleanup-receipt-2",
        execution_attempt_id="cleanup-attempt-2",
        trial_outcome="failed",
    )
    assert failed.cleanup_status == "failed"
    assert "secret-token" not in str(failed.model_dump(mode="json"))


def test_bounded_conformance_probe_never_certifies_the_non_runnable_target() -> None:
    # The portable-contract probe leaves only the bounded envelope no-witness case.
    report = run_primaite_conformance(driver=FakeDriver())
    non_passing = [case for case in report.cases if not case.passed]
    assert len(non_passing) == 1
    assert non_passing[0].contract_name == "realization-envelope-v1"

    # No affirmative runtime capability is production-evidenced: the live driver
    # fails closed, so a fake-driver probe cannot certify it. Every affirmative
    # capability is disclosed as an open gap instead.
    evidence = primaite_manifest_capability_evidence()
    gaps = primaite_manifest_capability_evidence_gaps()
    assert evidence == {}
    assert "/capabilities/cleanup/supported_action_kinds" in gaps
    assert "/capabilities/participant_runtime/feature_support" in gaps
    assert "/capabilities/evaluator/supports_scoring" not in gaps  # no longer declared


def test_source_protocol_diagnostics_and_declared_weaknesses_hold() -> None:
    diagnostics = primaite_source_protocol_diagnostics()
    codes = {diagnostic.code for diagnostic in diagnostics}
    assert "primaite.source-protocol.validated" in codes
    assert "primaite.source-protocol.validation-failed" not in codes
    weaknesses = primaite_declared_weaknesses()
    assert any(item.startswith("limitation:broken-public-seed-seam") for item in weaknesses)
    assert any(item.startswith("loss:loss-abstracted-participant-interface") for item in weaknesses)


def _tree_digest(content_by_path: dict[str, bytes]) -> str:
    """Reproduce base.installed_tree_digest over a sorted portable tree."""

    digest = hashlib.sha256()
    for path in sorted(content_by_path):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(content_by_path[path]).hexdigest().encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


class _FakeDistribution:
    def __init__(self, version: str, root: Path) -> None:
        self.version = version
        self._root = root
        self.direct_url_text: str | None = None

    def locate_file(self, path: str) -> Path:
        return self._root / path

    def read_text(self, filename: str) -> str | None:
        return self.direct_url_text if filename == "direct_url.json" else None


def _install_live_driver_fixtures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> _FakeDistribution:
    """Install a valid fake selected distribution + qualification for the live driver.

    The live driver never imports PrimAITE and never mutates process-global state,
    so only the installed distribution and the qualification record are faked.
    """

    tree_content = {
        "primaite/__init__.py": b"selected primaite package",
        "primaite/session/environment.py": b"selected primaite environment",
        "primaite/game/game.py": b"selected primaite game",
        "primaite/config/_package_data/data_manipulation.yaml": b"metadata:\n  version: 3.0\n",
    }
    root = tmp_path / "selected-distribution"
    for path, content in tree_content.items():
        installed = root / path
        installed.parent.mkdir(parents=True, exist_ok=True)
        installed.write_bytes(content)

    distribution = _FakeDistribution("4.0.0", root)
    tree_digest = _tree_digest(tree_content)
    running = f"{sys.version_info.major}.{sys.version_info.minor}.0"
    qualification: dict[str, object] = {
        "source": {"package": "primaite", "version": "4.0.0", "commit": "9861798" + "0" * 33},
        "runtime": {"python": running},
        "source_files": [
            {"path": f"src/{path}", "sha256": hashlib.sha256(content).hexdigest()}
            for path, content in tree_content.items()
            if path
            in {
                "primaite/__init__.py",
                "primaite/session/environment.py",
                "primaite/game/game.py",
            }
        ],
        "runtime_source_tree": {
            "root": "primaite",
            "file_count": len(tree_content),
            "sha256": tree_digest,
        },
        "runtime_artifacts": [
            {
                "name": "primaite",
                "version": "4.0.0",
                "artifact": {
                    "filename": "primaite-4.0.0-py3-none-any.whl",
                    "sha256": "1" * 64,
                    "require_direct_archive_sha256": False,
                    "runtime_identity": "complete-root-tree",
                },
                "roots": [
                    {"path": "primaite", "file_count": len(tree_content), "sha256": tree_digest}
                ],
            }
        ],
    }
    monkeypatch.setattr(
        "raes_adapters.primaite.backend.driver.distribution",
        lambda name: distribution,
    )
    monkeypatch.setattr(
        "raes_adapters.primaite.backend.driver.load_qualification",
        lambda: qualification,
    )
    return distribution


def test_live_driver_verifies_source_identity_then_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_live_driver_fixtures(monkeypatch, tmp_path)
    driver = PrimaiteDriver()

    # construct (via reset) verifies the selected identity, then fails closed with a
    # bounded reason — it never imports PrimAITE or mutates process-global state.
    with pytest.raises(RuntimeError, match="does not run in-process") as reset_error:
        driver.reset(20260802)
    message = str(reset_error.value)
    assert "worker-process boundary" in message
    for forbidden in _LEAKAGE_MARKERS:
        assert forbidden not in message

    for operation in (
        lambda: driver.step(SERVICE_CONTROL),
        driver.evaluate,
    ):
        with pytest.raises(RuntimeError, match="does not run in-process"):
            operation()

    # Nothing was opened in-process, so cleanup is a bounded no-op and verify_closed holds.
    report = driver.close()
    assert report.closed and report.verified and report.already_closed
    assert report.workspace_removed is False
    assert driver.verify_closed()


def test_live_driver_refuses_unqualified_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_live_driver_fixtures(monkeypatch, tmp_path)
    unqualified = {
        "source": {"package": "primaite", "version": "4.0.0", "commit": "9861798" + "0" * 33},
        "runtime": {"python": "2.7.0"},
    }
    monkeypatch.setattr(
        "raes_adapters.primaite.backend.driver.load_qualification",
        lambda: unqualified,
    )
    with pytest.raises(RuntimeError, match="runtime is not the qualified runtime"):
        PrimaiteDriver().construct()


def test_live_driver_rejects_editable_install_and_source_drift(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    distribution = _install_live_driver_fixtures(monkeypatch, tmp_path)

    # An editable/directory install cannot be attested.
    distribution.direct_url_text = '{"dir_info":{"editable":true},"url":"file:///unqualified"}'
    with pytest.raises(RuntimeError, match="runtime artifact could not be verified"):
        PrimaiteDriver().construct()

    # A tampered critical source file fails source-identity verification.
    distribution.direct_url_text = None
    (tmp_path / "selected-distribution" / "primaite/session/environment.py").write_bytes(
        b"tampered"
    )
    with pytest.raises(RuntimeError, match="source identity could not be verified"):
        PrimaiteDriver().construct()


def test_diagnostic_address_passthrough_and_empty_fallback() -> None:
    from raes_adapters.primaite.backend._diagnostics import diagnostic_address

    assert diagnostic_address("/already/pointer") == "/already/pointer"
    assert diagnostic_address("") == "/primaite"
    assert diagnostic_address("primaite.node.database-host") == "/primaite/node/database-host"


def test_provisioner_bounds_native_construction_failure() -> None:
    driver = FakeDriver(fail_construct=True)
    plan = _provision_plan(
        [
            ProvisionOp(
                action=ChangeAction.CREATE,
                address="provision.node.database-host",
                resource_type="node",
                payload={"node_type": "vm"},
            )
        ]
    )

    result = PrimaiteProvisioner(driver, _realization_identity()).apply(plan, RuntimeSnapshot())

    assert not result.success
    assert result.diagnostics[-1].code == "primaite.provisioning.construct-failed"
    assert "secret-token" not in str([d.message for d in result.diagnostics])


def test_provisioner_unchanged_operations_are_a_noop() -> None:
    driver = FakeDriver()
    plan = _provision_plan(
        [
            ProvisionOp(
                action=ChangeAction.UNCHANGED,
                address="provision.node.web-host",
                resource_type="node",
                payload={},
            )
        ]
    )

    result = PrimaiteProvisioner(driver, _realization_identity()).apply(plan, RuntimeSnapshot())

    assert result.success
    assert driver.construct_calls == 0


def test_orchestrator_rejects_unsupported_resource_and_stops_cleanly() -> None:
    orchestrator = PrimaiteOrchestrator()
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
    assert unsupported.diagnostics[0].code == "primaite.orchestration.unsupported-resource"

    empty = orchestrator.start(OrchestrationPlan(operations=[]), RuntimeSnapshot())
    assert empty.success

    started = orchestrator.start(
        OrchestrationPlan(
            operations=[
                OrchestrationOp(
                    action=ChangeAction.CREATE,
                    address="orchestration.workflow.episode",
                    resource_type="workflow",
                    payload={"name": "episode"},
                )
            ],
            startup_order=["orchestration.workflow.episode"],
        ),
        RuntimeSnapshot(),
    )
    assert orchestrator.status()["running"] is True
    assert orchestrator.results()
    assert orchestrator.history()

    stopped = orchestrator.stop(started.snapshot)
    assert stopped.success
    assert "orchestration.workflow.episode" not in stopped.snapshot.entries
    assert orchestrator.status()["running"] is False


def test_evaluator_metadata_only_change_clears_evidence_and_stop_resets() -> None:
    driver = FakeDriver()
    evaluator = PrimaiteEvaluator(driver)

    # A proposition-only plan needs no source projection.
    metadata_only = evaluator.start(
        EvaluationPlan(
            operations=[
                EvaluationOp(
                    action=ChangeAction.CREATE,
                    address="evaluation.proposition.web-service-available",
                    resource_type="proposition",
                    payload={"evaluation_basis": "declared_state"},
                )
            ]
        ),
        RuntimeSnapshot(),
    )
    assert metadata_only.success
    assert driver.evaluate_calls == 0
    assert evaluator.evidence_records() == ()
    assert evaluator.capture_spec() is None
    assert evaluator.status()["capture_spec"] is False

    stopped = evaluator.stop(metadata_only.snapshot)
    assert stopped.success
    assert evaluator.status()["running"] is False
