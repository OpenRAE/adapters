"""Private NASim lifecycle and source-transition boundary.

The driver is the only code that touches native NASim, Gymnasium, or NumPy
objects. The selected ``tiny`` static benchmark is fully observed natively, so
every fact that leaves this class is a bounded, sanitized projection: the flat
action index, the raw ``(56,)`` observation vector, host state, and ``info``
never cross. Action success is drawn from the process-global legacy NumPy RNG
(``nasim/envs/network.py``); the driver keeps that stream isolated behind a
process-wide lock and its own saved state so it neither corrupts nor is
corrupted by unrelated caller code.
"""

from __future__ import annotations

import importlib
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from importlib.util import find_spec
from typing import Protocol, cast

from raes_adapters import _source_admission
from raes_adapters.nasim import load_qualification

# One process-wide lock guards the global NumPy RNG while a native operation
# runs, so concurrent adapters cannot interleave on the shared stream.
_NATIVE_RANDOM_LOCK = threading.Lock()

# Portable action-contract kinds (authored in the SDL) map to the native NASim
# action class name resolved privately from the flat action space. The class
# names stay inside the driver and never reach a portable artifact.
_NATIVE_ACTION_CLASS = {
    "service-exploit": "Exploit",
    "privilege-escalation": "PrivilegeEscalation",
    "service-discovery": "ServiceScan",
    "subnet-discovery": "SubnetScan",
}
_SUPPORTED_ACTION_KINDS = frozenset(_NATIVE_ACTION_CLASS)

# Selected source files verified per-digest before the native import. Only the
# published wheel's importable ``nasim/`` tree is checked here; the top-level
# git-only files recorded in ``runtime_source_tree`` are provenance evidence.
_RUNTIME_SOURCE_PATHS = (
    "nasim/__init__.py",
    "nasim/envs/environment.py",
    "nasim/envs/network.py",
    "nasim/envs/action.py",
    "nasim/scenarios/__init__.py",
    "nasim/scenarios/benchmark/__init__.py",
    "nasim/scenarios/benchmark/tiny.yaml",
    "nasim/agents/bruteforce_agent.py",
)
_RUNTIME_ARTIFACT_NAMES = frozenset({"nasim", "gymnasium", "numpy"})
_QUALIFICATION_INVALID = _source_admission.QUALIFICATION_INVALID
_TK_UNAVAILABLE = "selected simulator requires the Tk system libraries"

_HOST_REF = re.compile(r"host-(\d+)-(\d+)$")


class _NativeAction(Protocol):
    """The native NASim action surface used for private resolution."""

    target: object


class _FlatActionSpace(Protocol):
    """Native flat action space surface kept behind the driver."""

    n: int

    def get_action(self, index: int) -> _NativeAction: ...


class _NativeEnvironment(Protocol):
    """Selected native NASim environment surface kept behind the driver."""

    action_space: _FlatActionSpace

    def reset(self, *, seed: int | None) -> object: ...

    def step(self, action: int) -> object: ...

    def close(self) -> None: ...


class _NasimModule(Protocol):
    """The selected NASim construction entry point."""

    make_benchmark: Callable[..., _NativeEnvironment]


class _NumpyRandom(Protocol):
    """Global NumPy RNG operations used for stream isolation."""

    def get_state(self) -> object: ...

    def set_state(self, state: object) -> None: ...

    def seed(self, seed: int) -> None: ...


class _NumpyModule(Protocol):
    """NumPy surface used only for global-RNG state isolation."""

    random: _NumpyRandom


@dataclass(frozen=True)
class NasimResetReport(object):
    """Sanitized reset facts and stochastic-control dispositions.

    ``applied_streams`` and ``unbound_streams`` name the selected NASim random
    streams and whether the reset bound each; binding a stream is never a
    deterministic-replay claim.
    """

    operation_ref: str
    applied_streams: tuple[str, ...]
    unbound_streams: tuple[str, ...]


