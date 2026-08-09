"""Private CyberBattleSim lifecycle and source-transition boundary."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from importlib.metadata import Distribution
from threading import RLock
from typing import Protocol, TypedDict, cast

from raes_adapters import _source_admission
from raes_adapters.cyberbattlesim import load_qualification

_SUPPORTED_ACTION_KINDS = frozenset(
    {
        "connect",
        "local-vulnerability",
        "remote-vulnerability",
    }
)
_NATIVE_ACTION_KIND = {
    "connect": "connect",
    "local-vulnerability": "local_vulnerability",
    "remote-vulnerability": "remote_vulnerability",
}
_PORTABLE_TARGET_BY_ACTION_KIND = {
    "connect": "provision.node.customer-data",
    "local-vulnerability": "provision.node.linux-relay",
    "remote-vulnerability": "provision.node.windows-relay",
}
_CREDENTIAL_CACHE_SOURCE_PATH = "cyberbattle/agents/baseline/agent_randomcredlookup.py"
_CREDENTIAL_CACHE_MODULE = "cyberbattle.agents.baseline.agent_randomcredlookup"
_AGENT_WRAPPER_MODULE = "cyberbattle.agents.baseline.agent_wrapper"
_RUNTIME_SOURCE_PATHS = (
    "cyberbattle/__init__.py",
    _CREDENTIAL_CACHE_SOURCE_PATH,
    "cyberbattle/agents/baseline/learner.py",
    "cyberbattle/_env/cyberbattle_env.py",
    "cyberbattle/_env/defender.py",
    "cyberbattle/_env/cyberbattle_chain.py",
    "cyberbattle/samples/chainpattern/chainpattern.py",
)
_RUNTIME_ARTIFACT_NAMES = frozenset({"cyberbattlesim", "gymnasium", "numpy"})
_QUALIFICATION_INVALID = _source_admission.QUALIFICATION_INVALID


def _verify_selected_source_identity(
    qualification: dict[str, object],
    selected_distribution: Distribution,
) -> dict[str, Distribution]:
    """Verify the complete pinned runtime without constructing an environment."""

    distributions = _source_admission.verify_runtime_artifacts(
        qualification,
        selected_distribution,
        expected_names=_RUNTIME_ARTIFACT_NAMES,
        primary_name="cyberbattlesim",
    )
    _source_admission.verify_runtime_source_tree(
        qualification,
        selected_distribution,
        import_root="cyberbattle",
    )
    _source_admission.verify_selected_source_files(
        qualification,
        selected_distribution,
        source_paths=_RUNTIME_SOURCE_PATHS,
    )
    for module_name, path in (
        ("cyberbattle", "cyberbattle/__init__.py"),
        (
            _CREDENTIAL_CACHE_MODULE,
            _CREDENTIAL_CACHE_SOURCE_PATH,
        ),
        (
            _AGENT_WRAPPER_MODULE,
            "cyberbattle/agents/baseline/agent_wrapper.py",
        ),
    ):
        _source_admission.verify_package_origin(
            module_name,
            selected_distribution,
            path,
        )
    _source_admission.verify_package_origin(
        "gymnasium",
        distributions["gymnasium"],
        "gymnasium/__init__.py",
    )
    _source_admission.verify_package_origin(
        "numpy",
        distributions["numpy"],
        "numpy/__init__.py",
    )
    return distributions


class _ActionSpace(Protocol):
    """Native action-space methods used by the driver."""

    def seed(self, seed: int) -> None: ...


class _NativeEnvironment(Protocol):
    """Selected native environment surface kept behind the driver."""

    action_space: _ActionSpace

    def reset(self, *, seed: int | None) -> object: ...

    def step(self, action: dict[str, object]) -> object: ...

    def close(self) -> None: ...


class _EnvironmentWrapper(Protocol):
    """Gymnasium wrapper surface used to obtain the native environment."""

    unwrapped: _NativeEnvironment


class _GymnasiumModule(Protocol):
    """Gymnasium module surface used by the selected construction path."""

    def make(self, gym_id: str, **kwargs: object) -> _EnvironmentWrapper: ...


class _NumpyRandomModule(Protocol):
    """One random draw used by the pinned evaluator policy."""

    def rand(self) -> float: ...


class _NumpyModule(Protocol):
    """NumPy operations needed for private action-mask selection."""

    int32: object
    random: _NumpyRandomModule

    def argwhere(self, mask: object) -> Sequence[object]: ...

    def asarray(self, value: object, *, dtype: object) -> object: ...


class _SourceEnvironmentModule(Protocol):
    """Selected source environment constructors used by the driver."""

    AttackerGoal: Callable[..., object]
    DefenderConstraint: Callable[..., object]


class _DefenderModule(Protocol):
    """Selected source defender constructor used by the driver."""

    ScanAndReimageCompromisedMachines: Callable[..., object]


class _SourcePolicy(Protocol):
    """Selected source policy kept entirely behind the driver boundary."""

    def new_episode(self) -> None: ...

    def explore(self, wrapped_env: object) -> tuple[str, object, object]: ...

    def exploit(
        self, wrapped_env: object, observation: object
    ) -> tuple[str, object | None, object]: ...

    def on_step(
        self,
        wrapped_env: object,
        observation: object,
        reward: object,
        done: object,
        truncated: object,
        info: object,
        action_metadata: object,
    ) -> None: ...


class _SourcePolicyModule(Protocol):
    """Constructor surface of the qualified source participant module."""

    CredentialCacheExploiter: Callable[[], _SourcePolicy]


class _SourceWrapperModule(Protocol):
    """Minimal qualified wrapper constructors used by the selected policy."""

    AgentWrapper: Callable[[object, object], object]
    StateAugmentation: Callable[[object], object]


class _SelectedSource(TypedDict):
    """Normalized selected source identity."""

    package: str
    version: str


class _ScenarioSelection(TypedDict):
    """Normalized scenario construction values."""

    gym_id: str
    size: int


class _TerminationSelection(TypedDict):
    """Normalized termination and evaluator-cutoff values."""

    attacker_own_atleast: int
    attacker_own_atleast_percent: int | float
    defender_maintain_sla: int | float
    evaluator_cutoff_steps: int


class _DefenderSelection(TypedDict):
    """Normalized defender construction values."""

    probability: int | float
    scan_capacity: int
    scan_frequency: int


class _Selection(TypedDict):
    """Normalized selected native protocol configuration."""

    scenario: _ScenarioSelection
    termination: _TerminationSelection
    defender: _DefenderSelection


@dataclass(frozen=True)
class DriverResetReport(object):
    """Sanitized reset and stochastic-control dispositions."""

    operation_ref: str
    applied_streams: tuple[str, ...]
    unbound_streams: tuple[str, ...]


@dataclass(frozen=True)
class DriverStep(object):
    """Sanitized facts from at most one source transition."""

    operation_ref: str
    step_number: int
    source_transition: bool
    processed: bool
    terminated: bool
    truncated: bool
    terminal_cause: str | None
    portable_target_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class DriverEvaluation(object):
    """Evaluator-only source facts; never a participant result."""

    step_count: int
    cumulative_reward: float
    terminated: bool
    truncated: bool
    terminal_cause: str | None
    execution_ref: str = "driver.reset.injected"
    projection_ref: str = "driver.reset.injected.evaluation.1"


@dataclass(frozen=True)
class DriverCleanupReport(object):
    """Sanitized close and verification facts."""

    operation_ref: str
    closed: bool
    verified: bool
    already_closed: bool


@dataclass(frozen=True)
class AutonomousActionProposal(object):
    """Portable authorization coordinates for one private native proposal."""

    action_kind: str
    target_address: str
    proposal_ref: str


class CyberBattleSimDriverProtocol(Protocol):
    """Injectable boundary implemented by the live and test drivers."""

    def construct(self) -> None: ...

    def reset(self, seed: int | None) -> DriverResetReport: ...

    def propose_autonomous_action(self, *, epsilon: float) -> AutonomousActionProposal: ...

    def step(
        self,
        action_kind: str,
        *,
        target_address: str | None = None,
        proposal_ref: str | None = None,
    ) -> DriverStep: ...

    def evaluate(self) -> DriverEvaluation: ...

    def close(self) -> DriverCleanupReport: ...

    def verify_closed(self) -> bool: ...


class CyberBattleSimDriver(object):
    """Lazy in-process driver for the selected public chain profile.

    Native objects never leave this class. The portable action selects one
    semantic action kind; the driver resolves the first currently available
    native coordinate from the private source mask. This keeps discovery-order
    indices and credential-cache positions out of RAES artifacts.
    """

    def __init__(self) -> None:
        self._max_steps: int | None = None
        self._lock = RLock()
        self._environment: _NativeEnvironment | None = None
        self._numpy: _NumpyModule | None = None
        self._last_observation: object | None = None
        self._autonomous_policy: _SourcePolicy | None = None
        self._autonomous_wrapper: object | None = None
        self._pending_native_action: dict[str, object] | None = None
        self._pending_action_kind: str | None = None
        self._pending_target_address: str | None = None
        self._pending_proposal_ref: str | None = None
        self._pending_action_metadata: object | None = None
        self._step_count = 0
        self._operation_count = 0
        self._evaluation_count = 0
        self._execution_ref: str | None = None
        self._cumulative_reward = 0.0
        self._terminated = False
        self._truncated = False
        self._terminal_cause: str | None = None
        self._closed = True
        self._artifacts_verified = False
        self._selected_distribution: Distribution | None = None

    def construct(self) -> None:
        """Construct the selected source environment once, on demand."""

        with self._lock:
            if self._environment is not None and not self._closed:
                return
            qualification, source, selection = self._selected_configuration()
            selected_distribution = _source_admission.resolve_selected_distribution(
                source["package"],
                source["version"],
            )

            if not self._artifacts_verified:
                _verify_selected_source_identity(qualification, selected_distribution)
            self._selected_distribution = selected_distribution
            # Importing ``cyberbattle`` registers CyberBattleChain-v0.
            importlib.import_module("cyberbattle")
            gymnasium = cast(_GymnasiumModule, importlib.import_module("gymnasium"))
            numpy = cast(_NumpyModule, importlib.import_module("numpy"))
            _source_admission.verify_package_origin(
                "cyberbattle._env.cyberbattle_env",
                selected_distribution,
                "cyberbattle/_env/cyberbattle_env.py",
            )
            _source_admission.verify_package_origin(
                "cyberbattle._env.defender",
                selected_distribution,
                "cyberbattle/_env/defender.py",
            )
            self._artifacts_verified = True
            source_environment = cast(
                _SourceEnvironmentModule,
                importlib.import_module("cyberbattle._env.cyberbattle_env"),
            )
            defender = cast(
                _DefenderModule,
                importlib.import_module("cyberbattle._env.defender"),
            )
            termination = selection["termination"]
            defender_selection = selection["defender"]
            attacker_goal = source_environment.AttackerGoal(
                own_atleast=termination["attacker_own_atleast"],
                own_atleast_percent=termination["attacker_own_atleast_percent"],
            )
            defender_constraint = source_environment.DefenderConstraint(
                maintain_sla=termination["defender_maintain_sla"]
            )
            defender_agent = defender.ScanAndReimageCompromisedMachines(
                probability=defender_selection["probability"],
                scan_capacity=defender_selection["scan_capacity"],
                scan_frequency=defender_selection["scan_frequency"],
            )
            environment = gymnasium.make(
                selection["scenario"]["gym_id"],
                size=selection["scenario"]["size"],
                attacker_goal=attacker_goal,
                defender_constraint=defender_constraint,
                defender_agent=defender_agent,
            ).unwrapped
            self._environment = environment
            self._numpy = numpy
            self._max_steps = termination["evaluator_cutoff_steps"]
            self._closed = False

    def reset(self, seed: int | None) -> DriverResetReport:
        """Reset the source and report bounded random-stream coverage."""

        with self._lock:
            self.construct()
            environment = self._require_environment()
            reset_result = environment.reset(seed=seed)
            if not isinstance(reset_result, tuple) or len(reset_result) != 2:
                raise RuntimeError("selected simulator reset returned an unsupported shape")
            self._last_observation = reset_result[0]
            applied: tuple[str, ...] = ()
            unbound: tuple[str, ...] = (
                "gym-environment",
                "gym-action-space",
                "python-random",
                "numpy-global",
            )
            if seed is not None:
                environment.action_space.seed(seed)
                applied = ("gym-environment", "gym-action-space")
                unbound = ("python-random", "numpy-global")
            operation_ref = self._next_operation_ref("reset")
            self._step_count = 0
            self._evaluation_count = 0
            self._execution_ref = operation_ref
            self._cumulative_reward = 0.0
            self._terminated = False
            self._truncated = False
            self._terminal_cause = None
            self._autonomous_policy = None
            self._autonomous_wrapper = None
            self._clear_pending_action()
            return DriverResetReport(
                operation_ref=operation_ref,
                applied_streams=applied,
                unbound_streams=unbound,
            )

    def propose_autonomous_action(self, *, epsilon: float) -> AutonomousActionProposal:
        """Return only the semantic kind of one qualified source-policy proposal.

        The native proposal remains pending and driver-private until a matching
        public RAES action request reaches :meth:`step`. Merely asking the policy
        for a proposal can therefore never mutate the simulator.
        """

        with self._lock:
            if not 0.0 <= epsilon <= 1.0:
                raise ValueError("autonomous epsilon is outside the supported range")
            self._require_environment()
            if self._last_observation is None or self._numpy is None:
                raise RuntimeError("selected simulator must be reset before action selection")
            if self._pending_native_action is not None:
                raise RuntimeError("selected autonomous proposal is already pending admission")
            policy, wrapper = self._require_autonomous_policy()
            draw = self._numpy.random.rand()
            if draw <= epsilon:
                _style, action, metadata = policy.explore(wrapper)
            else:
                _style, action, metadata = policy.exploit(wrapper, self._last_observation)
                if not action:
                    _style, action, metadata = policy.explore(wrapper)
            kind, normalized = self._normalize_policy_action(action)
            target_address = _PORTABLE_TARGET_BY_ACTION_KIND[kind]
            proposal_ref = self._next_operation_ref("proposal")
            self._pending_native_action = normalized
            self._pending_action_kind = kind
            self._pending_target_address = target_address
            self._pending_proposal_ref = proposal_ref
            self._pending_action_metadata = metadata
            return AutonomousActionProposal(
                action_kind=kind,
                target_address=target_address,
                proposal_ref=proposal_ref,
            )

    def step(
        self,
        action_kind: str,
        *,
        target_address: str | None = None,
        proposal_ref: str | None = None,
    ) -> DriverStep:
        """Resolve one private native action and perform at most one source step."""

        with self._lock:
            if action_kind not in _SUPPORTED_ACTION_KINDS:
                raise ValueError("unsupported CyberBattleSim action kind")
            environment = self._require_environment()
            if self._last_observation is None:
                raise RuntimeError("selected simulator must be reset before action execution")
            operation_ref = self._next_operation_ref("step")
            native_action, autonomous = self._admitted_native_action(
                action_kind,
                target_address,
                proposal_ref,
            )
            if native_action is None:
                return DriverStep(
                    operation_ref=operation_ref,
                    step_number=self._step_count,
                    source_transition=False,
                    processed=False,
                    terminated=False,
                    truncated=False,
                    terminal_cause=None,
                )

            step_result = environment.step(native_action)
            if not isinstance(step_result, tuple) or len(step_result) != 5:
                self._clear_pending_action()
                raise RuntimeError("selected simulator step returned an unsupported shape")
            observation, reward, terminated, truncated, source_info = step_result
            if autonomous:
                policy, wrapper = self._require_autonomous_policy()
                policy.on_step(
                    wrapper,
                    observation,
                    reward,
                    terminated,
                    truncated,
                    source_info,
                    self._pending_action_metadata,
                )
            self._clear_pending_action()
            self._last_observation = observation
            self._step_count += 1
            self._cumulative_reward += float(reward)
            self._terminated = bool(terminated)
            self._truncated = bool(truncated)
            if self._terminated:
                self._terminal_cause = "source-terminated"
            elif self._truncated:
                self._terminal_cause = "source-truncated"
            elif self._step_count >= self._require_max_steps():
                self._terminal_cause = "evaluator-cutoff"
            else:
                self._terminal_cause = None
            return DriverStep(
                operation_ref=operation_ref,
                step_number=self._step_count,
                source_transition=True,
                processed=True,
                terminated=self._terminated,
                truncated=self._truncated,
                terminal_cause=self._terminal_cause,
            )

    def _admitted_native_action(
        self,
        action_kind: str,
        target_address: str | None,
        proposal_ref: str | None,
    ) -> tuple[dict[str, object] | None, bool]:
        """Return the native action only when a pending proposal matches exactly."""

        autonomous = self._pending_native_action is not None
        if not autonomous:
            return self._resolve_native_action(action_kind), False
        matches_pending = all(
            (
                action_kind == self._pending_action_kind,
                target_address == self._pending_target_address,
                proposal_ref == self._pending_proposal_ref,
            )
        )
        if not matches_pending:
            self._clear_pending_action()
            raise ValueError("autonomous proposal does not match admitted authorization")
        return self._pending_native_action, True

    def evaluate(self) -> DriverEvaluation:
        """Return evaluator-only facts without advancing the simulator."""

        with self._lock:
            self._require_environment()
            execution_ref = self._execution_ref
            if execution_ref is None:
                raise RuntimeError("selected simulator must be reset before evaluation")
            self._evaluation_count += 1
            return DriverEvaluation(
                execution_ref=execution_ref,
                projection_ref=f"{execution_ref}.evaluation.{self._evaluation_count}",
                step_count=self._step_count,
                cumulative_reward=self._cumulative_reward,
                terminated=self._terminated,
                truncated=self._truncated,
                terminal_cause=self._terminal_cause,
            )

    def close(self) -> DriverCleanupReport:
        """Close the source environment idempotently."""

        with self._lock:
            already_closed = self._closed
            if self._environment is not None and not self._closed:
                self._environment.close()
            self._environment = None
            self._last_observation = None
            self._execution_ref = None
            self._autonomous_policy = None
            self._autonomous_wrapper = None
            self._clear_pending_action()
            self._closed = True
            return DriverCleanupReport(
                operation_ref=self._next_operation_ref("close"),
                closed=True,
                verified=self.verify_closed(),
                already_closed=already_closed,
            )

    def verify_closed(self) -> bool:
        """Verify the bounded in-process ownership state."""

        with self._lock:
            return self._closed and self._environment is None

    def _require_autonomous_policy(self) -> tuple[_SourcePolicy, object]:
        if self._autonomous_policy is None or self._autonomous_wrapper is None:
            environment = self._require_environment()
            observation = self._last_observation
            if observation is None:
                raise RuntimeError("selected simulator must be reset before action selection")
            policy_module = cast(
                _SourcePolicyModule,
                importlib.import_module(_CREDENTIAL_CACHE_MODULE),
            )
            wrapper_module = cast(
                _SourceWrapperModule,
                importlib.import_module(_AGENT_WRAPPER_MODULE),
            )
            selected_distribution = self._selected_distribution
            if selected_distribution is None:
                raise RuntimeError("selected simulator source identity is unavailable")
            _source_admission.verify_package_origin(
                _CREDENTIAL_CACHE_MODULE,
                selected_distribution,
                _CREDENTIAL_CACHE_SOURCE_PATH,
            )
            _source_admission.verify_package_origin(
                _AGENT_WRAPPER_MODULE,
                selected_distribution,
                "cyberbattle/agents/baseline/agent_wrapper.py",
            )
            policy = policy_module.CredentialCacheExploiter()
            wrapper = wrapper_module.AgentWrapper(
                environment,
                wrapper_module.StateAugmentation(observation),
            )
            policy.new_episode()
            self._autonomous_policy = policy
            self._autonomous_wrapper = wrapper
        return self._autonomous_policy, self._autonomous_wrapper

    @staticmethod
    def _normalize_policy_action(action: object) -> tuple[str, dict[str, object]]:
        if not isinstance(action, Mapping) or len(action) != 1:
            raise RuntimeError("selected source policy returned an unsupported action shape")
        native_kind, value = next(iter(action.items()))
        kind_by_native = {value: key for key, value in _NATIVE_ACTION_KIND.items()}
        kind = kind_by_native.get(native_kind)
        if kind is None:
            raise RuntimeError("selected source policy returned an unsupported action kind")
        return kind, {native_kind: value}

    def _clear_pending_action(self) -> None:
        self._pending_native_action = None
        self._pending_action_kind = None
        self._pending_target_address = None
        self._pending_proposal_ref = None
        self._pending_action_metadata = None

    def _resolve_native_action(self, action_kind: str) -> dict[str, object] | None:
        if not isinstance(self._last_observation, Mapping):
            raise RuntimeError("selected simulator observation has an unsupported shape")
        masks = self._last_observation.get("action_mask")
        if not isinstance(masks, Mapping):
            raise RuntimeError("selected simulator action availability is unavailable")
        native_kind = _NATIVE_ACTION_KIND[action_kind]
        native_mask = masks.get(native_kind)
        numpy = self._numpy
        if numpy is None:
            raise RuntimeError("selected simulator numeric runtime is unavailable")
        coordinates = numpy.argwhere(native_mask)
        if len(coordinates) == 0:
            return None
        selected = numpy.asarray(coordinates[0], dtype=numpy.int32)
        return {native_kind: selected}

    def _require_environment(self) -> _NativeEnvironment:
        if self._environment is None or self._closed:
            raise RuntimeError("selected simulator environment is not constructed")
        return self._environment

    def _require_max_steps(self) -> int:
        if self._max_steps is None:
            raise RuntimeError("selected simulator cutoff is unavailable")
        return self._max_steps

    @staticmethod
    def _selected_configuration() -> tuple[dict[str, object], _SelectedSource, _Selection]:
        """Load and normalize the maintainer-selected native configuration."""

        qualification = cast(dict[str, object], load_qualification())
        source = qualification.get("source")
        protocol = qualification.get("protocol")
        if not isinstance(source, dict) or not isinstance(protocol, dict):
            raise RuntimeError(_QUALIFICATION_INVALID)
        package = source.get("package")
        version = source.get("version")
        selection = protocol.get("selection")
        if not isinstance(package, str) or not isinstance(version, str):
            raise RuntimeError(_QUALIFICATION_INVALID)
        if not isinstance(selection, dict):
            raise RuntimeError(_QUALIFICATION_INVALID)
        return (
            qualification,
            {"package": package, "version": version},
            CyberBattleSimDriver._normalize_selection(selection),
        )

    @staticmethod
    def _normalize_selection(selection: dict[object, object]) -> _Selection:
        """Validate the three selected construction sections independently."""

        scenario = selection.get("scenario")
        termination = selection.get("termination")
        defender = selection.get("defender")
        if not all(isinstance(section, dict) for section in (scenario, termination, defender)):
            raise RuntimeError(_QUALIFICATION_INVALID)
        return {
            "scenario": CyberBattleSimDriver._normalize_scenario(
                cast(dict[object, object], scenario)
            ),
            "termination": CyberBattleSimDriver._normalize_termination(
                cast(dict[object, object], termination)
            ),
            "defender": CyberBattleSimDriver._normalize_defender(
                cast(dict[object, object], defender)
            ),
        }

    @staticmethod
    def _normalize_scenario(section: dict[object, object]) -> _ScenarioSelection:
        """Validate and normalize the selected scenario."""

        gym_id = section.get("gym_id")
        size = section.get("size")
        if not isinstance(gym_id, str) or not isinstance(size, int):
            raise RuntimeError(_QUALIFICATION_INVALID)
        return {"gym_id": gym_id, "size": size}

    @staticmethod
    def _normalize_termination(section: dict[object, object]) -> _TerminationSelection:
        """Validate and normalize selected termination controls."""

        own_atleast = section.get("attacker_own_atleast")
        own_percent = section.get("attacker_own_atleast_percent")
        maintain_sla = section.get("defender_maintain_sla")
        cutoff = section.get("evaluator_cutoff_steps")
        if not isinstance(own_atleast, int) or not isinstance(own_percent, (int, float)):
            raise RuntimeError(_QUALIFICATION_INVALID)
        if not isinstance(maintain_sla, (int, float)):
            raise RuntimeError(_QUALIFICATION_INVALID)
        if not isinstance(cutoff, int) or cutoff <= 0:
            raise RuntimeError(_QUALIFICATION_INVALID)
        return {
            "attacker_own_atleast": own_atleast,
            "attacker_own_atleast_percent": own_percent,
            "defender_maintain_sla": maintain_sla,
            "evaluator_cutoff_steps": cutoff,
        }

    @staticmethod
    def _normalize_defender(section: dict[object, object]) -> _DefenderSelection:
        """Validate and normalize selected defender controls."""

        probability = section.get("probability")
        scan_capacity = section.get("scan_capacity")
        scan_frequency = section.get("scan_frequency")
        if not isinstance(probability, (int, float)):
            raise RuntimeError(_QUALIFICATION_INVALID)
        if not isinstance(scan_capacity, int) or not isinstance(scan_frequency, int):
            raise RuntimeError(_QUALIFICATION_INVALID)
        return {
            "probability": probability,
            "scan_capacity": scan_capacity,
            "scan_frequency": scan_frequency,
        }

    def _next_operation_ref(self, operation: str) -> str:
        self._operation_count += 1
        return f"driver.{operation}.{self._operation_count}"


def verify_selected_cyberbattlesim_source() -> None:
    """Verify the complete pinned source without importing or constructing it."""

    qualification, source, _selection = CyberBattleSimDriver._selected_configuration()
    selected_distribution = _source_admission.resolve_selected_distribution(
        source["package"], source["version"]
    )
    _verify_selected_source_identity(qualification, selected_distribution)


__all__ = [
    "AutonomousActionProposal",
    "CyberBattleSimDriver",
    "CyberBattleSimDriverProtocol",
    "DriverCleanupReport",
    "DriverEvaluation",
    "DriverResetReport",
    "DriverStep",
    "verify_selected_cyberbattlesim_source",
]
