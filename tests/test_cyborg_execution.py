"""CybORG aggregate-turn execution through published RAES runtime contracts."""

from __future__ import annotations

import random
import textwrap
from dataclasses import dataclass, field, replace
from threading import Event, Thread
from types import SimpleNamespace
from typing import Any

import pytest
from raes import parse_sdl
from raes_contracts.contracts import (
    ExperimentEpisodeControlModel,
    ExperimentRedVariantSelectionModel,
)
from raes_contracts.contracts.time_model import (
    ClockDeclarationModel,
    ExactRatioModel,
    TimeDomainDeclarationModel,
    TimeModelDeclarationModel,
    TimeProgressionPolicyDeclarationModel,
)
from raes_contracts.participant_action_arguments import ParticipantValidatedActionSelection
from raes_contracts.participant_binding import ParticipantActionAdmissionRequest
from raes_contracts.participant_episode import (
    ParticipantEpisodeInitializeRequest,
    ParticipantEpisodeResetRequest,
)
from raes_contracts.planning import (
    ChangeAction,
    OrchestrationOp,
    OrchestrationPlan,
    PlannedResource,
    RuntimeDomain,
)
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_runtime.manager import RuntimeManager
from raes_runtime.participant_result_contracts import (
    participant_runtime_history_transition_diagnostics,
    participant_runtime_state_contract_diagnostics,
)
from raes_runtime.registry_probes import sample_participant_action_admission_request

from raes_adapters.cyborg import create_cyborg_target
from raes_adapters.cyborg import driver as driver_module
from raes_adapters.cyborg.driver import (
    SourceInstalledCyborgDriver,
    _NativeParticipantOccurrence,
    _NativeTurnResult,
)

_BLUE = "participant.behavior.blue"
_GREEN = "participant.behavior.green"
_RED = "participant.behavior.red"
_SLEEP = "participant.action-contract.sleep"
_ANALYSE = "participant.action-contract.analyse"
_GREEN_PORT_SCAN = "participant.action-contract.green-port-scan"
_CLOCK = "time.clock.cage2"
_WORKFLOW = "orchestration.workflow.cage2-run"

_SDL = """
name: cyborg-execution
nodes:
  user-net: {type: switch}
  user-host: {type: vm, os: linux}
infrastructure:
  user-net:
    properties: {cidr: 10.20.0.0/24, gateway: 10.20.0.1}
  user-host: {count: 1, links: [user-net]}
"""


class HostileNative:
    """Fail if adapter code tries to render or serialize a native value."""

    def __str__(self) -> str:
        raise AssertionError("native value was stringified")

    def __repr__(self) -> str:
        raise AssertionError("native value was represented")


@dataclass
class FakeExecutionDriver:
    """Private mechanical seam recording aggregate source-native calls."""

    seed: int | None = None
    red_variant: str = "sleep"
    source_terminal_at: int | None = None
    malformed_at: int | None = None
    handles: list[HostileNative] = field(default_factory=list)
    cleanup_calls: list[object] = field(default_factory=list)
    selections: list[ParticipantValidatedActionSelection] = field(default_factory=list)
    reconstruction_variants: list[str] = field(default_factory=list)
    resets: int = 0

    def construct(self, descriptor: object, *, seed: int | None) -> object:
        del descriptor
        self.seed = seed
        handle = HostileNative()
        self.handles.append(handle)
        return handle

    def construct_execution(
        self,
        descriptor: object,
        *,
        seed: int | None,
        red_variant: str,
    ) -> object:
        del descriptor
        self.seed = seed
        self.red_variant = red_variant
        self.reconstruction_variants.append(red_variant)
        handle = HostileNative()
        self.handles.append(handle)
        return handle

    def cleanup(self, handle: object) -> bool:
        self.cleanup_calls.append(handle)
        return True

    def reset(self, handle: object, *, seed: int | None) -> bool:
        assert handle in self.handles
        self.seed = seed
        self.resets += 1
        return True

    def step(
        self,
        handle: object,
        selection: ParticipantValidatedActionSelection,
    ) -> object:
        assert handle in self.handles
        self.selections.append(selection)
        turn = len(self.selections)
        if self.malformed_at == turn:
            return HostileNative()
        red_action = {
            "b-line": "participant.action-contract.discover-network-services",
            "meander": "participant.action-contract.discover-remote-systems",
            "sleep": _SLEEP,
        }[self.red_variant]
        return _NativeTurnResult(
            external_action_succeeded=True,
            source_terminal=self.source_terminal_at == turn,
            occurrences=(
                _NativeParticipantOccurrence(_BLUE, selection.action_contract_address),
                _NativeParticipantOccurrence(_GREEN, _GREEN_PORT_SCAN),
                _NativeParticipantOccurrence(_RED, red_action),
            ),
        )


