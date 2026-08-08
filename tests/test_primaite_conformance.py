"""PrimAITE conformance composition and source-protocol probes.

Composes the published RAES backend conformance report with PrimAITE-local
source-protocol and adapter-runtime evidence. The deterministic PR lane uses a
fully constructed ``RuntimeTarget`` driven by an explicit injected driver; it
never imports the simulator. The live ``PrimaiteDriver`` verifies source identity
and then fails closed (CPython-3.11-qualified runtime, platform-dir writes on
import), so an injected driver proves portable mechanics but never certifies a
live-native capability: capability evidence stays empty and every affirmative
capability is a disclosed gap. The manual-live lane (documented, not run here) is
enforced by ``test_manual_native_readiness_protocol_covers_adapter_conformance_path``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

from raes_backend_protocols.manifest import backend_manifest_payload
from raes_conformance.conformance import BackendConformanceReport
from raes_conformance.conformance.report import backend_conformance_report_payload
from raes_contracts.contracts import (
    ApparatusIdentityModel,
    CleanStateRequirementModel,
    CleanupObligationModel,
    CleanupResourceBoundaryModel,
    ExecutionRetryPolicyModel,
    ParticipantActionResultModel,
    ParticipantExposurePolicyModel,
    ParticipantImplementationCapabilitiesModel,
    ParticipantImplementationCompatibilityModel,
    ParticipantImplementationManifestModel,
    ParticipantImplementationSelectionModel,
    TrialCleanupPlanModel,
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

from raes_adapters.primaite.backend import (
    ACTION_EVIDENCE_REF,
    PR_CONFORMANCE_SEED,
    PRIMAITE_BACKEND_NAME,
    DriverCleanupReport,
    DriverEvaluation,
    DriverResetReport,
    DriverStep,
    PrimaiteEvaluator,
    PrimaiteOrchestrator,
    PrimaiteParticipantRuntime,
    PrimaiteProvisioner,
    create_primaite_manifest,
    execute_primaite_cleanup,
)
from raes_adapters.primaite.backend.conformance import (
    primaite_backend_conformance_payload,
    primaite_declared_weaknesses,
    primaite_manifest_capability_evidence,
    primaite_manifest_capability_evidence_gaps,
    primaite_source_protocol_diagnostics,
    run_primaite_conformance,
    run_primaite_pr_conformance,
)

PARTICIPANT = "participant.behavior.blue-defender"
OBSERVATION_BOUNDARY = "participant.observation-boundary.defender-view"
SERVICE_CONTROL = "participant.action-contract.service-control"
SENTINEL = "native-secret-sentinel"
REPO_ROOT = Path(__file__).resolve().parents[1]

# PrimAITE leaks would surface as the flattened observation, action mask, native
# ``info``, reward components, or a native object ``repr``. Prove none reach a
# portable projection alongside the injected sentinels.
NATIVE_MARKERS = (
    SENTINEL,
    "native_observation_vector",
    "action_mask",
    "reward_components",
    "Box(1652)",
    "Discrete(78)",
    "secret-token",
)


@dataclass
class ProbeDriver:
    """Deterministic injected driver with hostile private native-state sentinels.

    By default ``step`` reports an unrepresentable action, the honest live
    behavior for the current evidence, so the canonical probe never certifies the
    non-runnable target. A representable transition is exercised by passing an
    explicit ``step_result``.
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
    fail_construct: bool = False
    fail_reset: bool = False
    fail_step: bool = False
    fail_evaluate: bool = False
    fail_close: bool = False
    construct_calls: int = 0
    reset_calls: list[int | None] = field(default_factory=list)
    step_calls: list[str] = field(default_factory=list)
    evaluate_calls: int = 0
    close_calls: int = 0
    closed: bool = False
    # Deliberately private native state whose ``str``/``repr`` are unsafe to
    # emit; it must never cross into a portable projection.
    native_state: object = field(
        default_factory=lambda: {
            "native_observation_vector": SENTINEL,
            "action_mask": SENTINEL,
            "info": SENTINEL,
            "reward_components": [0.40, 0.25, 0.05],
        }
    )

    def construct(self) -> None:
        self.construct_calls += 1
        if self.fail_construct:
            raise RuntimeError(f"private native construct failure with {SENTINEL} secret-token")
        self.closed = False

    def reset(self, seed: int | None) -> DriverResetReport:
        self.reset_calls.append(seed)
        if self.fail_reset:
            raise RuntimeError(f"private native reset failure with {SENTINEL} secret-token")
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
            raise RuntimeError(f"private native step failure with {SENTINEL} secret-token")
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
        if self.fail_evaluate:
            raise RuntimeError(f"private native evaluate failure with {SENTINEL} secret-token")
        return replace(
            self.evaluation,
            projection_ref=f"{self.evaluation.execution_ref}.evaluation.{self.evaluate_calls}",
        )

    def close(self) -> DriverCleanupReport:
        self.close_calls += 1
        if self.fail_close:
            raise RuntimeError(f"private native close failure with {SENTINEL} secret-token")
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
    manifest = create_primaite_manifest()
    assert manifest.realization_envelope is not None
    return manifest.realization_envelope.identity


