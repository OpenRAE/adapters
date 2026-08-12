"""Private in-process construction driver for the selected CybORG backend."""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import shutil
import sys
import tempfile
import threading
from contextlib import suppress
from importlib import import_module, invalidate_caches
from importlib.machinery import PathFinder
from pathlib import Path
from typing import NamedTuple, Protocol, TypeGuard, cast

from raes_contracts.participant_action_arguments import (  # type: ignore[import-untyped]
    ParticipantValidatedActionSelection,
)

from .qualification import load_qualification
from .scenario import CyborgScenarioDescriptor, translate_scenario

_NATIVE_RANDOM_LOCK = threading.Lock()

_BLUE = "participant.behavior.blue"
_GREEN = "participant.behavior.green"
_RED = "participant.behavior.red"

_SLEEP = "participant.action-contract.sleep"
_MONITOR = "participant.action-contract.monitor"
_ANALYSE = "participant.action-contract.analyse"
_REMOVE = "participant.action-contract.remove"
_RESTORE = "participant.action-contract.restore"


class _NativeParticipantOccurrence(NamedTuple):
    """Portable identity projected from one private native participant turn."""

    participant_address: str
    action_contract_address: str


class _NativeTurnResult(NamedTuple):
    """Strict, bounded projection of a completed aggregate CybORG turn."""

    external_action_succeeded: bool
    source_terminal: bool
    occurrences: tuple[_NativeParticipantOccurrence, ...]


class _NativeRewardComponent(NamedTuple):
    """One finite backend evaluation fact with a portable target identity."""

    participant_address: str
    target_address: str | None
    component: str
    value: float
    source_row: str


class _NativeEvaluationTurn(NamedTuple):
    """Closed evaluation facts projected from one accepted native turn."""

    run_id: str
    episode_id: str
    action_instance_id: str
    logical_step: int
    terminal_cause: str | None
    rewards: tuple[tuple[str, float], ...]
    components: tuple[_NativeRewardComponent, ...]


class _NativeEvaluationContext(NamedTuple):
    """Portable identity and admitted-host context for one native turn."""

    external_address: str
    host_addresses: dict[str, str]
    run_id: str
    episode_id: str
    action_instance_id: str
    logical_step: int
    terminal_cause: str | None


_ACTION_ARGUMENTS: dict[str, frozenset[str]] = {
    _SLEEP: frozenset(),
    _MONITOR: frozenset({"session"}),
    _ANALYSE: frozenset({"hostname", "session"}),
    _REMOVE: frozenset({"hostname", "session"}),
    _RESTORE: frozenset({"hostname", "session"}),
}


def _finite_native_number(value: object) -> float:
    """Accept only plain finite source numeric scalars without rendering them."""

    if type(value) not in {int, float}:
        raise ValueError
    projected = value if type(value) is float else float(cast(int, value))
    if not math.isfinite(projected):
        raise ValueError
    return projected


def _strict_native_mapping(value: object) -> dict[str, object]:
    """Return an exact native dict after rejecting subclasses and non-string keys."""

    if type(value) is not dict:
        raise ValueError
    mapping = cast(dict[object, object], value)
    if any(type(key) is not str for key in mapping):
        raise ValueError
    return cast(dict[str, object], mapping)


def _valid_evaluation_context(context: object) -> TypeGuard[_NativeEvaluationContext]:
    """Validate the closed portable context passed across the driver boundary."""

    if not isinstance(context, _NativeEvaluationContext):
        return False
    identities = (
        context.external_address,
        context.run_id,
        context.episode_id,
        context.action_instance_id,
    )
    return (
        all(isinstance(value, str) and bool(value) for value in identities)
        and type(context.logical_step) is int
        and context.logical_step >= 1
        and context.terminal_cause in {None, "source-terminal", "logical-step-limit"}
        and _valid_host_addresses(context.host_addresses)
    )


def _valid_host_addresses(host_addresses: object) -> bool:
    """Accept only a non-empty exact string-to-string portable host map."""

    if type(host_addresses) is not dict or not host_addresses:
        return False
    mapping = cast(dict[object, object], host_addresses)
    return all(
        type(native_name) is str and bool(native_name) and type(address) is str and bool(address)
        for native_name, address in mapping.items()
    )