class BlockingExecutionDriver(FakeExecutionDriver):
    """Expose deterministic barriers for the shared-session lock test."""

    def __init__(self) -> None:
        super().__init__()
        self.turn_entered = Event()
        self.turn_release = Event()
        self.reconstruction_entered = Event()

    def construct_execution(
        self,
        descriptor: object,
        *,
        seed: int | None,
        red_variant: str,
    ) -> object:
        self.reconstruction_entered.set()
        return super().construct_execution(
            descriptor,
            seed=seed,
            red_variant=red_variant,
        )

    def step(
        self,
        handle: object,
        selection: ParticipantValidatedActionSelection,
    ) -> object:
        self.turn_entered.set()
        assert self.turn_release.wait(timeout=2)
        return super().step(handle, selection)


def _time_declaration() -> TimeModelDeclarationModel:
    domain = "time.domain.cage2"
    policy = "time.progression.cage2"
    return TimeModelDeclarationModel(
        domains={
            domain: TimeDomainDeclarationModel(
                address=domain,
                kind="logical",
                tick_period_seconds=ExactRatioModel(numerator=1, denominator=1),
                epoch="run_start",
                visibility="runtime_only",
                description="One tick per validated aggregate CybORG turn.",
            )
        },
        clocks={
            _CLOCK: ClockDeclarationModel(
                address=_CLOCK,
                time_domain_address=domain,
                authority_kind="runtime",
                authority_ref="cyborg-cage2-participant-runtime",
                monotonicity="non_decreasing",
                supports_pause=True,
                supports_reset=True,
                supports_jump=False,
                description="RAES-owned CAGE-2 logical step clock.",
            )
        },
        progression_policies={
            policy: TimeProgressionPolicyDeclarationModel(
                address=policy,
                clock_address=_CLOCK,
                advancement_mode="event_driven",
                synchronization_mode="none",
                reset_behavior="new_segment_zero",
                replay_behavior="unsupported",
                description="Only a committed aggregate turn advances this clock.",
            )
        },
    )


def _orchestration_plan(*, max_steps: int, red_variant: str) -> OrchestrationPlan:
    episode_control = ExperimentEpisodeControlModel(
        turn_order="scenario-defined",
        termination_rule="admitted-logical-step-limit-or-source-terminal",
        max_steps=max_steps,
        termination_condition_refs=["source-ledger:wrapper-termination-cutoff"],
    )
    variant = ExperimentRedVariantSelectionModel(
        variant_id=red_variant,
        agent_ref=f"participant.implementation.red-{red_variant}",
    )
    payload: dict[str, object] = {
        "name": "cage2-run",
        "episode_control": episode_control.model_dump(mode="json"),
        "red_variant_selection": variant.model_dump(mode="json"),
        "result_contract": {
            "state_schema_version": "workflow-step-state/v1",
            "observable_steps": {},
        },
        "execution_contract": {
            "state_schema_version": "workflow-step-state/v1",
            "start_step": "",
            "steps": {},
            "step_types": {},
            "control_edges": {},
            "join_owners": {},
            "call_steps": {},
            "observable_steps": [],
        },
    }
    resource = PlannedResource(
        address=_WORKFLOW,
        domain=RuntimeDomain.ORCHESTRATION,
        resource_type="workflow",
        payload=payload,
    )
    operation = OrchestrationOp(
        action=ChangeAction.CREATE,
        address=_WORKFLOW,
        resource_type="workflow",
        payload=payload,
    )
    return OrchestrationPlan(
        resources={_WORKFLOW: resource},
        operations=[operation],
        startup_order=[_WORKFLOW],
    )