@dataclass(frozen=True)
class NasimStep(object):
    """Sanitized facts from at most one native ``env.step``.

    ``terminated`` (goal reached) and ``truncated`` (step-limit) are retained
    independently. ``terminal_cause`` is ``"goal"`` when the goal is reached,
    ``"step-limit"`` when only the step limit fires, else ``None``; goal takes
    precedence for participant completion while truncation is retained.
    """

    operation_ref: str
    step_number: int
    source_transition: bool
    processed: bool
    terminated: bool
    truncated: bool
    terminal_cause: str | None
    portable_target_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class NasimEvaluation(object):
    """Evaluator-only source facts; never a participant result."""

    step_count: int
    cumulative_reward: float
    terminated: bool
    truncated: bool
    terminal_cause: str | None
    execution_ref: str = "driver.reset.injected"
    projection_ref: str = "driver.reset.injected.evaluation.1"


@dataclass(frozen=True)
class NasimCleanupReport(object):
    """Sanitized close and verification facts."""

    operation_ref: str
    closed: bool
    verified: bool
    already_closed: bool


class NasimDriverProtocol(Protocol):
    """Injectable boundary implemented by the live and test drivers."""

    def construct(self) -> None: ...

    def reset(self, seed: int | None) -> NasimResetReport: ...

    def step(self, action_kind: str, target_ref: str | None = None) -> NasimStep: ...

    def evaluate(self) -> NasimEvaluation: ...

    def close(self) -> NasimCleanupReport: ...

    def verify_closed(self) -> bool: ...