def _provision_plan() -> ProvisioningPlan:
    return ProvisioningPlan(
        operations=[
            ProvisionOp(
                action=ChangeAction.CREATE,
                address="provision.node.database-host",
                resource_type="node",
                payload={"node_type": "vm", "os_family": "linux"},
            )
        ],
        realization_envelope=_realization_identity(),
    )


def _participant_manifest() -> ParticipantImplementationManifestModel:
    return ParticipantImplementationManifestModel(
        identity=ApparatusIdentityModel(name="primaite-blue-defender-policy", version="1.0.0"),
        implementation_kind="policy",
        supported_contract_versions=[
            "participant-implementation-manifest-v1",
            "participant-implementation-provenance-v1",
            "participant-episode-state-envelope-v1",
            "participant-episode-history-event-stream-v1",
            "participant-behavior-history-event-stream-v1",
            "participant-decision-surface-v2",
        ],
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


def _action_request() -> ParticipantActionAdmissionRequest:
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
        action_contract_address=SERVICE_CONTROL,
        observation_boundary_address=OBSERVATION_BOUNDARY,
        action_instance_id="action-conformance",
        implementation_manifest=manifest,
        implementation_selection=selection,
        visible_refs=(OBSERVATION_BOUNDARY,),
        disclosed_refs=(OBSERVATION_BOUNDARY,),
        observation_boundary_evidence_refs=(ACTION_EVIDENCE_REF,),
        validated_selection=ParticipantValidatedActionSelection(
            action_contract_address=SERVICE_CONTROL,
            argument_shape_ref="argument-shape.primaite.selected-action",
            proposal_ref="proposal.action-conformance",
            normalized_arguments=(),
            loss_disclosure_refs=("loss-abstracted-participant-interface",),
        ),
        target_addresses=("provision.node.database-host",),
        requires_terminal_outcome=True,
    )


def _cleanup_plan() -> TrialCleanupPlanModel:
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
        requirement="best-effort",
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


def _json_text(payload: object) -> str:
    return json.dumps(payload, sort_keys=True)


def _normalized_text(text: str) -> str:
    return " ".join(text.split())


def test_canonical_conformance_report_and_payload_are_published_shapes() -> None:
    report = run_primaite_conformance(driver=ProbeDriver(), seed=PR_CONFORMANCE_SEED)

    assert isinstance(report, BackendConformanceReport)
    # An injected driver is hermetic adapter evidence, never native conformance.
    assert report.native_conformance is False
    # The non-runnable target is never certified: exactly one published no-witness
    # unsupported case remains; adapter code does not relabel or append cases.
    non_passing = [case for case in report.cases if not case.passed]
    assert len(non_passing) == 1
    assert non_passing[0].contract_name == "realization-envelope-v1"
    # The adapter serializes only through the published projector.
    assert primaite_backend_conformance_payload(report) == backend_conformance_report_payload(
        report
    )


def test_source_protocol_diagnostics_and_declared_weaknesses_are_raes_models() -> None:
    diagnostics = primaite_source_protocol_diagnostics()
    models = [diagnostic_model(diagnostic) for diagnostic in diagnostics]
    weaknesses = primaite_declared_weaknesses()

    assert {model.code for model in models} >= {
        "primaite.source-protocol.validated",
        "primaite.source-protocol.declared-weakness",
    }
    assert "primaite.source-protocol.validation-failed" not in {model.code for model in models}
    assert all(model.address.startswith("/") for model in models)
    # Real admitted limitations and loss disclosures, not adapter inventions.
    assert any(item.startswith("limitation:broken-public-seed-seam") for item in weaknesses)
    assert any(item.startswith("loss:loss-abstracted-participant-interface") for item in weaknesses)


def test_manifest_capability_evidence_fails_closed_for_the_non_runnable_target() -> None:
    manifest = create_primaite_manifest()

    # No affirmative runtime capability is production-evidenced: the live driver
    # fails closed, so an injected-driver probe cannot certify it. Evidence is
    # unconditionally empty and every affirmative capability is a disclosed gap.
    evidence = primaite_manifest_capability_evidence()
    gaps = primaite_manifest_capability_evidence_gaps(manifest)
    assert evidence == {}
    assert {
        "/capabilities/cleanup/supported_action_kinds",
        "/capabilities/participant_runtime/feature_support",
    } <= set(gaps)
    assert all(pointer.startswith("/capabilities/") for pointer in gaps)
    assert "/capabilities/evaluator/supports_scoring" not in gaps

    # A newly declared affirmative capability is also disclosed as a gap: the
    # closure fails closed rather than silently backing an unevidenced surface.
    payload = backend_manifest_payload(manifest)
    payload["capabilities"]["provisioner"]["supports_new_mode"] = True
    assert "/capabilities/provisioner/supports_new_mode" in (
        primaite_manifest_capability_evidence_gaps(payload=payload)
    )