def _request(
    action_address: str = _SLEEP,
    *,
    action_instance_id: str = "blue-action-1",
    arguments: tuple[tuple[str, object], ...] = (),
) -> ParticipantActionAdmissionRequest:
    sample = sample_participant_action_admission_request()
    selection = sample.implementation_selection.model_copy(update={"participant_address": _BLUE})
    validated = ParticipantValidatedActionSelection(
        action_contract_address=action_address,
        argument_shape_ref="participant.action-argument-shape.cage2",
        proposal_ref=f"proposal:{action_instance_id}",
        normalized_arguments=arguments,  # type: ignore[arg-type]
    )
    return replace(
        sample,
        participant_address=_BLUE,
        action_contract_address=action_address,
        observation_boundary_address="participant.observation-boundary.blue",
        action_instance_id=action_instance_id,
        implementation_selection=selection,
        validated_selection=validated,
        requires_terminal_outcome=True,
    )


def _prepared_target(
    driver: FakeExecutionDriver,
    *,
    max_steps: int,
    red_variant: str = "sleep",
) -> tuple[Any, RuntimeSnapshot]:
    target = create_cyborg_target(driver=driver, seed=7)
    assert target.orchestrator is not None
    assert target.participant_runtime is not None
    assert target.time_runtime is not None

    planned = RuntimeManager(target).plan(parse_sdl(textwrap.dedent(_SDL)))
    provisioned = target.provisioner.apply(planned.provisioning, RuntimeSnapshot())
    assert provisioned.success
    timed = target.time_runtime.initialize(_time_declaration(), provisioned.snapshot)
    assert timed.success
    started = target.orchestrator.start(
        _orchestration_plan(max_steps=max_steps, red_variant=red_variant),
        timed.snapshot,
    )
    assert started.success
    snapshot = started.snapshot
    for address in (_BLUE, _GREEN, _RED):
        initialized = target.participant_runtime.initialize(
            ParticipantEpisodeInitializeRequest(
                participant_address=address,
                episode_id=f"{address}-episode-1",
            ),
            snapshot,
        )
        assert initialized.success
        snapshot = initialized.snapshot
    return target, snapshot


def test_target_declares_execution_components_without_evaluator() -> None:
    target = create_cyborg_target(driver=FakeExecutionDriver(), seed=7)

    assert target.manifest.has_orchestrator
    assert target.manifest.has_participant_runtime
    assert target.manifest.has_time
    assert not target.manifest.has_evaluator
    assert target.orchestrator is not None
    assert target.participant_runtime is not None
    assert target.time_runtime is not None


@pytest.mark.parametrize(
    ("action_address", "arguments"),
    [
        ("participant.action-contract.unmapped", ()),
        (_SLEEP, (("unknown", "native-id-7"),)),
        (_ANALYSE, (("hostname", "User0"), ("session", 0), ("unknown", "value"))),
        (_ANALYSE, (("hostname", "not-realized"), ("session", 0))),
    ],
)
def test_unmapped_or_invalid_actions_have_no_native_effect(
    action_address: str,
    arguments: tuple[tuple[str, object], ...],
) -> None:
    driver = FakeExecutionDriver()
    target, snapshot = _prepared_target(driver, max_steps=30)
    assert target.participant_runtime is not None

    result = target.participant_runtime.admit_action(
        _request(action_address, arguments=arguments),
        snapshot,
    )

    assert not result.success
    assert result.snapshot is snapshot
    assert driver.selections == []
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].code.startswith("cyborg-backend.action.")
    rendered = str(result.diagnostics[0])
    assert "native-id" not in rendered
    assert "unknown" not in rendered