def _project_reward_totals(value: object) -> dict[str, float]:
    """Project the exact Blue, Green, and Red total reward surface."""

    rewards = _strict_native_mapping(value)
    if set(rewards) != {"Blue", "Green", "Red"}:
        raise ValueError
    return {
        _BLUE: _finite_native_number(rewards["Blue"]),
        _GREEN: _finite_native_number(rewards["Green"]),
        _RED: _finite_native_number(rewards["Red"]),
    }


def _project_participant_components(
    native: _NativeCyborg,
    source_name: str,
    participant: str,
    host_addresses: dict[str, str],
) -> tuple[list[_NativeRewardComponent], float]:
    """Project one participant's finite host reward breakdown."""

    breakdown = _strict_native_mapping(native.get_reward_breakdown(source_name))
    components: list[_NativeRewardComponent] = []
    total = 0.0
    for native_hostname in sorted(breakdown):
        if native_hostname not in host_addresses:
            raise ValueError
        native_components = breakdown[native_hostname]
        values = (
            (
                "confidentiality",
                _finite_native_number(getattr(native_components, "confidentiality", None)),
            ),
            (
                "availability",
                _finite_native_number(getattr(native_components, "availability", None)),
            ),
        )
        for component, value in values:
            total += value
            if component == "availability" or not math.isclose(
                value, 0.0, rel_tol=0.0, abs_tol=1e-9
            ):
                components.append(
                    _NativeRewardComponent(
                        participant,
                        host_addresses[native_hostname],
                        component,
                        value,
                        "source-ledger:reward-components",
                    )
                )
    return components, total


def _project_reward_components(
    native: _NativeCyborg,
    host_addresses: dict[str, str],
) -> tuple[list[_NativeRewardComponent], dict[str, float]]:
    """Project Blue and Red component ledgers in stable participant order."""

    blue, blue_total = _project_participant_components(native, "Blue", _BLUE, host_addresses)
    red, red_total = _project_participant_components(native, "Red", _RED, host_addresses)
    return blue + red, {_BLUE: blue_total, _RED: red_total}


