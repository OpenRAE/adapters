"""NASim conformance composition and source-protocol probes.

Composes the published RAES backend conformance report with NASim-local
source-protocol evidence. The deterministic PR lane uses a fully constructed
``RuntimeTarget`` driven by an explicit injected driver; it never imports the
simulator. The manual-live lane (documented, not run here) uses a real
``NasimDriver`` and is enforced by ``test_manual_native_readiness_protocol_*``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest
from raes_backend_protocols.manifest import backend_manifest_payload
from raes_conformance.conformance import BackendConformanceReport
from raes_conformance.conformance.report import backend_conformance_report_payload
from raes_contracts.contracts import ParticipantActionResultModel
from raes_contracts.diagnostics import diagnostic_model, diagnostic_payload
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

from raes_adapters.nasim.backend import (
    ACTION_EVIDENCE_REF,
    NASIM_BACKEND_NAME,
    PR_CONFORMANCE_SEED,
    NasimCleanupReport,
    NasimEvaluation,
    NasimEvaluator,
    NasimOrchestrator,
    NasimParticipantRuntime,
    NasimProvisioner,
    NasimResetReport,
    NasimStep,
    create_nasim_manifest,
    execute_nasim_cleanup,
)
from raes_adapters.nasim.backend.conformance import (
    nasim_backend_conformance_payload,
    nasim_declared_weaknesses,
    nasim_manifest_capability_evidence,
    nasim_manifest_capability_evidence_gaps,
    nasim_source_protocol_diagnostics,
    run_nasim_conformance,
    run_nasim_pr_conformance,
)
from tests._gym_fixtures import GymFixtureConfig, action_request, cleanup_plan

PARTICIPANT = "participant.behavior.attacker"
OBSERVATION_BOUNDARY = "participant.observation-boundary.attacker-view"
EXPLOIT_ACTION = "participant.action-contract.service-exploit"
SENTINEL = "native-secret-sentinel"
REPO_ROOT = Path(__file__).resolve().parents[1]

# NASim leaks would surface as source action-class symbols or the flat gym
# encodings, not a dict of named observation fields. Prove none reach a portable
# projection alongside the injected sentinel.
NATIVE_MARKERS = (
    SENTINEL,
    "flat_action_index",
    "flat_observation_vector",
    "native_host_state",
    "native_info",
    "flatactionspace",
    "servicescan",
)


@dataclass
class ProbeDriver:
    """Deterministic injected driver with hostile native state sentinels."""

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
    fail_construct: bool = False
    fail_step: bool = False
    fail_evaluate: bool = False
    fail_close: bool = False
    construct_calls: int = 0
    reset_calls: list[int | None] = field(default_factory=list)
    step_calls: list[tuple[str, str | None]] = field(default_factory=list)
    evaluate_calls: int = 0
    close_calls: int = 0
    closed: bool = False
    # Deliberately private native state whose ``str``/``repr`` are unsafe to
    # emit; it must never cross into a portable projection.
    native_state: object = field(
        default_factory=lambda: {
            "flat_action_index": SENTINEL,
            "flat_observation_vector": SENTINEL,
            "native_host_state": SENTINEL,
            "native_info": SENTINEL,
        }
    )

    def construct(self) -> None:
        self.construct_calls += 1
        if self.fail_construct:
            raise RuntimeError(f"{SENTINEL}: construct")
        self.closed = False

    def reset(self, seed: int | None) -> NasimResetReport:
        self.reset_calls.append(seed)
        if self.fail_construct:
            raise RuntimeError(f"{SENTINEL}: reset")
        self.closed = False
        return NasimResetReport(
            operation_ref=f"driver.reset.{len(self.reset_calls)}",
            applied_streams=("numpy-global-action-success", "gym-environment-reset")
            if seed is not None
            else (),
            unbound_streams=()
            if seed is not None
            else ("numpy-global-action-success", "gym-environment-reset"),
        )

    def step(self, action_kind: str, target_ref: str | None = None) -> NasimStep:
        self.step_calls.append((action_kind, target_ref))
        if self.fail_step:
            raise RuntimeError(f"{SENTINEL}: step")
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
        if self.fail_evaluate:
            raise RuntimeError(f"{SENTINEL}: evaluate")
        return replace(
            self.evaluation,
            projection_ref=f"{self.evaluation.execution_ref}.evaluation.{self.evaluate_calls}",
        )

    def close(self) -> NasimCleanupReport:
        self.close_calls += 1
        if self.fail_close:
            raise RuntimeError(f"{SENTINEL}: close")
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
    implementation_name="nasim-conformance-probe",
    participant_runtime_name="nasim-participant-runtime",
)


def _action_request():
    return action_request(
        _CONFIG,
        EXPLOIT_ACTION,
        action_instance_id="action-conformance",
        target_addresses=("provision.node.host-2-0",),
    )


def _json_text(payload: object) -> str:
    return json.dumps(payload, sort_keys=True)


def _normalized_text(text: str) -> str:
    return " ".join(text.split())


def test_canonical_conformance_report_and_payload_are_published_shapes() -> None:
    report = run_nasim_conformance(driver=ProbeDriver(), seed=PR_CONFORMANCE_SEED)

    assert isinstance(report, BackendConformanceReport)
    assert report.passed
    assert report.unsupported_contract_gaps == ()
    # An injected driver is hermetic adapter evidence, never native conformance.
    assert report.native_conformance is False
    # The adapter serializes only through the published projector; no bespoke
    # envelope is invented.
    assert nasim_backend_conformance_payload(report) == (backend_conformance_report_payload(report))


def test_source_protocol_diagnostics_and_declared_weaknesses_are_raes_models() -> None:
    diagnostics = nasim_source_protocol_diagnostics()
    models = [diagnostic_model(diagnostic) for diagnostic in diagnostics]
    weaknesses = nasim_declared_weaknesses()

    assert {model.code for model in models} >= {
        "nasim.source-protocol.validated",
        "nasim.source-protocol.declared-weakness",
    }
    assert "nasim.source-protocol.validation-failed" not in {model.code for model in models}
    assert all(model.address.startswith("/") for model in models)
    # Real admitted limitations and loss disclosures, not adapter inventions.
    assert "limitation:action-success-rng-unbound-by-env-seed" in weaknesses
    assert "loss:loss-unbound-action-rng:deterministic-replay" in weaknesses


def test_manifest_capability_evidence_is_derived_and_fails_closed() -> None:
    manifest = create_nasim_manifest()
    report = run_nasim_conformance(driver=ProbeDriver(), seed=PR_CONFORMANCE_SEED)
    diagnostics = nasim_source_protocol_diagnostics()
    inventory = nasim_manifest_capability_evidence(
        manifest,
        conformance_report=report,
        source_diagnostics=diagnostics,
    )

    assert {
        "/capabilities/cleanup/supported_action_kinds",
        "/capabilities/evaluator/supported_sections",
        "/capabilities/orchestrator/supports_workflows",
        "/capabilities/participant_runtime/supported_behavior_features",
        "/capabilities/provisioner/supported_node_types",
    } <= set(inventory)
    # Provisioner/participant surfaces require both backend and source evidence;
    # control-plane surfaces need only the canonical report.
    assert set(inventory["/capabilities/provisioner/supported_node_types"]) == {
        "evidence.nasim.backend-conformance",
        "evidence.nasim.source-protocol.validated",
    }
    assert inventory["/capabilities/cleanup/supported_action_kinds"] == (
        "evidence.nasim.backend-conformance",
    )
    assert (
        nasim_manifest_capability_evidence_gaps(
            manifest,
            conformance_report=report,
            source_diagnostics=diagnostics,
        )
        == ()
    )

    # A newly declared affirmative capability with no probe evidence must fail
    # closed as a gap rather than be silently backed.
    payload = backend_manifest_payload(manifest)
    payload["capabilities"]["provisioner"]["supports_new_mode"] = True
    payload_gaps = nasim_manifest_capability_evidence_gaps(
        payload=payload,
        conformance_report=report,
        source_diagnostics=diagnostics,
    )
    assert payload_gaps == ("/capabilities/provisioner/supports_new_mode",)

    # With no probe evidence at all, every affirmative surface is a gap.
    assert nasim_manifest_capability_evidence(payload=backend_manifest_payload(manifest)) == {}
    assert nasim_manifest_capability_evidence_gaps(payload=backend_manifest_payload(manifest))


def test_pr_conformance_suite_composes_published_and_source_evidence() -> None:
    bundle = run_nasim_pr_conformance(driver=ProbeDriver())

    assert bundle["seed"] == PR_CONFORMANCE_SEED
    assert bundle["native_conformance"] is False
    assert bundle["backend_conformance"]["passed"] is True
    assert bundle["source_diagnostics"]
    assert bundle["capability_evidence"]["/capabilities/provisioner/supported_node_types"] == [
        "evidence.nasim.backend-conformance",
        "evidence.nasim.source-protocol.validated",
    ]
    assert any(item.startswith("limitation:") for item in bundle["declared_weaknesses"])
    # The composed bundle is the machine-readable evidence run by the
    # clean-install proof; it must carry no native leakage.
    assert not any(marker in _json_text(bundle) for marker in NATIVE_MARKERS)


def test_pr_conformance_suite_fails_closed_on_capability_evidence_gaps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Drive the fail-closed branch: if any declared affirmative capability
    # lacks passing evidence, the bundle must refuse rather than ship an
    # unbacked surface (the guarantee run_nasim_pr_conformance's docstring
    # exists to enforce). The success-path test above never reaches this
    # branch because the real manifest has zero gaps.
    monkeypatch.setattr(
        "raes_adapters.nasim.backend.conformance.nasim_manifest_capability_evidence_gaps",
        lambda *args, **kwargs: ("/capabilities/provisioner/supported_node_types",),
    )

    driver = ProbeDriver()
    with pytest.raises(RuntimeError, match="incomplete"):
        run_nasim_pr_conformance(driver=driver)


def test_clock_control_is_unsupported_consistent_with_manifest() -> None:
    manifest = create_nasim_manifest()
    payload = backend_manifest_payload(manifest)

    # NASim exposes no RAES time runtime or time capability. The serialized
    # source step number is an observation, not a logical clock, so clock
    # control resolves to an unsupported disposition consistent with the
    # manifest rather than an affirmative time claim.
    assert manifest.time is None
    assert "time" not in payload
    assert "clock" not in payload.get("capabilities", {})


def test_manual_native_readiness_protocol_covers_adapter_conformance_path() -> None:
    conformance_guardrails = _normalized_text(
        (REPO_ROOT / "docs/decisions/nasim-conformance-guardrails.md").read_text(encoding="utf-8")
    )

    # The manual-live lane is documented with the exact adapter conformance
    # path so the operator runs the real composition, not a stand-in.
    assert "adapter conformance composition is checked against the real simulator" in (
        conformance_guardrails
    )
    assert "real `NasimDriver`" in conformance_guardrails
    assert "`run_nasim_conformance()`" in conformance_guardrails
    assert "`backend_conformance_report_payload()`" in conformance_guardrails
    assert "`nasim_source_protocol_diagnostics()`" in conformance_guardrails
    assert "deterministic injected-driver" in conformance_guardrails
    assert "injected driver under the same label" in conformance_guardrails
    assert "must not contain native action coordinates" in conformance_guardrails


def test_failure_surface_diagnostics_validate_and_do_not_leak_native_sentinels() -> None:
    provisioning = NasimProvisioner(ProbeDriver(fail_construct=True)).apply(
        ProvisioningPlan(
            operations=[
                ProvisionOp(
                    action=ChangeAction.CREATE,
                    address="provision.node.host-1-0",
                    resource_type="node",
                    payload={"node_type": "vm", "os_family": "linux"},
                )
            ]
        ),
        RuntimeSnapshot(),
    )
    orchestration = NasimOrchestrator().start(
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
    participant_runtime = NasimParticipantRuntime(ProbeDriver(fail_step=True))
    initialized = participant_runtime.initialize(
        ParticipantEpisodeInitializeRequest(
            participant_address=PARTICIPANT,
            episode_id="episode-conformance",
        ),
        RuntimeSnapshot(),
    )
    participant = participant_runtime.admit_action(_action_request(), initialized.snapshot)
    evaluation = NasimEvaluator(ProbeDriver(fail_evaluate=True)).start(
        EvaluationPlan(
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
        ),
        RuntimeSnapshot(),
    )
    cleanup = execute_nasim_cleanup(
        cleanup_plan(_CONFIG, required=False),
        create_nasim_manifest(),
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
    text = _json_text(payloads)
    assert not any(marker in text for marker in NATIVE_MARKERS)