def test_one_admitted_action_commits_one_aggregate_turn_and_portable_joins() -> None:
    driver = FakeExecutionDriver()
    target, snapshot = _prepared_target(driver, max_steps=30, red_variant="b-line")
    assert target.participant_runtime is not None
    request = _request()

    result = target.participant_runtime.admit_action(request, snapshot)

    assert result.success
    assert participant_runtime_state_contract_diagnostics(result.snapshot) == []
    assert participant_runtime_history_transition_diagnostics(snapshot, result.snapshot) == []
    assert len(driver.selections) == 1
    assert result.action_result is not None
    assert result.action_result.status == "succeeded"
    assert result.action_result.action_instance_id == request.action_instance_id
    assert result.action_result.participant_address == request.participant_address
    assert result.action_result.action_contract_address == request.action_contract_address
    clock = result.snapshot.time_model_state
    assert clock is not None
    assert clock.clocks[_CLOCK].coordinate.tick == 1
    assert list(result.snapshot.shared_state_records) == ["cyborg.shared-state:blue-action-1"]
    assert list(result.snapshot.joint_action_records) == ["cyborg.joint-action:blue-action-1"]
    joint = result.snapshot.joint_action_records["cyborg.joint-action:blue-action-1"]
    assert joint["realized_order"] == [
        "blue-action-1",
        "blue-action-1:green",
        "blue-action-1:red",
    ]
    assert result.snapshot.participant_behavior_history[_GREEN][-1]["action_contract_address"] == (
        _GREEN_PORT_SCAN
    )
    assert result.snapshot.participant_behavior_history[_RED][-1]["action_contract_address"] == (
        "participant.action-contract.discover-network-services"
    )
    portable = repr(result.snapshot)
    for forbidden in ("reward_vector", "action_id", "native-id", "Traceback", "HostileNative"):
        assert forbidden not in portable


@pytest.mark.parametrize(
    "action_address",
    [_ANALYSE, "participant.action-contract.remove", "participant.action-contract.restore"],
)
def test_target_bearing_blue_actions_require_the_realized_host_closure(
    action_address: str,
) -> None:
    driver = FakeExecutionDriver()
    target, snapshot = _prepared_target(driver, max_steps=30)
    assert target.participant_runtime is not None

    result = target.participant_runtime.admit_action(
        _request(action_address, arguments=(("hostname", "user-host"), ("session", 0))),
        snapshot,
    )

    assert result.success
    assert len(driver.selections) == 1


@pytest.mark.parametrize("max_steps", [30, 50, 100])
def test_trial_limit_commits_exactly_declared_logical_steps(max_steps: int) -> None:
    driver = FakeExecutionDriver()
    target, snapshot = _prepared_target(driver, max_steps=max_steps)
    assert target.participant_runtime is not None

    for index in range(max_steps):
        result = target.participant_runtime.admit_action(
            _request(action_instance_id=f"blue-action-{index + 1}"),
            snapshot,
        )
        assert result.success
        snapshot = result.snapshot

    rejected = target.participant_runtime.admit_action(
        _request(action_instance_id="one-too-many"),
        snapshot,
    )
    assert not rejected.success
    assert rejected.snapshot is snapshot
    assert len(driver.selections) == max_steps
    assert snapshot.time_model_state is not None
    assert snapshot.time_model_state.clocks[_CLOCK].coordinate.tick == max_steps


@pytest.mark.parametrize(
    ("variant", "red_action"),
    [
        ("b-line", "participant.action-contract.discover-network-services"),
        ("meander", "participant.action-contract.discover-remote-systems"),
        ("sleep", _SLEEP),
    ],
)
def test_red_variants_and_green_behavior_preserve_declared_order(
    variant: str,
    red_action: str,
) -> None:
    driver = FakeExecutionDriver()
    target, snapshot = _prepared_target(driver, max_steps=30, red_variant=variant)
    assert target.participant_runtime is not None

    result = target.participant_runtime.admit_action(_request(), snapshot)

    assert result.success
    assert driver.reconstruction_variants == [variant]
    joint = result.snapshot.joint_action_records["cyborg.joint-action:blue-action-1"]
    assert joint["realized_order"] == [
        "blue-action-1",
        "blue-action-1:green",
        "blue-action-1:red",
    ]
    assert (
        result.snapshot.participant_behavior_history[_RED][-1]["action_contract_address"]
        == red_action
    )


