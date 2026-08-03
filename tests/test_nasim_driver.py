"""Live-driver plumbing for the NASim backend, exercised without the simulator.

The native NASim/Gymnasium/NumPy surfaces are replaced by fakes so the private
driver's construction, installed-source admission, global-NumPy stream
isolation, flat-action resolution, and terminal-fact mapping are verified
hermetically. The shared installed-source verifier itself is exercised
end-to-end by the CyberBattleSim live-driver test.
"""

from __future__ import annotations

import hashlib
import importlib
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest

from raes_adapters.nasim.backend.driver import NasimDriver

_REAL_IMPORT_MODULE = importlib.import_module

_SOURCE_CONTENT = {
    "nasim/__init__.py": b"selected nasim package",
    "nasim/envs/environment.py": b"selected nasim environment",
    "nasim/envs/network.py": b"selected nasim network",
    "nasim/envs/action.py": b"selected nasim action",
    "nasim/scenarios/__init__.py": b"selected nasim scenarios",
    "nasim/scenarios/benchmark/__init__.py": b"selected nasim benchmark package",
    "nasim/scenarios/benchmark/tiny.yaml": b"selected nasim tiny scenario",
    "nasim/agents/bruteforce_agent.py": b"selected nasim bruteforce agent",
}


class _FakeNumpyRandom:
    """A stateful stand-in for the global legacy NumPy RNG."""

    def __init__(self) -> None:
        self.state: object = ("initial",)

    def get_state(self) -> object:
        return self.state

    def set_state(self, state: object) -> None:
        self.state = state

    def seed(self, seed: int) -> None:
        self.state = ("seeded", seed)


class _FakeNumpy:
    def __init__(self) -> None:
        self.random = _FakeNumpyRandom()


class _NativeAction:
    """Base for fakes whose class name matches a native NASim action class."""

    def __init__(self, target: tuple[int, int]) -> None:
        self.target = target


# The driver resolves an action by ``type(action).__name__``; these fakes carry
# the native NASim action class names verbatim.
class Exploit(_NativeAction): ...


class ServiceScan(_NativeAction): ...


class SubnetScan(_NativeAction): ...


class PrivilegeEscalation(_NativeAction): ...


class _FlatActionSpace:
    """A tiny flat action space spanning the four portable action classes."""

    def __init__(self) -> None:
        self._actions = [
            ServiceScan((1, 0)),
            Exploit((2, 0)),
            Exploit((3, 0)),
            SubnetScan((1, 0)),
            PrivilegeEscalation((2, 0)),
        ]
        self.n = len(self._actions)

    def get_action(self, index: int) -> object:
        return self._actions[index]


class _FakeEnvironment:
    def __init__(self, numpy: _FakeNumpy, step_results: list[tuple[object, ...]]) -> None:
        self.action_space = _FlatActionSpace()
        self._numpy = numpy
        self._step_results = step_results
        self.reset_seeds: list[int | None] = []
        self.stepped: list[int] = []
        self.close_calls = 0

    def reset(self, *, seed: int | None) -> tuple[dict[str, object], dict[str, object]]:
        self.reset_seeds.append(seed)
        return ({"native-observation": "must-not-cross"}, {"native-info": "must-not-cross"})

    def step(self, action: int) -> tuple[object, ...]:
        self.stepped.append(action)
        # Simulate consuming the global RNG for the action-success draw.
        self._numpy.random.state = ("stepped", self._numpy.random.state)
        return self._step_results.pop(0)

    def close(self) -> None:
        self.close_calls += 1


def _runtime_root_record(root_path: str, content_by_path: dict[str, bytes]) -> dict[str, object]:
    digest = hashlib.sha256()
    selected_paths = sorted(
        path for path in content_by_path if path == root_path or path.startswith(f"{root_path}/")
    )
    for selected_path in selected_paths:
        digest.update(selected_path.encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(content_by_path[selected_path]).hexdigest().encode())
        digest.update(b"\n")
    return {"path": root_path, "file_count": len(selected_paths), "sha256": digest.hexdigest()}


class _SelectedDistribution:
    def __init__(self, version: str, root: Path, files: tuple[str, ...]) -> None:
        self.version = version
        self.root = root
        self.files = files
        self.direct_url_text: str | None = None

    def locate_file(self, path: str) -> Path:
        return self.root / path

    def read_text(self, filename: str) -> str | None:
        return self.direct_url_text if filename == "direct_url.json" else None


