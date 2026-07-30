"""Behavioral tests for simulator-neutral shared adapter plumbing."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest
from raes_backend_protocols.backend_manifest import BackendManifest
from raes_backend_protocols.capabilities import (
    CLEANUP_CAPABILITY_REQUIRED_CONTRACTS,
    CleanupCapabilities,
)
from raes_conformance.conformance.report import BackendConformanceReport
from raes_conformance.realization import ExecutionBasis
from raes_contracts.contracts import (
    CleanStateRequirementModel,
    CleanupObligationModel,
    CleanupObligationResultModel,
    CleanupResourceBoundaryModel,
    ExecutionRetryPolicyModel,
    ExperimentStochasticControlModel,
    PublicSeedModel,
    RandomStreamControlBindingModel,
    RandomStreamProfileReferenceModel,
    TrialCleanupPlanModel,
)
from raes_contracts.contracts.time_model import (
    ClockDeclarationModel,
    ExactRatioModel,
    TimeDomainDeclarationModel,
    TimeModelDeclarationModel,
    TimeProgressionPolicyDeclarationModel,
)
from raes_contracts.diagnostics import DiagnosticModel, Severity
from raes_contracts.runtime_state import ApplyResult, RuntimeSnapshot
from raes_runtime.registry import RuntimeTarget, RuntimeTargetComponents
from raes_runtime.time_coordinator import ClockTransitionKind, ReferenceTimeRuntime

from raes_adapters.base import (
    apply_logical_clock_transition,
    apply_seed_controls,
    bounded_context_label,
    build_runtime_target,
    execute_cleanup,
    project_action,
    project_evaluation,
    project_observation,
    redact_native_value,
    run_conformance_probe,
)


@dataclass
class ToyQueueProvisioner:
    """Neutral, non-cyber provisioner used only as driver evidence."""

    applied: list[object] = field(default_factory=list)

    def validate(self, plan: object) -> list[object]:
        return []

    def apply(self, plan: object, snapshot: RuntimeSnapshot) -> ApplyResult:
        self.applied.append(plan)
        return ApplyResult(success=True, snapshot=snapshot)


@dataclass(frozen=True)
class ToyManifest:
    """Minimum structural manifest surface consumed by ``RuntimeTarget``."""

    cleanup: CleanupCapabilities | None = None
    time: object | None = None
    participant_runtime: object | None = None
    has_orchestrator: bool = False
    has_evaluator: bool = False
    has_participant_runtime: bool = False
    has_time: bool = False


def _manifest(*, cleanup: CleanupCapabilities | None = None) -> BackendManifest:
    return cast(BackendManifest, ToyManifest(cleanup=cleanup))


def _time_declaration() -> TimeModelDeclarationModel:
    domain_address = "time.domain.queue"
    clock_address = "time.clock.queue"
    policy_address = "time.progression.queue"
    return TimeModelDeclarationModel(
        domains={
            domain_address: TimeDomainDeclarationModel(
                address=domain_address,
                kind="logical",
                tick_period_seconds=ExactRatioModel(numerator=1, denominator=1),
                epoch="run_start",
                visibility="runtime_only",
                description="Queue event ordering.",
            )
        },
        clocks={
            clock_address: ClockDeclarationModel(
                address=clock_address,
                time_domain_address=domain_address,
                authority_kind="runtime",
                authority_ref="toy-queue-driver",
                monotonicity="may_jump",
                supports_pause=True,
                supports_reset=True,
                supports_jump=True,
                description="Explicit queue event clock.",
            )
        },
        progression_policies={
            policy_address: TimeProgressionPolicyDeclarationModel(
                address=policy_address,
                clock_address=clock_address,
                advancement_mode="event_driven",
                synchronization_mode="none",
                reset_behavior="new_segment_zero",
                replay_behavior="restart_from_anchor",
                description="Only caller-mapped queue events advance the clock.",
            )
        },
    )


def _seed_control(control_id: str, *, bound: bool = True) -> ExperimentStochasticControlModel:
    executable_binding = None
    if bound:
        executable_binding = RandomStreamControlBindingModel(
            profile_ref=RandomStreamProfileReferenceModel(
                ref_kind="profile",
                ref_id="blake3-xof-v1",
            ),
            namespace=f"queue-{control_id}",
            root_entropy=PublicSeedModel(
                kind="public-seed",
                encoding="hex-fixed-width",
                value="01" * 32,
            ),
        )
    return ExperimentStochasticControlModel(
        control_id=control_id,
        role="seed",
        description="Toy queue random source.",
        executable_binding=executable_binding,
    )


def _cleanup_plan() -> TrialCleanupPlanModel:
    boundary = CleanupResourceBoundaryModel(
        boundary_id="queue-range",
        resource_kind="queue",
        owner_ref="toy-driver",
        resource_refs=["queue:primary"],
    )
    prepare = CleanupObligationModel(
        obligation_id="prepare",
        boundary_refs=["queue-range"],
        action_kind="reset",
        triggers=["success", "failure"],
        requirement="required",
        idempotency="idempotent",
        verification_probe_refs=["probe:queue-empty"],
        timeout_seconds=5,
    )
    finish = CleanupObligationModel(
        obligation_id="finish",
        boundary_refs=["queue-range"],
        action_kind="verify",
        triggers=["success", "failure"],
        requirement="best-effort",
        depends_on=["prepare"],
        idempotency="idempotent",
        verification_probe_refs=["probe:queue-depth"],
        timeout_seconds=5,
    )
    record = CleanupObligationModel(
        obligation_id="record",
        boundary_refs=["queue-range"],
        action_kind="custom",
        action_profile_ref="toy-cleanup-record/v1",
        triggers=["success", "failure"],
        requirement="best-effort",
        idempotency="idempotent",
        timeout_seconds=5,
    )
    return TrialCleanupPlanModel(
        plan_id="queue-cleanup",
        plan_entry_id="queue-entry",
        run_id="queue-run",
        clean_state=CleanStateRequirementModel(
            mode="verified-reset",
            boundary_refs=["queue-range"],
            verification_probe_refs=["probe:queue-empty"],
        ),
        resource_boundaries={"queue-range": boundary},
        cleanup_obligations={
            "prepare": prepare,
            "finish": finish,
            "record": record,
        },
        retry_policy=ExecutionRetryPolicyModel(
            max_attempts=1,
            after_effect_policy="disallow",
        ),
    )


def _cleanup_capabilities() -> CleanupCapabilities:
    return CleanupCapabilities(
        name="toy-cleanup",
        supported_contract_versions=CLEANUP_CAPABILITY_REQUIRED_CONTRACTS,
        supported_action_kinds=frozenset({"reset", "verify", "custom"}),
        supported_verification_methods=frozenset({"probe"}),
        supports_residual_state_disclosure=True,
    )


def test_runtime_target_factory_delegates_shape_validation_to_raes() -> None:
    provisioner = ToyQueueProvisioner()
    components = RuntimeTargetComponents(provisioner=provisioner)

    target = build_runtime_target("toy-queue", _manifest(), components)

    assert isinstance(target, RuntimeTarget)
    assert target.name == "toy-queue"
    assert target.provisioner is provisioner

    invalid_manifest = cast(BackendManifest, ToyManifest(has_orchestrator=True))
    with pytest.raises(ValueError, match="orchestrator presence"):
        build_runtime_target("toy-queue", invalid_manifest, components)


def test_logical_clock_transitions_are_explicit_and_deterministic() -> None:
    declaration = _time_declaration()
    final_states = []
    for _ in range(2):
        runtime = ReferenceTimeRuntime()
        initialized = runtime.initialize(declaration, RuntimeSnapshot())
        advanced = apply_logical_clock_transition(
            runtime,
            initialized.snapshot,
            transition=ClockTransitionKind.ADVANCE,
            clock_address="time.clock.queue",
            ticks=3,
            microstep=2,
        )
        paused = apply_logical_clock_transition(
            runtime,
            advanced.snapshot,
            transition=ClockTransitionKind.PAUSE,
            clock_address="time.clock.queue",
        )
        final_states.append(runtime.state(paused.snapshot))

    assert final_states[0] == final_states[1]
    reading = final_states[0].clocks["time.clock.queue"]
    assert (reading.coordinate.tick, reading.coordinate.microstep) == (3, 2)
    assert [event.kind for event in reading.history] == ["initialize", "advance", "pause"]


def test_logical_clock_helper_refuses_implicit_transition_arguments() -> None:
    runtime = ReferenceTimeRuntime()
    initialized = runtime.initialize(_time_declaration(), RuntimeSnapshot())

    with pytest.raises(ValueError, match="requires explicit ticks"):
        apply_logical_clock_transition(
            runtime,
            initialized.snapshot,
            transition=ClockTransitionKind.ADVANCE,
            clock_address="time.clock.queue",
        )

    with pytest.raises(ValueError, match="Initialize logical clocks through ReferenceTimeRuntime"):
        apply_logical_clock_transition(
            runtime,
            initialized.snapshot,
            transition=ClockTransitionKind.INITIALIZE,
            clock_address="time.clock.queue",
        )


def test_logical_clock_helper_delegates_resume_jump_reset_and_replay() -> None:
    runtime = ReferenceTimeRuntime()
    result = runtime.initialize(_time_declaration(), RuntimeSnapshot())
    for transition, arguments in (
        (ClockTransitionKind.PAUSE, {}),
        (ClockTransitionKind.RESUME, {}),
        (ClockTransitionKind.JUMP, {"tick": 7, "microstep": 1}),
        (ClockTransitionKind.RESET, {}),
        (ClockTransitionKind.REPLAY, {}),
    ):
        result = apply_logical_clock_transition(
            runtime,
            result.snapshot,
            transition=transition,
            clock_address="time.clock.queue",
            **arguments,
        )

    reading = runtime.state(result.snapshot).clocks["time.clock.queue"]
    assert (reading.coordinate.segment, reading.coordinate.tick) == (3, 0)
    assert [event.kind for event in reading.history] == [
        "initialize",
        "pause",
        "resume",
        "jump",
        "reset",
        "replay",
    ]


def test_seed_controls_preserve_order_and_report_every_disposition() -> None:
    controls = [
        _seed_control("simulator"),
        _seed_control("policy"),
        _seed_control("unbound", bound=False),
        _seed_control("unsupported"),
    ]
    applied: list[str] = []

    def apply_simulator(binding: RandomStreamControlBindingModel) -> None:
        assert binding.namespace == "queue-simulator"
        applied.append("simulator")

    def fail_policy(binding: RandomStreamControlBindingModel) -> None:
        applied.append("policy")
        raise RuntimeError("token=must-not-escape")

    diagnostics = apply_seed_controls(
        controls,
        {
            "simulator": apply_simulator,
            "policy": fail_policy,
        },
    )

    assert applied == ["simulator", "policy"]
    assert [diagnostic.code for diagnostic in diagnostics] == [
        "adapter.seed.applied",
        "adapter.seed.failed",
        "adapter.seed.unbound",
        "adapter.seed.unsupported",
    ]
    assert [diagnostic.severity for diagnostic in diagnostics] == [
        Severity.INFO,
        Severity.ERROR,
        Severity.WARNING,
        Severity.WARNING,
    ]
    assert all("must-not-escape" not in diagnostic.message for diagnostic in diagnostics)


def test_seed_controls_refuse_duplicate_portable_control_ids() -> None:
    control = _seed_control("simulator")
    with pytest.raises(ValueError, match="control ids must be unique"):
        apply_seed_controls([control, control], {})


def test_cleanup_uses_capability_admission_dependency_order_and_raes_receipt() -> None:
    plan = _cleanup_plan()
    calls: list[str] = []

    def succeed(obligation: CleanupObligationModel) -> CleanupObligationResultModel:
        calls.append(obligation.obligation_id)
        return CleanupObligationResultModel(
            obligation_id=obligation.obligation_id,
            status="succeeded",
            evidence_refs=[f"evidence:{obligation.obligation_id}"],
        )

    class HostileCleanupError(RuntimeError):
        def __str__(self) -> str:
            raise AssertionError("native exception text was rendered")

        def __repr__(self) -> str:
            raise AssertionError("native exception repr was rendered")

    def fail(obligation: CleanupObligationModel) -> CleanupObligationResultModel:
        calls.append(obligation.obligation_id)
        raise HostileCleanupError()

    def failure_result(obligation: CleanupObligationModel) -> CleanupObligationResultModel:
        return CleanupObligationResultModel(
            obligation_id=obligation.obligation_id,
            status="failed",
            evidence_refs=["evidence:cleanup-failure"],
        )

    receipt = execute_cleanup(
        plan,
        _manifest(cleanup=_cleanup_capabilities()),
        {
            "prepare": succeed,
            "finish": fail,
            "record": succeed,
        },
        failure_result=failure_result,
        receipt_id="queue-cleanup-receipt",
        execution_attempt_id="queue-attempt-1",
        trial_outcome="succeeded",
    )

    assert calls == ["prepare", "finish", "record"]
    assert receipt.cleanup_status == "partial"
    assert receipt.obligation_results["prepare"].status == "succeeded"
    assert receipt.obligation_results["finish"].status == "failed"
    assert receipt.obligation_results["record"].status == "succeeded"


def test_cleanup_reports_unsupported_bindings_and_capability_gaps() -> None:
    plan = _cleanup_plan()
    manifest = _manifest()

    def unsupported_result(
        obligation: CleanupObligationModel,
    ) -> CleanupObligationResultModel:
        return CleanupObligationResultModel(
            obligation_id=obligation.obligation_id,
            status="unsupported",
        )

    with pytest.raises(ValueError, match="backend does not declare cleanup capabilities"):
        execute_cleanup(
            plan,
            manifest,
            {},
            failure_result=unsupported_result,
            receipt_id="queue-cleanup-receipt",
            execution_attempt_id="queue-attempt-1",
            trial_outcome="succeeded",
        )

    receipt = execute_cleanup(
        plan,
        _manifest(cleanup=_cleanup_capabilities()),
        {},
        failure_result=lambda obligation: CleanupObligationResultModel(
            obligation_id=obligation.obligation_id,
            status="unsupported",
        ),
        receipt_id="queue-cleanup-receipt",
        execution_attempt_id="queue-attempt-1",
        trial_outcome="cancelled",
    )
    assert receipt.cleanup_status == "not-required"
    assert receipt.obligation_results == {}


def test_cleanup_failure_reporting_does_not_retain_native_exception_context() -> None:
    class HostileCleanupError(RuntimeError):
        def __str__(self) -> str:
            raise AssertionError("native cleanup exception was rendered")

        def __repr__(self) -> str:
            raise AssertionError("native cleanup exception was represented")

    def fail_operation(obligation: CleanupObligationModel) -> CleanupObligationResultModel:
        raise HostileCleanupError()

    def fail_reporting(obligation: CleanupObligationModel) -> CleanupObligationResultModel:
        raise HostileCleanupError()

    plan = _cleanup_plan()
    manifest = _manifest(cleanup=_cleanup_capabilities())
    operations = {"prepare": fail_operation}
    with pytest.raises(ValueError, match=r"^Cleanup failure reporting failed\.$") as captured:
        execute_cleanup(
            plan,
            manifest,
            operations,
            failure_result=fail_reporting,
            receipt_id="queue-cleanup-receipt",
            execution_attempt_id="queue-attempt-1",
            trial_outcome="succeeded",
        )
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None


def test_cleanup_malformed_result_does_not_abandon_independent_obligations() -> None:
    calls: list[str] = []

    def succeed(obligation: CleanupObligationModel) -> CleanupObligationResultModel:
        calls.append(obligation.obligation_id)
        return CleanupObligationResultModel(
            obligation_id=obligation.obligation_id,
            status="succeeded",
            evidence_refs=[f"evidence:{obligation.obligation_id}"],
        )

    def malformed(obligation: CleanupObligationModel) -> CleanupObligationResultModel:
        calls.append(obligation.obligation_id)
        return cast(CleanupObligationResultModel, object())

    receipt = execute_cleanup(
        _cleanup_plan(),
        _manifest(cleanup=_cleanup_capabilities()),
        {
            "prepare": succeed,
            "finish": malformed,
            "record": succeed,
        },
        failure_result=lambda obligation: CleanupObligationResultModel(
            obligation_id=obligation.obligation_id,
            status="failed",
            evidence_refs=["evidence:malformed-cleanup-result"],
        ),
        receipt_id="queue-cleanup-receipt",
        execution_attempt_id="queue-attempt-1",
        trial_outcome="succeeded",
    )

    assert calls == ["prepare", "finish", "record"]
    assert receipt.obligation_results["finish"].status == "failed"
    assert receipt.obligation_results["record"].status == "succeeded"


def test_cleanup_failed_dependency_skips_dependent_but_runs_independent_obligation() -> None:
    original = _cleanup_plan()
    best_effort_prepare = original.cleanup_obligations["prepare"].model_copy(
        update={"requirement": "best-effort"}
    )
    plan = TrialCleanupPlanModel(
        plan_id=original.plan_id,
        plan_entry_id=original.plan_entry_id,
        run_id=original.run_id,
        clean_state=original.clean_state,
        resource_boundaries=original.resource_boundaries,
        cleanup_obligations={
            "prepare": best_effort_prepare,
            "finish": original.cleanup_obligations["finish"],
            "record": original.cleanup_obligations["record"],
        },
        retry_policy=original.retry_policy,
    )
    calls: list[str] = []

    def fail_prepare(obligation: CleanupObligationModel) -> CleanupObligationResultModel:
        calls.append(obligation.obligation_id)
        return CleanupObligationResultModel(
            obligation_id=obligation.obligation_id,
            status="failed",
            evidence_refs=["evidence:prepare-failure"],
        )

    def succeed(obligation: CleanupObligationModel) -> CleanupObligationResultModel:
        calls.append(obligation.obligation_id)
        return CleanupObligationResultModel(
            obligation_id=obligation.obligation_id,
            status="succeeded",
            evidence_refs=[f"evidence:{obligation.obligation_id}"],
        )

    receipt = execute_cleanup(
        plan,
        _manifest(cleanup=_cleanup_capabilities()),
        {
            "prepare": fail_prepare,
            "finish": succeed,
            "record": succeed,
        },
        failure_result=lambda obligation: CleanupObligationResultModel(
            obligation_id=obligation.obligation_id,
            status="failed",
            evidence_refs=["evidence:cleanup-failure"],
        ),
        receipt_id="queue-cleanup-receipt",
        execution_attempt_id="queue-attempt-1",
        trial_outcome="succeeded",
    )

    assert calls == ["prepare", "record"]
    assert receipt.obligation_results["prepare"].status == "failed"
    assert receipt.obligation_results["finish"].status == "skipped"
    assert receipt.obligation_results["record"].status == "succeeded"


def test_non_cyber_toy_driver_uses_direction_specific_projection_seams() -> None:
    native_queue: list[str] = []
    portable_action = DiagnosticModel(
        code="queue.enqueue",
        domain="queue",
        address="/items/0",
        message="Enqueue one item.",
        severity=Severity.INFO,
    )

    def action_projector(action: DiagnosticModel) -> str:
        return action.code

    native_action = project_action(portable_action, action_projector)
    native_queue.append(native_action)

    observation = project_observation(
        native_queue,
        lambda queue: {
            "code": "queue.depth",
            "domain": "queue",
            "address": "",
            "message": f"Queue depth is {len(queue)}.",
            "severity": "info",
        },
        DiagnosticModel.model_validate,
    )
    evaluation = project_evaluation(
        len(native_queue),
        lambda depth: {
            "code": "queue.nonempty",
            "domain": "queue",
            "address": "",
            "message": "Queue contains work." if depth else "Queue is empty.",
            "severity": "info",
        },
        DiagnosticModel.model_validate,
    )

    assert native_action == "queue.enqueue"
    assert isinstance(observation, DiagnosticModel)
    assert observation.code == "queue.depth"
    assert evaluation.code == "queue.nonempty"


def test_projection_failure_does_not_return_or_render_native_values() -> None:
    class HostileNative:
        def __str__(self) -> str:
            raise AssertionError("native value was stringified")

        def __repr__(self) -> str:
            raise AssertionError("native value was represented")

    native_value = HostileNative()
    with pytest.raises(ValueError, match=r"^Observation projection failed\.$") as captured:
        project_observation(
            native_value,
            lambda value: value,
            DiagnosticModel.model_validate,
        )
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None


@pytest.mark.parametrize(
    "native_value",
    [
        "rejected-action-id",
        {"payload": "secret"},
        Path("/private/run/state"),
        RuntimeError("native failure"),
        "Bearer abcdefghijklmnopqrstuvwxyz",
        "environment-secret-value",
    ],
)
def test_native_redaction_is_default_deny(native_value: object) -> None:
    assert redact_native_value(native_value) == "[redacted]"


def test_native_redaction_never_calls_object_renderers_or_uses_tracebacks() -> None:
    class HostileNative:
        def __str__(self) -> str:
            raise AssertionError("str called")

        def __repr__(self) -> str:
            raise AssertionError("repr called")

    assert redact_native_value(HostileNative()) == "[redacted]"
    assert redact_native_value(TimeoutError("private path /tmp/secret")) == "TimeoutError"


@pytest.mark.parametrize(
    "unsafe",
    [
        "/home/user/secret",
        "~/secret",
        "C:\\private\\state",
        "bearer-token",
        "api_key",
        "Traceback-most-recent-call-last",
        "line\\nwith-control",
        "a" * 129,
        "0123456789abcdef" * 4,
    ],
)
def test_bounded_context_labels_reject_paths_tokens_tracebacks_and_entropy(unsafe: str) -> None:
    assert bounded_context_label(unsafe) == "[redacted]"


def test_bounded_context_labels_preserve_only_short_grammar_checked_text() -> None:
    assert bounded_context_label("queue-cleanup.stage_1") == "queue-cleanup.stage_1"
    assert bounded_context_label("queue-cleanup.stage_1", max_length=8) == "[redacted]"
    with pytest.raises(ValueError, match="between 1 and 128"):
        bounded_context_label("queue", max_length=129)


def test_conformance_helper_delegates_to_published_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = cast(RuntimeTarget, object())
    report = cast(BackendConformanceReport, object())
    captured: dict[str, object] = {}

    def fake_runner(received: RuntimeTarget, **options: object) -> BackendConformanceReport:
        captured["target"] = received
        captured.update(options)
        return report

    monkeypatch.setattr(
        "raes_adapters.base.conformance.run_target_conformance",
        fake_runner,
    )

    result = run_conformance_probe(
        target,
        profile="provisioning-only",
        fixture_root_for_tests=Path("/tmp/fixtures"),
        profiles_root_for_tests=Path("/tmp/profiles"),
        observer_version="toy-observer/v1",
    )

    assert result is report
    assert captured == {
        "target": target,
        "profile": "provisioning-only",
        "root": Path("/tmp/fixtures"),
        "profiles_root": Path("/tmp/profiles"),
        "reference_scenario": None,
        "realization_harness": None,
        "execution_basis": ExecutionBasis.HERMETIC_LIVE,
        "realization_envelope": None,
        "observer_version": "toy-observer/v1",
        "native_conformance": False,
    }