def test_invalid_post_step_output_quarantines_session_until_reconstruction() -> None:
    driver = FakeExecutionDriver(malformed_at=1)
    target, snapshot = _prepared_target(driver, max_steps=30)
    assert target.participant_runtime is not None
    assert target.orchestrator is not None

    failed = target.participant_runtime.admit_action(_request(), snapshot)
    blocked = target.participant_runtime.admit_action(
        _request(action_instance_id="blue-action-2"),
        snapshot,
    )

    assert not failed.success
    assert failed.snapshot is snapshot
    assert not blocked.success
    assert blocked.snapshot is snapshot
    assert len(driver.selections) == 1
    assert all(
        "HostileNative" not in str(item) for item in (*failed.diagnostics, *blocked.diagnostics)
    )

    restarted = target.orchestrator.start(
        _orchestration_plan(max_steps=30, red_variant="sleep"),
        snapshot,
    )
    assert restarted.success
    recovered = target.participant_runtime.admit_action(
        _request(action_instance_id="blue-action-3"),
        restarted.snapshot,
    )
    assert recovered.success
    assert len(driver.selections) == 2


def test_post_effect_portable_failure_quarantines_the_aggregate_session() -> None:
    driver = FakeExecutionDriver()
    target, snapshot = _prepared_target(driver, max_steps=30)
    assert target.participant_runtime is not None
    incomplete = snapshot.with_entries(
        dict(snapshot.entries),
        participant_episode_results={
            key: value
            for key, value in snapshot.participant_episode_results.items()
            if key != _GREEN
        },
    )

    failed = target.participant_runtime.admit_action(_request(), incomplete)
    blocked = target.participant_runtime.admit_action(
        _request(action_instance_id="after-portable-failure"),
        incomplete,
    )

    assert not failed.success
    assert failed.snapshot is incomplete
    assert failed.diagnostics[0].code == "cyborg-backend.action.portable-commit-failed"
    assert not blocked.success
    assert len(driver.selections) == 1


def test_reconstruction_cannot_interleave_with_an_aggregate_turn() -> None:
    driver = BlockingExecutionDriver()
    target, snapshot = _prepared_target(driver, max_steps=30)
    assert target.participant_runtime is not None
    assert target.orchestrator is not None
    driver.reconstruction_entered.clear()
    action_results: list[object] = []
    restart_results: list[object] = []
    action_thread = Thread(
        target=lambda: action_results.append(
            target.participant_runtime.admit_action(_request(), snapshot)
        )
    )
    restart_thread = Thread(
        target=lambda: restart_results.append(
            target.orchestrator.start(
                _orchestration_plan(max_steps=30, red_variant="meander"),
                snapshot,
            )
        )
    )

    action_thread.start()
    assert driver.turn_entered.wait(timeout=1)
    restart_thread.start()
    assert not driver.reconstruction_entered.wait(timeout=0.1)
    driver.turn_release.set()
    action_thread.join(timeout=2)
    restart_thread.join(timeout=2)

    assert driver.reconstruction_entered.is_set()
    assert len(action_results) == 1
    assert len(restart_results) == 1


def test_source_terminal_stops_before_declared_limit_without_extra_call() -> None:
    driver = FakeExecutionDriver(source_terminal_at=1)
    target, snapshot = _prepared_target(driver, max_steps=30)
    assert target.participant_runtime is not None

    terminal = target.participant_runtime.admit_action(_request(), snapshot)
    rejected = target.participant_runtime.admit_action(
        _request(action_instance_id="after-terminal"),
        terminal.snapshot,
    )

    assert terminal.success
    assert not rejected.success
    assert len(driver.selections) == 1
    assert terminal.snapshot.time_model_state is not None
    assert terminal.snapshot.time_model_state.clocks[_CLOCK].coordinate.tick == 1
    assert any(
        event["event_type"] == "workflow_completed"
        for event in terminal.snapshot.orchestration_history[_WORKFLOW]
    )


