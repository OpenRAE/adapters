"""Selected CyberBattleSim source admission and native construction seam.

This module owns only backend-local mechanics shared by the serialized driver
and the source-native reproduction collector.  The selected values remain in
``qualification.json``; callers supply its already-normalized selection.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib.metadata import Distribution
from typing import Protocol, cast

from raes_adapters import _source_admission

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


class _SourceEnvironmentModule(Protocol):
    """Typed surface of the selected native environment module."""

    AttackerGoal: Callable[..., object]
    DefenderConstraint: Callable[..., object]


class _DefenderModule(Protocol):
    """Typed surface of the selected native defender module."""

    ScanAndReimageCompromisedMachines: Callable[..., object]


class _EnvironmentWrapper(Protocol):
    """Typed surface returned by the admitted Gymnasium constructor."""

    unwrapped: object


class _GymnasiumModule(Protocol):
    """Typed surface of the admitted Gymnasium module."""

    def make(self, gym_id: object, **kwargs: object) -> _EnvironmentWrapper: ...


@dataclass(frozen=True)
class SelectedNativeRuntime(object):
    """Private installed objects for the one qualified native selection."""

    environment: object
    numpy: object
    selected_distribution: Distribution


def verify_selected_source_identity(
    qualification: dict[str, object], selected_distribution: Distribution
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
        (_CREDENTIAL_CACHE_MODULE, _CREDENTIAL_CACHE_SOURCE_PATH),
        (_AGENT_WRAPPER_MODULE, "cyberbattle/agents/baseline/agent_wrapper.py"),
    ):
        _source_admission.verify_package_origin(module_name, selected_distribution, path)
    _source_admission.verify_package_origin(
        "gymnasium", distributions["gymnasium"], "gymnasium/__init__.py"
    )
    _source_admission.verify_package_origin("numpy", distributions["numpy"], "numpy/__init__.py")
    return distributions


def resolve_and_verify_selected_source(
    qualification: dict[str, object], source: Mapping[str, object]
) -> Distribution:
    """Resolve and verify the selected simulator distribution."""

    package = cast(str, source["package"])
    version = cast(str, source["version"])
    selected_distribution = _source_admission.resolve_selected_distribution(package, version)
    verify_selected_source_identity(qualification, selected_distribution)
    return selected_distribution


def construct_selected_environment(
    qualification: dict[str, object],
    source: Mapping[str, object],
    selection: Mapping[str, object],
    *,
    module_loader: Callable[[str], object] = importlib.import_module,
) -> SelectedNativeRuntime:
    """Construct the exact admitted source environment after identity checks."""

    selected_distribution = resolve_and_verify_selected_source(qualification, source)
    # Importing the package registers CyberBattleChain-v0.
    module_loader("cyberbattle")
    gymnasium = cast(_GymnasiumModule, module_loader("gymnasium"))
    numpy = module_loader("numpy")
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
    source_environment = cast(
        _SourceEnvironmentModule, module_loader("cyberbattle._env.cyberbattle_env")
    )
    defender = cast(_DefenderModule, module_loader("cyberbattle._env.defender"))
    termination = cast(Mapping[str, object], selection["termination"])
    defender_selection = cast(Mapping[str, object], selection["defender"])
    scenario = cast(Mapping[str, object], selection["scenario"])
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
    wrapper = gymnasium.make(
        scenario["gym_id"],
        size=scenario["size"],
        attacker_goal=attacker_goal,
        defender_constraint=defender_constraint,
        defender_agent=defender_agent,
    )
    return SelectedNativeRuntime(
        environment=wrapper.unwrapped,
        numpy=numpy,
        selected_distribution=selected_distribution,
    )


__all__ = [
    "SelectedNativeRuntime",
    "construct_selected_environment",
    "resolve_and_verify_selected_source",
    "verify_selected_source_identity",
]