def _add_action_cost(
    external_address: str,
    totals: dict[str, float],
    component_totals: dict[str, float],
    components: list[_NativeRewardComponent],
) -> list[_NativeRewardComponent]:
    """Reconcile total rewards and add the bounded Blue action-cost component."""

    red_difference = totals[_RED] - component_totals[_RED]
    if not math.isclose(red_difference, 0.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError
    action_cost = totals[_BLUE] - component_totals[_BLUE]
    if action_cost > 0.0 and not math.isclose(action_cost, 0.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError
    if external_address == _RESTORE and not math.isclose(
        action_cost, -1.0, rel_tol=0.0, abs_tol=1e-9
    ):
        raise ValueError
    if not math.isclose(action_cost, 0.0, rel_tol=0.0, abs_tol=1e-9):
        blue_count = sum(item.participant_address == _BLUE for item in components)
        components.insert(
            blue_count,
            _NativeRewardComponent(
                _BLUE,
                None,
                "action-cost",
                action_cost,
                "source-ledger:reward-objectives",
            ),
        )
    return components


def validate_action_selection(selection: object) -> TypeGuard[ParticipantValidatedActionSelection]:
    """Accept only exact, closed normalized bindings supported by CAGE-2 blue."""

    if not isinstance(selection, ParticipantValidatedActionSelection):
        return False
    allowed = _ACTION_ARGUMENTS.get(selection.action_contract_address)
    if allowed is None or set(selection.argument_map) != allowed:
        return False
    values = selection.argument_map
    return ("session" not in values or type(values["session"]) is int) and (
        "hostname" not in values or isinstance(values["hostname"], str)
    )


class _NativeCyborg(Protocol):
    """Minimum native instance surface used behind the driver boundary."""

    def set_seed(self, seed: int) -> None:
        """Set the simulator seed."""

    def reset(self) -> object:
        """Reset the simulator after construction."""

    def shutdown(self) -> None:
        """Release native simulator state."""

    def step(self, agent: str, action: object) -> object:
        """Execute one aggregate source-native turn."""

    def get_last_action(self, agent: str) -> object:
        """Return the private action selected for one participant."""

    def get_rewards(self) -> object:
        """Return source-native participant reward totals for the latest turn."""

    def get_reward_breakdown(self, agent: str) -> object:
        """Return source-native reward components for one participant."""


class _NativeObservation(Protocol):
    """Private observation fields inspected only for the closed success enum."""

    data: dict[str, object]


class _NativeResult(Protocol):
    """Private result fields projected into bounded portable facts."""

    error: object | None
    observation: object
    done: object


class _NativeCyborgType(Protocol):
    """Callable constructor surface exposed by the selected package."""

    def __call__(
        self,
        scenario_path: str,
        mode: str,
        agents: dict[str, object] | None = None,
    ) -> _NativeCyborg:
        """Construct a simulator from one generated scenario document."""


class _NativePackage(Protocol):
    """Selected package attributes inspected after verified import."""

    CYBORG_VERSION: object
    CybORG: _NativeCyborgType
    __file__: str


class _NativeActionTypes(Protocol):
    """Selected native action classes used only for exact-type projection."""

    Sleep: type[object]
    Monitor: type[object]
    Analyse: type[object]
    Remove: type[object]
    Restore: type[object]
    GreenPingSweep: type[object]
    GreenPortScan: type[object]
    GreenConnection: type[object]
    DiscoverRemoteSystems: type[object]
    DiscoverNetworkServices: type[object]
    ExploitRemoteService: type[object]
    PrivilegeEscalate: type[object]
    Impact: type[object]


class CyborgDriver(Protocol):
    """Backend-local driver seam; native handles never cross this protocol."""

    def construct(
        self,
        descriptor: CyborgScenarioDescriptor,
        *,
        seed: int | None,
    ) -> object:
        """Construct and return one private native CybORG backend handle."""

    def cleanup(self, handle: object) -> bool:
        """Try to release one owned native handle idempotently."""


class SourceInstalledCyborgDriver(CyborgDriver):
    """Construct a generated scenario with a user-installed selected CybORG source."""

    def __init__(self, *, expected_version: str) -> None:
        self._expected_version = expected_version
        self._binding_lock = threading.Lock()
        self._runtime_workspace: tempfile.TemporaryDirectory[str] | None = None
        self._cyborg_type: _NativeCyborgType | None = None
        self._random_states: dict[int, object] = {}
        self._ordered_stream_state: object | None = None

    def begin_ordered_stream(self, seed: int) -> None:
        """Initialize one study-scoped Python random stream without global effects."""

        if type(seed) is not int or not 0 <= seed <= 0xFFFFFFFF:
            raise ValueError("ordered stream seed is outside the supported range")
        self._ordered_stream_state = random.Random(seed).getstate()

    def ordered_stream_checkpoint(self) -> object:
        """Return the current opaque stream checkpoint for bounded orchestration."""

        if self._ordered_stream_state is None:
            raise RuntimeError("ordered stream is not initialized")
        return self._ordered_stream_state

    def restore_ordered_stream(self, checkpoint: object) -> None:
        """Restore a checkpoint previously returned by this driver."""

        validator = random.Random()
        try:
            validator.setstate(cast(tuple[object, ...], checkpoint))
        except Exception:
            raise ValueError("ordered stream checkpoint is invalid") from None
        self._ordered_stream_state = checkpoint

    def construct(
        self,
        descriptor: CyborgScenarioDescriptor,
        *,
        seed: int | None,
    ) -> object:
        """Construct the selected backend while keeping native values private."""

        return self._construct(descriptor, seed=seed, agents=None)

    def construct_execution(
        self,
        descriptor: CyborgScenarioDescriptor,
        *,
        seed: int | None,
        red_variant: str,
    ) -> object:
        """Construct with the exact selected CAGE-2 red implementation."""

        self._native_binding()
        agents_module = {
            "b-line": ("CybORG.Agents.SimpleAgents.B_line", "B_lineAgent"),
            "meander": ("CybORG.Agents.SimpleAgents.Meander", "RedMeanderAgent"),
            "sleep": ("CybORG.Agents.SimpleAgents.SleepAgent", "SleepAgent"),
        }.get(red_variant)
        if agents_module is None:
            raise RuntimeError("CybORG execution policy is unsupported.")
        try:
            module_name, attribute = agents_module
            red_agent = getattr(import_module(module_name), attribute)
        except Exception:
            raise RuntimeError("CybORG execution policy could not be bound.") from None
        return self._construct(descriptor, seed=seed, agents={"Red": red_agent})

    def _construct(
        self,
        descriptor: CyborgScenarioDescriptor,
        *,
        seed: int | None,
        agents: dict[str, object] | None,
    ) -> object:
        """Construct a private backend and retain its isolated random stream."""

        cyborg_type = self._native_binding()
        scenario = translate_scenario(descriptor)
        native: _NativeCyborg | None = None
        scenario_path: Path | None = None
        try:
            scenario_path = self._write_scenario(scenario)
            with _NATIVE_RANDOM_LOCK:
                random_state = random.getstate()
                try:
                    if seed is not None:
                        random.seed(seed)
                    elif self._ordered_stream_state is not None:
                        random.setstate(cast(tuple[object, ...], self._ordered_stream_state))
                    native = (
                        cyborg_type(str(scenario_path), "sim")
                        if agents is None
                        else cyborg_type(str(scenario_path), "sim", agents=agents)
                    )
                    if seed is not None:
                        native.set_seed(seed)
                    native.reset()
                    self._random_states[id(native)] = random.getstate()
                finally:
                    random.setstate(random_state)
        except Exception:
            if native is not None:
                self.cleanup(native)
            raise RuntimeError("CybORG backend construction failed.") from None
        finally:
            if scenario_path is not None:
                scenario_path.unlink(missing_ok=True)
        return native

    def cleanup(self, handle: object) -> bool:
        """Shut down an owned CybORG backend without inspecting native output."""

        retained_state = self._random_states.get(id(handle))
        try:
            cast(_NativeCyborg, handle).shutdown()
        except Exception:
            return False
        self._random_states.pop(id(handle), None)
        if retained_state is not None and self._ordered_stream_state is not None:
            self._ordered_stream_state = retained_state
        return True

    def reset(self, handle: object, *, seed: int | None) -> bool:
        """Reset a private session without leaking its global random stream."""

        with _NATIVE_RANDOM_LOCK:
            caller_state = random.getstate()
            try:
                if seed is not None:
                    random.seed(seed)
                    cast(_NativeCyborg, handle).set_seed(seed)
                else:
                    stream_state = self._random_states.get(id(handle))
                    if stream_state is None:
                        raise ValueError
                    random.setstate(cast(tuple[object, ...], stream_state))
                cast(_NativeCyborg, handle).reset()
                self._random_states[id(handle)] = random.getstate()
            except Exception:
                return False
            finally:
                random.setstate(caller_state)
        return True

    def step(
        self,
        handle: object,
        selection: ParticipantValidatedActionSelection,
    ) -> object:
        """Translate one exact blue binding and project one aggregate turn."""

        if not validate_action_selection(selection):
            raise RuntimeError("CybORG action binding is unsupported.")
        native = cast(_NativeCyborg, handle)
        action = self._native_blue_action(selection)
        with _NATIVE_RANDOM_LOCK:
            caller_state = random.getstate()
            try:
                state = self._random_states.get(id(handle))
                if state is None:
                    raise ValueError
                random.setstate(cast(tuple[object, ...], state))
                result = native.step("Blue", action)
                projected = self._project_turn(native, result, selection.action_contract_address)
                self._random_states[id(handle)] = random.getstate()
            except Exception:
                raise RuntimeError("CybORG aggregate turn projection failed.") from None
            finally:
                random.setstate(caller_state)
        return projected

    def project_evaluation(
        self,
        handle: object,
        context: _NativeEvaluationContext,
    ) -> _NativeEvaluationTurn:
        """Read the latest native reward surfaces into a closed fact set."""

        try:
            return self._project_evaluation_turn(cast(_NativeCyborg, handle), context)
        except Exception:
            raise RuntimeError("CybORG evaluation projection failed.") from None

    @staticmethod
    def _native_blue_action(selection: ParticipantValidatedActionSelection) -> object:
        """Bind normalized arguments to fixed source action constructors."""

        actions = import_module("CybORG.Shared.Actions")
        values = selection.argument_map
        address = selection.action_contract_address
        if address == _SLEEP:
            action = actions.Sleep()
        elif address == _MONITOR:
            action = actions.Monitor(session=values["session"], agent="Blue")
        elif address == _ANALYSE:
            action = actions.Analyse(
                session=values["session"], agent="Blue", hostname=values["hostname"]
            )
        elif address == _REMOVE:
            action = actions.Remove(
                session=values["session"], agent="Blue", hostname=values["hostname"]
            )
        elif address == _RESTORE:
            action = actions.Restore(
                session=values["session"], agent="Blue", hostname=values["hostname"]
            )
        else:
            raise ValueError
        return action

    @staticmethod
    def _project_turn(
        native: _NativeCyborg,
        result: object,
        external_address: str,
    ) -> _NativeTurnResult:
        """Map only source types and bounded terminal facts into portable identities."""

        shared = import_module("CybORG.Shared")
        actions = cast(_NativeActionTypes, import_module("CybORG.Shared.Actions"))
        enums = import_module("CybORG.Shared.Enums")
        if type(result) is not shared.Results:
            raise ValueError
        native_result = cast(_NativeResult, result)
        if native_result.error is not None:
            raise ValueError
        observation = native_result.observation
        if isinstance(observation, dict):
            observation_data = observation
        elif type(observation) is shared.Observation:
            observation_data = cast(_NativeObservation, observation).data
        else:
            raise ValueError
        success = observation_data.get("success") == enums.TrinaryEnum.TRUE
        source_terminal = native_result.done is True
        green = _project_native_action(native.get_last_action("Green"), actions)
        red = _project_native_action(native.get_last_action("Red"), actions)
        return _NativeTurnResult(
            external_action_succeeded=success,
            source_terminal=source_terminal,
            occurrences=(
                _NativeParticipantOccurrence(_BLUE, external_address),
                _NativeParticipantOccurrence(_GREEN, green),
                _NativeParticipantOccurrence(_RED, red),
            ),
        )

    @staticmethod
    def _project_evaluation_turn(
        native: _NativeCyborg,
        context: _NativeEvaluationContext,
    ) -> _NativeEvaluationTurn:
        """Project exact finite reward facts without retaining native values."""

        if not _valid_evaluation_context(context):
            raise ValueError

        totals = _project_reward_totals(native.get_rewards())
        components, component_totals = _project_reward_components(native, context.host_addresses)
        components = _add_action_cost(
            context.external_address, totals, component_totals, components
        )

        return _NativeEvaluationTurn(
            run_id=context.run_id,
            episode_id=context.episode_id,
            action_instance_id=context.action_instance_id,
            logical_step=context.logical_step,
            terminal_cause=context.terminal_cause,
            rewards=tuple(totals.items()),
            components=tuple(components),
        )

    def _native_binding(self) -> _NativeCyborgType:
        """Load the constructor from a private snapshot of verified source bytes."""

        with self._binding_lock:
            if self._cyborg_type is not None:
                return self._cyborg_type
            package_root = self._resolve_verified_package_root()
            workspace = tempfile.TemporaryDirectory(prefix="raes-cyborg-runtime-")
            verified_root = Path(workspace.name) / "CybORG"
            try:
                shutil.copytree(
                    package_root,
                    verified_root,
                    ignore=shutil.ignore_patterns(
                        "__pycache__",
                        "*.pyc",
                        "*.pyo",
                        "*.so",
                        "*.pyd",
                        "*.dll",
                        "*.dylib",
                    ),
                )
                self._verify_selected_files(verified_root)
                self._verify_python_source_tree(verified_root)
                package = self._import_verified_snapshot(verified_root)
                version = str(package.CYBORG_VERSION)
                package_file = Path(str(package.__file__)).resolve()
                if package_file.parent != verified_root:
                    raise ValueError
                if version != self._expected_version:
                    raise RuntimeError(
                        "The installed CybORG backend version does not match the selected profile."
                    )
                cyborg_type = package.CybORG
            except RuntimeError:
                workspace.cleanup()
                raise
            except Exception:
                workspace.cleanup()
                raise RuntimeError(
                    "The selected CybORG backend is not installed through its documented "
                    "source route."
                ) from None
            self._runtime_workspace = workspace
            self._cyborg_type = cyborg_type
            return cyborg_type

    @staticmethod
    def _import_verified_snapshot(package_root: Path) -> _NativePackage:
        """Import only from the private source snapshot, never installed bytecode."""

        if any(name == "CybORG" or name.startswith("CybORG.") for name in sys.modules):
            raise RuntimeError(
                "CybORG was imported before the selected source snapshot was verified."
            )
        parent = str(package_root.parent)
        sys.path.insert(0, parent)
        invalidate_caches()
        try:
            package = cast(_NativePackage, import_module("CybORG"))
        finally:
            with suppress(ValueError):
                sys.path.remove(parent)
            invalidate_caches()
        return package

    @staticmethod
    def _write_scenario(scenario: dict[str, dict[str, object]]) -> Path:
        """Write one private canonical JSON document accepted by CybORG's YAML loader."""

        descriptor, raw_path = tempfile.mkstemp(prefix="raes-cyborg-", suffix=".json")
        path = Path(raw_path)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(
                    scenario,
                    stream,
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                stream.write("\n")
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return path

    @classmethod
    def _resolve_verified_package_root(cls) -> Path:
        """Resolve and verify package bytes without executing CybORG code."""

        try:
            spec = PathFinder.find_spec("CybORG")
            if spec is None or spec.origin is None or spec.submodule_search_locations is None:
                raise ValueError
            package_file = Path(spec.origin).resolve()
            package_root = package_file.parent
            search_locations = {
                Path(location).resolve() for location in spec.submodule_search_locations
            }
            if (
                package_file.name != "__init__.py"
                or search_locations != {package_root}
                or not package_file.is_file()
            ):
                raise ValueError
        except Exception:
            raise RuntimeError(
                "The selected CybORG backend is not installed through its documented source route."
            ) from None
        cls._verify_selected_files(package_root)
        cls._verify_python_source_tree(package_root)
        return package_root

    @staticmethod
    def _verify_selected_files(package_root: Path) -> None:
        """Prove the installed runtime files match the maintainer-selected source."""

        prefix = "CybORG/CybORG/"
        selected = [
            item
            for item in load_qualification()["selected_files"]
            if str(item["path"]).startswith(prefix)
        ]
        for item in selected:
            relative = Path(str(item["path"]).removeprefix(prefix))
            candidate = (package_root / relative).resolve()
            valid = (
                not relative.is_absolute()
                and candidate.is_relative_to(package_root)
                and candidate.is_file()
            )
            if not valid or hashlib.sha256(candidate.read_bytes()).hexdigest() != item["sha256"]:
                raise RuntimeError(
                    "The installed CybORG backend source does not match the selected profile."
                )

    @staticmethod
    def _verify_python_source_tree(package_root: Path) -> None:
        """Verify every importable CybORG source file before package execution."""

        try:
            integrity = load_qualification()["runtime"]["integrity"]
            expected_count = int(integrity["python_source_count"])
            expected_digest = str(integrity["python_source_tree_sha256"])
            files = sorted(
                package_root.rglob("*.py"),
                key=lambda path: path.relative_to(package_root).as_posix(),
            )
            digest = hashlib.sha256()
            for path in files:
                resolved = path.resolve()
                if not resolved.is_relative_to(package_root) or not resolved.is_file():
                    raise ValueError
                relative = path.relative_to(package_root).as_posix()
                digest.update(relative.encode("utf-8"))
                digest.update(b"\0")
                digest.update(hashlib.sha256(resolved.read_bytes()).digest())
            valid = len(files) == expected_count and digest.hexdigest() == expected_digest
        except Exception:
            valid = False
        if not valid:
            raise RuntimeError(
                "The installed CybORG backend source does not match the selected profile."
            )


def verify_selected_cyborg_source() -> None:
    """Verify the selected installed source bytes without importing CybORG."""

    SourceInstalledCyborgDriver._resolve_verified_package_root()


def _project_native_action(action: object, actions: _NativeActionTypes) -> str:
    """Project a fixed selected-source action type without rendering native data."""

    bindings = (
        (actions.Sleep, _SLEEP),
        (actions.Monitor, _MONITOR),
        (actions.Analyse, _ANALYSE),
        (actions.Remove, _REMOVE),
        (actions.Restore, _RESTORE),
        (actions.GreenPingSweep, "participant.action-contract.green-ping-sweep"),
        (actions.GreenPortScan, "participant.action-contract.green-port-scan"),
        (actions.GreenConnection, "participant.action-contract.green-connection"),
        (actions.DiscoverRemoteSystems, "participant.action-contract.discover-remote-systems"),
        (actions.DiscoverNetworkServices, "participant.action-contract.discover-network-services"),
        (actions.ExploitRemoteService, "participant.action-contract.exploit-remote-service"),
        (actions.PrivilegeEscalate, "participant.action-contract.privilege-escalate"),
        (actions.Impact, "participant.action-contract.impact"),
    )
    for native_type, address in bindings:
        if type(action) is native_type:
            return address
    raise ValueError


__all__ = [
    "CyborgDriver",
    "SourceInstalledCyborgDriver",
    "verify_selected_cyborg_source",
]