def _install_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    step_results: list[tuple[object, ...]],
) -> tuple[NasimDriver, _FakeEnvironment, _FakeNumpy]:
    """Wire fake distributions, modules, and qualification for one driver."""

    source_root = tmp_path / "nasim-distribution"
    for source_path, content in _SOURCE_CONTENT.items():
        installed = source_root / source_path
        installed.parent.mkdir(parents=True, exist_ok=True)
        installed.write_bytes(content)
    dependency_roots = {
        "gymnasium": tmp_path / "gymnasium-distribution",
        "numpy": tmp_path / "numpy-distribution",
    }
    dependency_content = {
        name: {f"{name}/__init__.py": f"selected {name}".encode()} for name in dependency_roots
    }
    for name, root in dependency_roots.items():
        package_init = root / name / "__init__.py"
        package_init.parent.mkdir(parents=True)
        package_init.write_bytes(f"selected {name}".encode())
    distributions = {
        "nasim": _SelectedDistribution("0.12.0", source_root, tuple(_SOURCE_CONTENT)),
        "gymnasium": _SelectedDistribution(
            "0.26.3", dependency_roots["gymnasium"], ("gymnasium/__init__.py",)
        ),
        "numpy": _SelectedDistribution("1.26.4", dependency_roots["numpy"], ("numpy/__init__.py",)),
    }
    module_origins = {
        "nasim": source_root / "nasim/__init__.py",
        "nasim.envs.action": source_root / "nasim/envs/action.py",
        "nasim.envs.network": source_root / "nasim/envs/network.py",
        "gymnasium": dependency_roots["gymnasium"] / "gymnasium/__init__.py",
        "numpy": dependency_roots["numpy"] / "numpy/__init__.py",
    }
    numpy = _FakeNumpy()
    environment = _FakeEnvironment(numpy, step_results)
    modules: dict[str, object] = {
        "nasim": SimpleNamespace(
            make_benchmark=lambda name, **kwargs: environment,
        ),
        "numpy": numpy,
    }

    def _import(name: str) -> object:
        return modules[name] if name in modules else _REAL_IMPORT_MODULE(name)

    _import_selected: Callable[[str], object] = _import
    qualification = {
        "source": {"package": "nasim", "version": "0.12.0"},
        "protocol": {"selection": {"scenario": {"name": "tiny"}}},
        "source_files": [
            {"path": path, "sha256": hashlib.sha256(content).hexdigest()}
            for path, content in _SOURCE_CONTENT.items()
        ],
        "runtime_artifacts": [
            {
                "name": "nasim",
                "version": "0.12.0",
                "artifact": {
                    "filename": "nasim-0.12.0-py3-none-any.whl",
                    "sha256": "1" * 64,
                    "require_direct_archive_sha256": True,
                    "runtime_identity": "complete-root-tree",
                },
                "roots": [_runtime_root_record("nasim", _SOURCE_CONTENT)],
            },
            {
                "name": "gymnasium",
                "version": "0.26.3",
                "artifact": {
                    "filename": "Gymnasium-0.26.3-py3-none-any.whl",
                    "sha256": "2" * 64,
                    "require_direct_archive_sha256": False,
                    "runtime_identity": "complete-root-tree",
                },
                "roots": [_runtime_root_record("gymnasium", dependency_content["gymnasium"])],
            },
            {
                "name": "numpy",
                "version": "1.26.4",
                "artifact": {
                    "filename": "numpy-1.26.4-cp312-manylinux.whl",
                    "sha256": "3" * 64,
                    "require_direct_archive_sha256": False,
                    "runtime_identity": "complete-root-tree",
                },
                "roots": [_runtime_root_record("numpy", dependency_content["numpy"])],
            },
        ],
        "dependencies": [
            {"name": "nasim", "version": "0.12.0"},
            {"name": "gymnasium", "version": "0.26.3"},
            {"name": "numpy", "version": "1.26.4"},
        ],
    }
    monkeypatch.setattr(
        "raes_adapters._source_admission.distribution",
        lambda name: distributions[name],
    )
    monkeypatch.setattr(
        "raes_adapters._source_admission.find_spec",
        lambda name: SimpleNamespace(origin=str(module_origins[name])),
    )
    monkeypatch.setattr(
        "raes_adapters.nasim.backend.driver.find_spec",
        lambda name: SimpleNamespace(origin="/usr/lib/_tkinter.so"),
    )
    monkeypatch.setattr(
        "raes_adapters.nasim.backend.driver.load_qualification",
        lambda: qualification,
    )
    monkeypatch.setattr(
        "raes_adapters.nasim.backend.driver.importlib.import_module",
        _import_selected,
    )
    return NasimDriver(), environment, numpy