def test_controlled_seed_replays_control_facts_without_determinism_claim() -> None:
    facts: list[tuple[object, ...]] = []
    context: dict[str, object] = {}
    for _ in range(2):
        driver = FakeExecutionDriver()
        target, snapshot = _prepared_target(driver, max_steps=30, red_variant="meander")
        assert target.participant_runtime is not None

        result = target.participant_runtime.admit_action(_request(), snapshot)

        assert result.success
        assert driver.seed == 7
        assert result.snapshot.time_model_state is not None
        joint = result.snapshot.joint_action_records["cyborg.joint-action:blue-action-1"]
        facts.append(
            (
                result.action_result.status if result.action_result is not None else None,
                result.snapshot.time_model_state.clocks[_CLOCK].coordinate.tick,
                tuple(joint["realized_order"]),
                result.snapshot.participant_behavior_history[_GREEN][-1]["action_contract_address"],
                result.snapshot.participant_behavior_history[_RED][-1]["action_contract_address"],
            )
        )
        context = result.snapshot.time_management_contexts["cyborg.time-context:blue-action-1"]

    assert facts[0] == facts[1]
    assert "loss-evaluation-seed-unbound" in context["provenance_refs"]
    assert all("deterministic" not in value.lower() for value in context["provenance_refs"])


def test_coordinated_reset_resets_the_aggregate_once() -> None:
    driver = FakeExecutionDriver()
    target, snapshot = _prepared_target(driver, max_steps=30)
    assert target.participant_runtime is not None

    reset = target.participant_runtime.reset_many(
        tuple(
            ParticipantEpisodeResetRequest(
                participant_address=address,
                episode_id=f"{address}-episode-2",
            )
            for address in (_BLUE, _GREEN, _RED)
        ),
        snapshot,
    )

    assert reset.success
    assert driver.resets == 1
    assert {
        value["episode_id"] for value in reset.snapshot.participant_episode_results.values()
    } == {
        f"{_BLUE}-episode-2",
        f"{_GREEN}-episode-2",
        f"{_RED}-episode-2",
    }


def test_exhausted_trial_reset_starts_a_new_logical_segment() -> None:
    driver = FakeExecutionDriver()
    target, snapshot = _prepared_target(driver, max_steps=1)
    assert target.participant_runtime is not None

    exhausted = target.participant_runtime.admit_action(_request(), snapshot)
    assert exhausted.success
    reset = target.participant_runtime.reset_many(
        tuple(
            ParticipantEpisodeResetRequest(
                participant_address=address,
                episode_id=f"{address}-episode-2",
            )
            for address in (_BLUE, _GREEN, _RED)
        ),
        exhausted.snapshot,
    )
    assert reset.success
    resumed = target.participant_runtime.admit_action(
        _request(action_instance_id="new-segment-action"),
        reset.snapshot,
    )

    assert resumed.success
    assert driver.resets == 1
    assert resumed.snapshot.time_model_state is not None
    coordinate = resumed.snapshot.time_model_state.clocks[_CLOCK].coordinate
    assert coordinate.segment == 1
    assert coordinate.tick == 1


def test_partial_reset_is_rejected_without_native_effect() -> None:
    driver = FakeExecutionDriver()
    target, snapshot = _prepared_target(driver, max_steps=30)
    assert target.participant_runtime is not None

    reset = target.participant_runtime.reset_many(
        (ParticipantEpisodeResetRequest(participant_address=_BLUE),),
        snapshot,
    )

    assert not reset.success
    assert reset.snapshot is snapshot
    assert driver.resets == 0


def _fake_native_modules() -> tuple[dict[str, object], SimpleNamespace, object]:
    def action_type() -> type[object]:
        class Action:
            def __init__(self, **kwargs: object) -> None:
                self.kwargs = kwargs

        return Action

    actions = SimpleNamespace(
        **{
            name: action_type()
            for name in (
                "Sleep",
                "Monitor",
                "Analyse",
                "Remove",
                "Restore",
                "GreenPingSweep",
                "GreenPortScan",
                "GreenConnection",
                "DiscoverRemoteSystems",
                "DiscoverNetworkServices",
                "ExploitRemoteService",
                "PrivilegeEscalate",
                "Impact",
            )
        }
    )
    true_value = object()

    class Observation:
        def __init__(self, success: object = true_value) -> None:
            self.data = {"success": success}

    class Results:
        def __init__(
            self,
            *,
            observation: object | None = None,
            error: object | None = None,
            done: object = False,
        ) -> None:
            self.observation = Observation() if observation is None else observation
            self.error = error
            self.done = done

    modules: dict[str, object] = {
        "CybORG.Shared": SimpleNamespace(Results=Results, Observation=Observation),
        "CybORG.Shared.Actions": actions,
        "CybORG.Shared.Enums": SimpleNamespace(TrinaryEnum=SimpleNamespace(TRUE=true_value)),
    }
    return modules, actions, true_value