class NasimDriver(object):
    """Lazy in-process driver for the selected NASim ``tiny`` profile.

    Native objects never leave this class. A portable action selects one
    semantic action kind and an optional portable target; the driver resolves
    exactly one native flat action privately, so flat indices and native target
    coordinates stay out of RAES artifacts.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._environment: _NativeEnvironment | None = None
        self._numpy: _NumpyModule | None = None
        self._numpy_state: object | None = None
        self._reset_done = False
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

    def construct(self) -> None:
        """Construct the selected NASim environment once, on demand."""

        with self._lock:
            if self._environment is not None and not self._closed:
                return
            qualification, source, scenario_name = self._selected_configuration()
            selected_distribution = _source_admission.resolve_selected_distribution(
                source["package"],
                source["version"],
            )
            if not self._artifacts_verified:
                distributions = _source_admission.verify_runtime_artifacts(
                    qualification,
                    selected_distribution,
                    expected_names=_RUNTIME_ARTIFACT_NAMES,
                    primary_name="nasim",
                )
                _source_admission.verify_selected_source_files(
                    qualification,
                    selected_distribution,
                    source_paths=_RUNTIME_SOURCE_PATHS,
                )
                if find_spec("_tkinter") is None:
                    raise RuntimeError(_TK_UNAVAILABLE)
                # Verify the top-level module origins resolve inside the selected
                # distributions BEFORE importing NASim. ``find_spec`` does not
                # execute a top-level module, so a shadowing package on the path
                # is rejected before its import-time code can run.
                _source_admission.verify_package_origin(
                    "nasim", selected_distribution, "nasim/__init__.py"
                )
                _source_admission.verify_package_origin(
                    "gymnasium", distributions["gymnasium"], "gymnasium/__init__.py"
                )
                _source_admission.verify_package_origin(
                    "numpy", distributions["numpy"], "numpy/__init__.py"
                )
            # Importing ``nasim`` pulls ``tkinter`` at import time (a disclosed
            # upstream defect); the Tk and origin checks above precede it.
            nasim = cast(_NasimModule, importlib.import_module("nasim"))
            numpy = cast(_NumpyModule, importlib.import_module("numpy"))
            if not self._artifacts_verified:
                # Submodule origins can only be resolved once the parent import
                # has run; their file contents were already digest-verified above.
                _source_admission.verify_package_origin(
                    "nasim.envs.action", selected_distribution, "nasim/envs/action.py"
                )
                _source_admission.verify_package_origin(
                    "nasim.envs.network", selected_distribution, "nasim/envs/network.py"
                )
            self._artifacts_verified = True
            environment = nasim.make_benchmark(
                scenario_name,
                fully_obs=True,
                flat_actions=True,
                flat_obs=True,
                render_mode=None,
            )
            self._environment = environment
            self._numpy = numpy
            self._closed = False

    def reset(self, seed: int | None) -> NasimResetReport:
        """Reset the source under an isolated global-NumPy stream."""

        with self._lock:
            self.construct()
            environment = self._require_environment()
            numpy = self._require_numpy()
            with _NATIVE_RANDOM_LOCK:
                caller_state = numpy.random.get_state()
                try:
                    if seed is not None:
                        # Bind the only stream that controls action success.
                        numpy.random.seed(seed)
                    elif self._numpy_state is not None:
                        numpy.random.set_state(self._numpy_state)
                    reset_result = environment.reset(seed=seed)
                    self._numpy_state = numpy.random.get_state()
                finally:
                    numpy.random.set_state(caller_state)
            if not isinstance(reset_result, tuple) or len(reset_result) != 2:
                raise RuntimeError("selected simulator reset returned an unsupported shape")
            applied: tuple[str, ...]
            unbound: tuple[str, ...]
            if seed is not None:
                applied = ("numpy-global-action-success", "gym-environment-reset")
                unbound = ()
            else:
                applied = ()
                unbound = ("numpy-global-action-success", "gym-environment-reset")
            operation_ref = self._next_operation_ref("reset")
            self._reset_done = True
            self._step_count = 0
            self._evaluation_count = 0
            self._execution_ref = operation_ref
            self._cumulative_reward = 0.0
            self._terminated = False
            self._truncated = False
            self._terminal_cause = None
            return NasimResetReport(
                operation_ref=operation_ref,
                applied_streams=applied,
                unbound_streams=unbound,
            )

    def step(self, action_kind: str, target_ref: str | None = None) -> NasimStep:
        """Resolve one private native flat action and perform one source step."""

        with self._lock:
            if action_kind not in _SUPPORTED_ACTION_KINDS:
                raise ValueError("unsupported NASim action kind")
            environment = self._require_environment()
            numpy = self._require_numpy()
            if not self._reset_done:
                raise RuntimeError("selected simulator must be reset before action execution")
            operation_ref = self._next_operation_ref("step")
            action_index = self._resolve_native_action(environment, action_kind, target_ref)
            if action_index is None:
                return NasimStep(
                    operation_ref=operation_ref,
                    step_number=self._step_count,
                    source_transition=False,
                    processed=False,
                    terminated=False,
                    truncated=False,
                    terminal_cause=None,
                )
            with _NATIVE_RANDOM_LOCK:
                caller_state = numpy.random.get_state()
                try:
                    if self._numpy_state is not None:
                        numpy.random.set_state(self._numpy_state)
                    step_result = environment.step(action_index)
                    self._numpy_state = numpy.random.get_state()
                finally:
                    numpy.random.set_state(caller_state)
            if not isinstance(step_result, tuple) or len(step_result) != 5:
                raise RuntimeError("selected simulator step returned an unsupported shape")
            _observation, reward, terminated, truncated, _info = step_result
            self._step_count += 1
            self._cumulative_reward += float(reward)
            self._terminated = bool(terminated)
            self._truncated = bool(truncated)
            self._terminal_cause = self._resolve_terminal_cause()
            return NasimStep(
                operation_ref=operation_ref,
                step_number=self._step_count,
                source_transition=True,
                processed=True,
                terminated=self._terminated,
                truncated=self._truncated,
                terminal_cause=self._terminal_cause,
            )

    def evaluate(self) -> NasimEvaluation:
        """Return evaluator-only facts without advancing the simulator."""

        with self._lock:
            self._require_environment()
            execution_ref = self._execution_ref
            if execution_ref is None:
                raise RuntimeError("selected simulator must be reset before evaluation")
            self._evaluation_count += 1
            return NasimEvaluation(
                execution_ref=execution_ref,
                projection_ref=f"{execution_ref}.evaluation.{self._evaluation_count}",
                step_count=self._step_count,
                cumulative_reward=self._cumulative_reward,
                terminated=self._terminated,
                truncated=self._truncated,
                terminal_cause=self._terminal_cause,
            )

    def close(self) -> NasimCleanupReport:
        """Close the source environment idempotently."""

        with self._lock:
            already_closed = self._closed
            if self._environment is not None and not self._closed:
                self._environment.close()
            self._environment = None
            self._reset_done = False
            self._execution_ref = None
            self._numpy_state = None
            self._closed = True
            return NasimCleanupReport(
                operation_ref=self._next_operation_ref("close"),
                closed=True,
                verified=self.verify_closed(),
                already_closed=already_closed,
            )

    def verify_closed(self) -> bool:
        """Verify the bounded in-process ownership state."""

        with self._lock:
            return self._closed and self._environment is None

    def _resolve_terminal_cause(self) -> str | None:
        """Retain both terminal facts; goal takes precedence over the limit."""

        if self._terminated:
            return "goal"
        if self._truncated:
            return "step-limit"
        return None

    @staticmethod
    def _resolve_native_action(
        environment: _NativeEnvironment,
        action_kind: str,
        target_ref: str | None,
    ) -> int | None:
        """Find one unambiguous native flat action for the portable request."""

        native_class = _NATIVE_ACTION_CLASS[action_kind]
        target_coordinate = _target_coordinate(target_ref)
        # A target that was supplied but does not resolve to a native coordinate
        # is a malformed selection: fail before mutation rather than silently
        # attacking the first action of the class on some other host.
        if target_ref is not None and target_coordinate is None:
            return None
        action_space = environment.action_space
        for index in range(action_space.n):
            action = action_space.get_action(index)
            if type(action).__name__ != native_class:
                continue
            if target_coordinate is not None and tuple(action.target) != target_coordinate:  # type: ignore[arg-type]
                continue
            return index
        return None

    def _require_environment(self) -> _NativeEnvironment:
        if self._environment is None or self._closed:
            raise RuntimeError("selected simulator environment is not constructed")
        return self._environment

    def _require_numpy(self) -> _NumpyModule:
        if self._numpy is None:
            raise RuntimeError("selected simulator numeric runtime is unavailable")
        return self._numpy

    @staticmethod
    def _selected_configuration() -> tuple[dict[str, object], dict[str, str], str]:
        """Load and validate the maintainer-selected native configuration."""

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
        scenario = selection.get("scenario")
        if not isinstance(scenario, dict):
            raise RuntimeError(_QUALIFICATION_INVALID)
        scenario_name = scenario.get("name")
        if not isinstance(scenario_name, str):
            raise RuntimeError(_QUALIFICATION_INVALID)
        return qualification, {"package": package, "version": version}, scenario_name

    def _next_operation_ref(self, operation: str) -> str:
        self._operation_count += 1
        return f"driver.{operation}.{self._operation_count}"


def _target_coordinate(target_ref: str | None) -> tuple[int, int] | None:
    """Parse a portable ``host-<subnet>-<host>`` reference into a coordinate."""

    if target_ref is None:
        return None
    match = _HOST_REF.search(target_ref)
    if match is None:
        return None
    return (int(match.group(1)), int(match.group(2)))


__all__ = [
    "NasimCleanupReport",
    "NasimDriver",
    "NasimDriverProtocol",
    "NasimEvaluation",
    "NasimResetReport",
    "NasimStep",
]