def test_live_driver_isolates_numpy_and_maps_goal_termination(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    driver, environment, numpy = _install_environment(
        monkeypatch,
        tmp_path,
        step_results=[
            ({"obs": "x"}, -1.0, False, False, {"native-info": "must-not-cross"}),
            ({"obs": "y"}, 100.0, True, False, {"native-info": "must-not-cross"}),
        ],
    )
    numpy.random.state = ("caller-owned",)

    reset = driver.reset(20260802)
    assert environment.reset_seeds == [20260802]
    assert reset.applied_streams == ("numpy-global-action-success", "gym-environment-reset")
    assert reset.unbound_streams == ()
    # The caller's global NumPy stream is restored after the bounded op.
    assert numpy.random.state == ("caller-owned",)

    scan = driver.step("service-discovery", "provision.node.host-1-0")
    assert environment.stepped == [0]  # first ServiceScan
    assert scan.source_transition
    assert scan.processed
    assert scan.step_number == 1
    assert scan.terminated is False
    assert scan.truncated is False
    assert scan.terminal_cause is None
    assert numpy.random.state == ("caller-owned",)

    exploit = driver.step("service-exploit", "provision.node.host-3-0")
    assert environment.stepped == [0, 2]  # the Exploit targeting (3, 0)
    assert exploit.terminated is True
    assert exploit.truncated is False
    assert exploit.terminal_cause == "goal"

    evaluation = driver.evaluate()
    assert evaluation.step_count == 2
    assert evaluation.cumulative_reward == 99.0
    assert evaluation.terminated is True
    assert evaluation.terminal_cause == "goal"

    # The fake environment emits native observation/info payloads; none of that
    # native data may survive into the sanitized driver outputs.
    for sanitized in (scan, exploit, evaluation):
        assert "must-not-cross" not in str(sanitized)

    first_close = driver.close()
    second_close = driver.close()
    assert first_close.verified
    assert not first_close.already_closed
    assert second_close.verified
    assert second_close.already_closed
    assert environment.close_calls == 1


def test_live_driver_maps_step_limit_truncation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    driver, _environment, _numpy = _install_environment(
        monkeypatch,
        tmp_path,
        step_results=[({"obs": "z"}, -1.0, False, True, {"native-info": "must-not-cross"})],
    )
    driver.reset(20260802)
    step = driver.step("subnet-discovery")

    assert step.terminated is False
    assert step.truncated is True
    assert step.terminal_cause == "step-limit"


def test_live_driver_fails_before_mutation_on_unresolvable_target(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    driver, environment, _numpy = _install_environment(monkeypatch, tmp_path, step_results=[])
    driver.reset(20260802)

    # A supplied target that does not resolve to a native coordinate must not
    # silently degrade to the first action of the class on some other host.
    step = driver.step("service-exploit", "provision.node.switch-core")

    assert step.source_transition is False
    assert step.processed is False
    assert environment.stepped == []


def test_live_driver_rejects_unsupported_action_and_requires_reset(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    driver, _environment, _numpy = _install_environment(monkeypatch, tmp_path, step_results=[])

    driver.construct()
    with pytest.raises(RuntimeError, match="must be reset"):
        driver.step("service-exploit")

    driver.reset(None)
    with pytest.raises(ValueError, match="unsupported NASim action kind"):
        driver.step("deploy-defender")


def test_live_driver_rejects_missing_tk(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    driver, _environment, _numpy = _install_environment(monkeypatch, tmp_path, step_results=[])
    monkeypatch.setattr(
        "raes_adapters.nasim.backend.driver.find_spec",
        lambda name: None,
    )
    with pytest.raises(RuntimeError, match="Tk system libraries"):
        driver.construct()


def test_live_driver_rejects_tampered_source_tree(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    driver, _environment, _numpy = _install_environment(monkeypatch, tmp_path, step_results=[])
    tampered = tmp_path / "nasim-distribution" / "nasim/envs/network.py"
    tampered.write_bytes(b"tampered network module")
    with pytest.raises(RuntimeError, match="dependency identity could not be verified"):
        driver.construct()