@pytest.mark.parametrize(
    ("address", "arguments", "native_name", "expected"),
    [
        (_SLEEP, (), "Sleep", {}),
        (
            "participant.action-contract.monitor",
            (("session", 2),),
            "Monitor",
            {"session": 2, "agent": "Blue"},
        ),
        (
            _ANALYSE,
            (("hostname", "user-host"), ("session", 3)),
            "Analyse",
            {"session": 3, "agent": "Blue", "hostname": "user-host"},
        ),
        (
            "participant.action-contract.remove",
            (("hostname", "user-host"), ("session", 4)),
            "Remove",
            {"session": 4, "agent": "Blue", "hostname": "user-host"},
        ),
        (
            "participant.action-contract.restore",
            (("hostname", "user-host"), ("session", 5)),
            "Restore",
            {"session": 5, "agent": "Blue", "hostname": "user-host"},
        ),
    ],
)
def test_source_driver_binds_each_blue_action_with_exact_arguments(
    monkeypatch: pytest.MonkeyPatch,
    address: str,
    arguments: tuple[tuple[str, object], ...],
    native_name: str,
    expected: dict[str, object],
) -> None:
    modules, actions, _ = _fake_native_modules()
    monkeypatch.setattr(driver_module, "import_module", modules.__getitem__)
    selection = _request(address, arguments=arguments).validated_selection
    assert selection is not None

    action = SourceInstalledCyborgDriver._native_blue_action(selection)

    assert type(action) is getattr(actions, native_name)
    assert action.kwargs == expected


def test_source_driver_projects_every_selected_native_action_type() -> None:
    _, actions, _ = _fake_native_modules()
    expected = {
        "Sleep": _SLEEP,
        "Monitor": "participant.action-contract.monitor",
        "Analyse": _ANALYSE,
        "Remove": "participant.action-contract.remove",
        "Restore": "participant.action-contract.restore",
        "GreenPingSweep": "participant.action-contract.green-ping-sweep",
        "GreenPortScan": _GREEN_PORT_SCAN,
        "GreenConnection": "participant.action-contract.green-connection",
        "DiscoverRemoteSystems": "participant.action-contract.discover-remote-systems",
        "DiscoverNetworkServices": "participant.action-contract.discover-network-services",
        "ExploitRemoteService": "participant.action-contract.exploit-remote-service",
        "PrivilegeEscalate": "participant.action-contract.privilege-escalate",
        "Impact": "participant.action-contract.impact",
    }

    for native_name, address in expected.items():
        assert (
            driver_module._project_native_action(getattr(actions, native_name)(), actions)
            == address
        )
    with pytest.raises(ValueError):
        driver_module._project_native_action(object(), actions)


