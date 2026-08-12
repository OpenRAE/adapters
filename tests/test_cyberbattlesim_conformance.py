"""CyberBattleSim conformance composition and source-protocol probes."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

from raes_backend_protocols.manifest import backend_manifest_payload
from raes_conformance.conformance import BackendConformanceReport
from raes_conformance.conformance.report import backend_conformance_report_payload
from raes_contracts.contracts import (
    ApparatusIdentityModel,
    CleanupObligationModel,
    CleanupResourceBoundaryModel,
    ParticipantActionResultModel,
    ParticipantConfigurationResultModel,
    ParticipantExposurePolicyModel,
    ParticipantImplementationCapabilitiesModel,
    ParticipantImplementationCompatibilityModel,
    ParticipantImplementationManifestModel,
    ParticipantImplementationSelectionModel,
    TrialCleanupPlanModel,
)
from raes_contracts.contracts.trial_cleanup import (
    CleanStateRequirementModel,
    ExecutionRetryPolicyModel,
)
from raes_contracts.diagnostics import diagnostic_model, diagnostic_payload
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

from raes_adapters.cyberbattlesim.backend import (
    ACTION_EVIDENCE_REF,
    CYBERBATTLESIM_BACKEND_NAME,
    CyberBattleSimEvaluator,
    CyberBattleSimOrchestrator,
    CyberBattleSimParticipantRuntime,
    CyberBattleSimProvisioner,
    DriverCleanupReport,
    DriverEvaluation,
    DriverResetReport,
    DriverStep,
    create_cyberbattlesim_manifest,
    execute_cyberbattlesim_cleanup,
)
from raes_adapters.cyberbattlesim.backend.conformance import (
    cyberbattlesim_backend_conformance_payload,
    cyberbattlesim_declared_weaknesses,
    cyberbattlesim_manifest_capability_gaps,
    cyberbattlesim_source_protocol_diagnostics,
    run_cyberbattlesim_conformance,
)

PARTICIPANT = "participant.behavior.attacker"
OBSERVATION_BOUNDARY = "participant.observation-boundary.attacker-view"
LOCAL_ACTION = "participant.action-contract.local-vulnerability"
SENTINEL = "native-secret-sentinel"
REPO_ROOT = Path(__file__).resolve().parents[1]


def _selected_participant() -> tuple[
    ParticipantImplementationManifestModel,
    ParticipantImplementationSelectionModel,
    ParticipantConfigurationResultModel,
]:
    root = REPO_ROOT / "environments" / "cyberbattlesim-chain" / "participant"
    return (
        ParticipantImplementationManifestModel.model_validate_json(
            (root / "cyberbattlesim-red-credential-cache.manifest.json").read_text()
        ),
        ParticipantImplementationSelectionModel.model_validate_json(
            (root / "cyberbattlesim-red-credential-cache.selection.json").read_text()
        ),
        ParticipantConfigurationResultModel.model_validate_json(
            (root / "cyberbattlesim-red-credential-cache.configuration.json").read_text()
        ),
    )


def _run_selected_conformance() -> BackendConformanceReport:
    manifest, selection, configuration = _selected_participant()
    return run_cyberbattlesim_conformance(
        driver=ProbeDriver(),
        seed=20260729,
        participant_manifest=manifest,
        participant_selection=selection,
        participant_configuration=configuration,
    )


@dataclass
class ProbeDriver:
    """Deterministic injected driver with hostile native state sentinels."""

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
    fail_construct: bool = False
    fail_step: bool = False
    fail_evaluate: bool = False
    fail_close: bool = False
    construct_calls: int = 0
    reset_calls: list[int | None] = field(default_factory=list)
    step_calls: list[str] = field(default_factory=list)
    evaluate_calls: int = 0
    close_calls: int = 0
    closed: bool = False

    def construct(self) -> None:
        self.construct_calls += 1
        if self.fail_construct:
            raise RuntimeError(f"{SENTINEL}: construct")
        self.closed = False

    def reset(self, seed: int | None) -> DriverResetReport:
        self.reset_calls.append(seed)
        if self.fail_construct:
            raise RuntimeError(f"{SENTINEL}: reset")
        self.closed = False
        return DriverResetReport(
            operation_ref=f"driver.reset.{len(self.reset_calls)}",
            applied_streams=("gym-environment", "gym-action-space") if seed is not None else (),
            unbound_streams=("python-random", "numpy-global"),
        )

    def step(self, action_kind: str) -> DriverStep:
        self.step_calls.append(action_kind)
        if self.fail_step:
            raise RuntimeError(f"{SENTINEL}: step")
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
        if self.fail_evaluate:
            raise RuntimeError(f"{SENTINEL}: evaluate")
        return replace(
            self.evaluation,
            projection_ref=f"{self.evaluation.execution_ref}.evaluation.{self.evaluate_calls}",
        )

    def close(self) -> DriverCleanupReport:
        self.close_calls += 1
        if self.fail_close:
            raise RuntimeError(f"{SENTINEL}: close")
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


def _participant_manifest() -> ParticipantImplementationManifestModel:
    return ParticipantImplementationManifestModel(
        identity=ApparatusIdentityModel(
            name="cyberbattlesim-conformance-probe",
            version="1.0.0",
        ),
        implementation_kind="policy",
        supported_contract_versions=[
            "participant-implementation-manifest-v1",
            "participant-implementation-provenance-v1",
            "participant-episode-state-envelope-v1",
            "participant-behavior-history-event-stream-v1",
            "participant-decision-surface-v2",
        ],
        compatibility=ParticipantImplementationCompatibilityModel(
            participant_runtimes=["cyberbattlesim-participant-runtime"],
            backends=[CYBERBATTLESIM_BACKEND_NAME],
        ),
        concept_bindings=[
            {"scope": "implementation_kind", "family": "apparatus-declarations"},
            {
                "scope": "capabilities.supported_participant_contracts",
                "family": "apparatus-declarations",
            },
        ],
        capabilities=ParticipantImplementationCapabilitiesModel(
            supported_participant_contracts=[
                "participant-episode-state-envelope-v1",
                "participant-behavior-history-event-stream-v1",
                "participant-decision-surface-v2",
            ],
            supported_decision_surface_modes=["policy-directed"],
            tool_affordance_expectations=["credential-store"],
            exposure_policy_kinds=["hidden-truth", "observation-stream"],
        ),
    )


def _action_request() -> ParticipantActionAdmissionRequest:
    manifest = _participant_manifest()
    exposure_policy = ParticipantExposurePolicyModel(
        policy_id="cyberbattlesim-attacker-view",
        exposure_policy_kinds=["hidden-truth", "observation-stream"],
        disclosed_refs=[OBSERVATION_BOUNDARY],
        withheld_refs=["evidence.cyberbattlesim.hidden-world"],
        visibility_scope_refs=[PARTICIPANT],
    )
    selection = ParticipantImplementationSelectionModel(
        participant_address=PARTICIPANT,
        implementation_identity=manifest.identity,
        manifest_ref="manifest.cyberbattlesim.conformance-probe",
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
        action_contract_address=LOCAL_ACTION,
        observation_boundary_address=OBSERVATION_BOUNDARY,
        action_instance_id="action-conformance",
        implementation_manifest=manifest,
        implementation_selection=selection,
        visible_refs=(OBSERVATION_BOUNDARY,),
        disclosed_refs=(OBSERVATION_BOUNDARY,),
        observation_boundary_evidence_refs=(ACTION_EVIDENCE_REF,),
        validated_selection=ParticipantValidatedActionSelection(
            action_contract_address=LOCAL_ACTION,
            argument_shape_ref="argument-shape.cyberbattlesim.selected-action",
            proposal_ref="proposal.action-conformance",
            normalized_arguments=(),
            loss_disclosure_refs=("loss-abstracted-topology",),
        ),
        target_addresses=("provision.node.entry-client",),
        requires_terminal_outcome=True,
    )


def _cleanup_plan() -> TrialCleanupPlanModel:
    boundary = CleanupResourceBoundaryModel(
        boundary_id="cyberbattlesim-process",
        resource_kind="in-process-simulator",
        owner_ref=CYBERBATTLESIM_BACKEND_NAME,
        resource_refs=["runtime.cyberbattlesim.selected-environment"],
    )
    destroy = CleanupObligationModel(
        obligation_id="destroy-environment",
        boundary_refs=[boundary.boundary_id],
        action_kind="destroy",
        triggers=["success", "failure"],
        requirement="best-effort",
        idempotency="idempotent",
        verification_probe_refs=["probe:cyberbattlesim-closed"],
        timeout_seconds=5,
    )
    return TrialCleanupPlanModel(
        plan_id="cyberbattlesim-cleanup",
        plan_entry_id="cyberbattlesim-cleanup-entry",
        run_id="cyberbattlesim-run",
        clean_state=CleanStateRequirementModel(
            mode="verified-reset",
            boundary_refs=[boundary.boundary_id],
            verification_probe_refs=["probe:cyberbattlesim-closed"],
        ),
        resource_boundaries={boundary.boundary_id: boundary},
        cleanup_obligations={destroy.obligation_id: destroy},
        retry_policy=ExecutionRetryPolicyModel(
            max_attempts=1,
            after_effect_policy="disallow",
        ),
    )


def _json_text(payload: object) -> str:
    return json.dumps(payload, sort_keys=True)


def _normalized_text(text: str) -> str:
    return " ".join(text.split())


def test_canonical_conformance_report_and_payload_are_published_shapes() -> None:
    report = _run_selected_conformance()

    assert isinstance(report, BackendConformanceReport)
    assert report.passed
    assert cyberbattlesim_backend_conformance_payload(report) == (
        backend_conformance_report_payload(report)
    )


def test_source_protocol_diagnostics_and_declared_weaknesses_are_raes_models() -> None:
    diagnostics = cyberbattlesim_source_protocol_diagnostics()
    models = [diagnostic_model(diagnostic) for diagnostic in diagnostics]
    weaknesses = cyberbattlesim_declared_weaknesses()

    assert {model.code for model in models} >= {
        "cyberbattlesim.source-protocol.validated",
        "cyberbattlesim.source-protocol.declared-weakness",
    }
    assert all(model.address.startswith("/") for model in models)
    assert "limitation:no-index-or-release-artifact" in weaknesses
    assert "loss:loss-unbound-random-streams:deterministic-replay" in weaknesses


def test_manifest_capability_inventory_is_derived_and_fails_closed() -> None:
    manifest = create_cyberbattlesim_manifest()
    gaps = cyberbattlesim_manifest_capability_gaps(manifest)

    assert {
        "/capabilities/cleanup/supported_action_kinds",
        "/capabilities/evaluator/supported_sections",
        "/capabilities/orchestrator/supports_workflows",
        "/capabilities/participant_runtime/supported_behavior_features",
        "/capabilities/provisioner/supported_node_types",
    } <= set(gaps)

    payload = backend_manifest_payload(manifest)
    payload["capabilities"]["provisioner"]["supports_new_mode"] = True

    payload_gaps = cyberbattlesim_manifest_capability_gaps(payload=payload)
    assert "/capabilities/provisioner/supports_new_mode" in payload_gaps


def test_manual_native_readiness_protocol_covers_adapter_conformance_path() -> None:
    qualification_guardrails = (
        REPO_ROOT / "docs/decisions/cyberbattlesim-qualification-guardrails.md"
    ).read_text(encoding="utf-8")
    conformance_guardrails = (
        REPO_ROOT / "docs/decisions/cyberbattlesim-conformance-guardrails.md"
    ).read_text(encoding="utf-8")
    qualification_guardrails_text = _normalized_text(qualification_guardrails)
    conformance_guardrails_text = _normalized_text(conformance_guardrails)

    assert "manual native-readiness plan" in qualification_guardrails_text
    assert "real `CyberBattleSimDriver`" in qualification_guardrails_text
    assert "not an upstream CyberBattleSim test" in qualification_guardrails_text
    assert "deterministic injected-driver CI probe" in qualification_guardrails_text

    assert "adapter conformance composition is checked against the real simulator" in (
        conformance_guardrails_text
    )
    assert "`CyberBattleSimDriver`" in conformance_guardrails_text
    assert "`run_cyberbattlesim_conformance()`" in conformance_guardrails_text
    assert "`backend_conformance_report_payload()`" in conformance_guardrails_text
    assert "`cyberbattlesim_source_protocol_diagnostics()`" in conformance_guardrails_text
    assert "must not contain native action coordinates" in conformance_guardrails_text
    assert "deterministic driver" in conformance_guardrails_text


def test_failure_surface_diagnostics_validate_and_do_not_leak_native_sentinels() -> None:
    provisioning = CyberBattleSimProvisioner(ProbeDriver(fail_construct=True)).apply(
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
    orchestration = CyberBattleSimOrchestrator().start(
        OrchestrationPlan(
            operations=[
                OrchestrationOp(
                    action=ChangeAction.CREATE,
                    address="orchestration.script.unsupported",
                    resource_type="script",
                    payload={"private": SENTINEL},
                )
            ]
        ),
        RuntimeSnapshot(),
    )
    participant_runtime = CyberBattleSimParticipantRuntime(ProbeDriver(fail_step=True))
    initialized = participant_runtime.initialize(
        ParticipantEpisodeInitializeRequest(
            participant_address=PARTICIPANT,
            episode_id="episode-conformance",
        ),
        RuntimeSnapshot(),
    )
    participant = participant_runtime.admit_action(_action_request(), initialized.snapshot)
    evaluation = CyberBattleSimEvaluator(ProbeDriver(fail_evaluate=True)).start(
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
                        }
                    },
                )
            ]
        ),
        RuntimeSnapshot(),
    )
    cleanup = execute_cyberbattlesim_cleanup(
        _cleanup_plan(),
        create_cyberbattlesim_manifest(),
        ProbeDriver(fail_close=True),
        receipt_id="cleanup-conformance-failure",
        execution_attempt_id="cleanup-conformance-attempt",
        trial_outcome="failed",
    )

    diagnostics = [
        *provisioning.diagnostics,
        *orchestration.diagnostics,
        *initialized.diagnostics,
        *participant.diagnostics,
        *evaluation.diagnostics,
    ]
    diagnostic_payloads = [diagnostic_payload(diagnostic) for diagnostic in diagnostics]
    for diagnostic in diagnostics:
        diagnostic_model(diagnostic)

    assert not provisioning.success
    assert not orchestration.success
    assert initialized.success
    assert not participant.success
    assert participant.action_result is not None
    assert participant.action_result.status == "failed"
    assert not evaluation.success
    assert cleanup.cleanup_status == "failed"
    assert cleanup.obligation_results["destroy-environment"].status == "failed"

    payloads = {
        "diagnostics": diagnostic_payloads,
        "participant_action": (
            participant.action_result.model_dump(mode="json")
            if isinstance(participant.action_result, ParticipantActionResultModel)
            else None
        ),
        "cleanup": cleanup.model_dump(mode="json"),
    }
    assert SENTINEL not in _json_text(payloads)