def test_pr_conformance_bundle_composes_published_and_source_evidence() -> None:
    bundle = run_primaite_pr_conformance(driver=ProbeDriver())

    assert bundle["seed"] == PR_CONFORMANCE_SEED
    assert bundle["native_conformance"] is False
    backend_conformance = bundle["backend_conformance"]
    assert isinstance(backend_conformance, dict)
    assert backend_conformance["native_conformance"] is False
    assert backend_conformance["cases"]
    assert bundle["source_diagnostics"]
    # PrimAITE is fail-closed: no capability evidence closes and every affirmative
    # capability is disclosed as an explicit non-claim rather than raising.
    assert bundle["capability_evidence"] == {}
    assert bundle["capability_gaps"]
    assert any(str(item).startswith("limitation:") for item in bundle["declared_weaknesses"])
    # The composed bundle is the machine-readable evidence the clean-install proof
    # runs; it must be portable JSON and carry no native leakage.
    text = _json_text(bundle)
    assert not any(marker in text for marker in NATIVE_MARKERS)


def test_clock_control_is_unsupported_consistent_with_manifest() -> None:
    manifest = create_primaite_manifest()
    payload = backend_manifest_payload(manifest)

    # PrimAITE exposes no RAES time runtime or time capability. Serialized source
    # step order and fixed-horizon truncation are source-protocol facts, so clock
    # control resolves to an unsupported disposition consistent with the manifest
    # rather than an affirmative time claim.
    assert manifest.time is None
    assert "time" not in payload
    assert "clock" not in payload.get("capabilities", {})


def test_manual_native_readiness_protocol_covers_adapter_conformance_path() -> None:
    conformance_guardrails = _normalized_text(
        (REPO_ROOT / "docs/decisions/primaite-conformance-guardrails.md").read_text(
            encoding="utf-8"
        )
    )

    # The manual-live lane is documented with the exact adapter conformance path so
    # an operator runs the real composition, not a stand-in — and it stays blocked
    # because the live driver is non-runnable in-process.
    assert "adapter conformance composition is checked against the real simulator" in (
        conformance_guardrails
    )
    assert "real `PrimaiteDriver`" in conformance_guardrails
    assert "`run_primaite_conformance()`" in conformance_guardrails
    assert "`backend_conformance_report_payload()`" in conformance_guardrails
    assert "`primaite_source_protocol_diagnostics()`" in conformance_guardrails
    assert "deterministic injected-driver" in conformance_guardrails
    assert "native readiness remains blocked" in conformance_guardrails
    assert "must not contain native action coordinates" in conformance_guardrails


def test_failure_surface_diagnostics_validate_and_do_not_leak_native_sentinels() -> None:
    provisioning = PrimaiteProvisioner(
        ProbeDriver(fail_construct=True), _realization_identity()
    ).apply(_provision_plan(), RuntimeSnapshot())
    orchestration = PrimaiteOrchestrator().start(
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
    participant_runtime = PrimaiteParticipantRuntime(ProbeDriver(fail_step=True))
    initialized = participant_runtime.initialize(
        ParticipantEpisodeInitializeRequest(
            participant_address=PARTICIPANT,
            episode_id="episode-conformance",
        ),
        RuntimeSnapshot(),
    )
    participant = participant_runtime.admit_action(_action_request(), initialized.snapshot)
    evaluation = PrimaiteEvaluator(ProbeDriver(fail_evaluate=True)).start(
        EvaluationPlan(
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
                )
            ],
            startup_order=["evaluation.objective.preserve-data-services"],
        ),
        RuntimeSnapshot(),
    )
    cleanup = execute_primaite_cleanup(
        _cleanup_plan(),
        create_primaite_manifest(),
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

    # Every declared surface fails hostilely; initialize succeeds before the
    # failing step so the action surface still projects a typed failed result.
    assert not provisioning.success
    assert not orchestration.success
    assert initialized.success
    assert not participant.success
    assert participant.action_result is not None
    assert participant.action_result.status == "failed"
    assert not evaluation.success
    assert cleanup.cleanup_status == "failed"

    payloads = {
        "diagnostics": diagnostic_payloads,
        "participant_action": (
            participant.action_result.model_dump(mode="json")
            if isinstance(participant.action_result, ParticipantActionResultModel)
            else None
        ),
        "cleanup": cleanup.model_dump(mode="json"),
    }
    text = _json_text(payloads)
    assert not any(marker in text for marker in NATIVE_MARKERS)