def test_source_driver_step_projects_turn_and_preserves_caller_rng(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    modules, actions, _ = _fake_native_modules()
    monkeypatch.setattr(driver_module, "import_module", modules.__getitem__)
    results_type = modules["CybORG.Shared"].Results

    class NativeHandle:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        def step(self, agent: str, action: object) -> object:
            self.calls.append((agent, action))
            random.random()
            return results_type(done=True)

        def get_last_action(self, agent: str) -> object:
            return actions.GreenPortScan() if agent == "Green" else actions.Impact()

    source_driver = SourceInstalledCyborgDriver(expected_version="2.1")
    native = NativeHandle()
    random.seed(11)
    source_driver._random_states[id(native)] = random.getstate()
    random.seed(99)
    caller_state = random.getstate()
    selection = _request().validated_selection
    assert selection is not None

    projected = source_driver.step(native, selection)

    assert random.getstate() == caller_state
    assert native.calls[0][0] == "Blue"
    assert type(native.calls[0][1]) is actions.Sleep
    assert projected == _NativeTurnResult(
        external_action_succeeded=True,
        source_terminal=True,
        occurrences=(
            _NativeParticipantOccurrence(_BLUE, _SLEEP),
            _NativeParticipantOccurrence(_GREEN, _GREEN_PORT_SCAN),
            _NativeParticipantOccurrence(_RED, "participant.action-contract.impact"),
        ),
    )


def test_source_driver_rejects_invalid_native_turn_outputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    modules, actions, _ = _fake_native_modules()
    monkeypatch.setattr(driver_module, "import_module", modules.__getitem__)
    shared = modules["CybORG.Shared"]

    class NativeHandle:
        def __init__(self, green: object) -> None:
            self.green = green

        def get_last_action(self, agent: str) -> object:
            return self.green if agent == "Green" else actions.Impact()

    valid_handle = NativeHandle(actions.GreenPortScan())
    invalid_results = (
        object(),
        shared.Results(error=object()),
        shared.Results(observation=object()),
    )
    for result in invalid_results:
        with pytest.raises(ValueError):
            SourceInstalledCyborgDriver._project_turn(valid_handle, result, _SLEEP)
    with pytest.raises(ValueError):
        SourceInstalledCyborgDriver._project_turn(
            NativeHandle(object()),
            shared.Results(),
            _SLEEP,
        )


@pytest.mark.parametrize(
    ("variant", "module_name", "attribute"),
    [
        ("b-line", "CybORG.Agents.SimpleAgents.B_line", "B_lineAgent"),
        ("meander", "CybORG.Agents.SimpleAgents.Meander", "RedMeanderAgent"),
        ("sleep", "CybORG.Agents.SimpleAgents.SleepAgent", "SleepAgent"),
    ],
)
def test_source_driver_construct_execution_binds_exact_red_agent(
    monkeypatch: pytest.MonkeyPatch,
    variant: str,
    module_name: str,
    attribute: str,
) -> None:
    source_driver = SourceInstalledCyborgDriver(expected_version="2.1")
    red_agent = object()
    observed: dict[str, object] = {}
    monkeypatch.setattr(source_driver, "_native_binding", lambda: object())
    monkeypatch.setattr(
        driver_module,
        "import_module",
        lambda requested: (
            SimpleNamespace(**{attribute: red_agent}) if requested == module_name else None
        ),
    )

    def construct(
        descriptor: object,
        *,
        seed: int | None,
        agents: dict[str, object] | None,
    ) -> object:
        observed.update(descriptor=descriptor, seed=seed, agents=agents)
        return "native"

    monkeypatch.setattr(source_driver, "_construct", construct)
    descriptor = object()

    result = source_driver.construct_execution(descriptor, seed=7, red_variant=variant)

    assert result == "native"
    assert observed == {"descriptor": descriptor, "seed": 7, "agents": {"Red": red_agent}}


def test_source_driver_construct_execution_rejects_invalid_policy_bindings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_driver = SourceInstalledCyborgDriver(expected_version="2.1")
    monkeypatch.setattr(source_driver, "_native_binding", lambda: object())

    with pytest.raises(RuntimeError, match="policy is unsupported"):
        source_driver.construct_execution(object(), seed=7, red_variant="unknown")
    monkeypatch.setattr(
        driver_module, "import_module", lambda name: (_ for _ in ()).throw(ImportError(name))
    )
    with pytest.raises(RuntimeError, match="policy could not be bound"):
        source_driver.construct_execution(object(), seed=7, red_variant="sleep")


def test_orchestrator_reports_execution_session_construction_failure() -> None:
    class FailingConstructionDriver(FakeExecutionDriver):
        def construct_execution(
            self,
            descriptor: object,
            *,
            seed: int | None,
            red_variant: str,
        ) -> object:
            del descriptor, seed, red_variant
            raise RuntimeError

    target = create_cyborg_target(driver=FailingConstructionDriver(), seed=7)
    assert target.time_runtime is not None
    assert target.orchestrator is not None
    planned = RuntimeManager(target).plan(parse_sdl(textwrap.dedent(_SDL)))
    provisioned = target.provisioner.apply(planned.provisioning, RuntimeSnapshot())
    assert provisioned.success
    timed = target.time_runtime.initialize(_time_declaration(), provisioned.snapshot)
    assert timed.success

    started = target.orchestrator.start(
        _orchestration_plan(max_steps=30, red_variant="sleep"), timed.snapshot
    )

    assert not started.success
    assert started.snapshot is timed.snapshot
    assert started.diagnostics[0].code == "cyborg-backend.orchestration.session-construction-failed"
