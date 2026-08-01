#!/usr/bin/env python3
"""Reproduce the bounded CybORG/CAGE-2 qualification evidence."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from urllib.request import ProxyHandler, Request, build_opener

import raes_adapters.cyborg as cyborg
import raes_adapters.cyborg.source_ledger as source_ledger

REPO_ROOT = Path(__file__).resolve().parent.parent
_RUNTIME_FILES = {
    "CybORG/version.txt",
    "CybORG/Shared/Config/defaultconfig.ini",
    "CybORG/Shared/Scenarios/Scenario2.yaml",
}
_SCENARIO_IMAGE_PREFIX = "CybORG/Shared/Scenarios/images/"
_SMOKE_CODE = r"""
import json
from importlib.metadata import distributions
from pathlib import Path
import platform
import random
import sys

import numpy as np
import CybORG as package
from CybORG import CYBORG_VERSION, CybORG
from CybORG.Agents import B_lineAgent, GreenAgent
from CybORG.Agents.SimpleAgents.SleepAgent import SleepAgent
from CybORG.Agents.Wrappers import ChallengeWrapper
from CybORG.Shared.Actions import Restore, Sleep

seed = int(sys.argv[1])
max_steps = int(sys.argv[2])
random.seed(seed)
np.random.seed(seed)
scenario = Path(package.__file__).parent / "Shared" / "Scenarios" / "Scenario2.yaml"
native = CybORG(
    str(scenario),
    "sim",
    agents={"Red": B_lineAgent, "Green": GreenAgent},
)
native.set_seed(seed)
environment = ChallengeWrapper(agent_name="Blue", env=native, max_steps=max_steps)
reset = environment.reset()
steps = []
for _ in range(max_steps):
    result = environment.step(0)
    steps.append(
        {
            "reward_type": type(result[1]).__name__,
            "done": result[2],
            "actions": {
                role.lower(): type(native.get_last_action(role)).__name__
                for role in ("Blue", "Red", "Green")
            },
        }
    )

reward_native = CybORG(
    str(scenario),
    "sim",
    agents={"Red": B_lineAgent, "Green": GreenAgent},
)
reward_native.set_seed(153)
reward_native.reset()
reward_steps = {}
cumulative_blue = 0.0
for logical_step in range(1, 17):
    reward_result = reward_native.step("Blue", Sleep())
    rewards = reward_native.get_rewards()
    cumulative_blue += rewards["Blue"]
    if logical_step in {3, 14, 15, 16}:
        blue = reward_native.get_reward_breakdown("Blue")
        red = reward_native.get_reward_breakdown("Red")
        target = "User4" if logical_step == 3 else "Op_Server0"
        reward_steps[str(logical_step)] = {
            "blue_total": rewards["Blue"],
            "red_total": rewards["Red"],
            "target": target,
            "blue_confidentiality": blue[target].confidentiality,
            "blue_availability": blue[target].availability,
            "red_confidentiality": red[target].confidentiality,
            "red_availability": red[target].availability,
            "source_terminal": reward_result.done,
        }

restore_native = CybORG(
    str(scenario),
    "sim",
    agents={"Red": SleepAgent, "Green": SleepAgent},
)
restore_native.set_seed(153)
restore_native.reset()
restore_result = restore_native.step(
    "Blue",
    Restore(session=0, agent="Blue", hostname="User0"),
)
restore_rewards = restore_native.get_rewards()
dependencies = {
    (dist.metadata["Name"] or "").lower().replace("_", "-"): dist.version
    for dist in distributions()
    if (dist.metadata["Name"] or "").lower() != "cyborg"
}
print(
    json.dumps(
        {
            "version": CYBORG_VERSION,
            "python": platform.python_version(),
            "platform": {
                "system": platform.system(),
                "kernel": platform.release(),
                "machine": platform.machine(),
                "libc": "-".join(platform.libc_ver()),
            },
            "dependencies": dependencies,
            "smoke": {
                "seed": seed,
                "scenario_exists": scenario.is_file(),
                "reset_type": type(reset).__name__,
                "reset_shape": list(reset.shape),
                "step_arity": len(result),
                "reward_types": [step["reward_type"] for step in steps],
                "step_count": len(steps),
                "done_sequence": [step["done"] for step in steps],
                "termination": "ChallengeWrapper.max_steps",
                "role_actions": {
                    role: [step["actions"][role] for step in steps]
                    for role in ("blue", "red", "green")
                },
                "reward_projection": {
                    "seed": 153,
                    "steps": reward_steps,
                    "cumulative_blue_through_step_16": cumulative_blue,
                    "restore": {
                        "hostname": "User0",
                        "blue_total": restore_rewards["Blue"],
                        "red_total": restore_rewards["Red"],
                        "source_terminal": restore_result.done,
                    },
                },
            },
        },
        sort_keys=True,
    )
)
"""

_ADAPTER_SMOKE_CODE = r"""
import json
import textwrap

from raes import parse_sdl
from raes_adapters.cyborg import (
    CYBORG_BACKEND_NAME,
    SourceInstalledCyborgDriver,
    create_cyborg_target,
    translate_scenario,
)
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_contracts.participant_action_arguments import ParticipantValidatedActionSelection
from raes_runtime.manager import RuntimeManager

class AuditedSourceDriver:
    def __init__(self):
        self.delegate = SourceInstalledCyborgDriver(expected_version="2.1")
        self.native_projection_matches = False

    def construct(self, descriptor, *, seed):
        expected = translate_scenario(descriptor)
        native = self.delegate.construct(descriptor, seed=seed)
        scenario = native.environment_controller.scenario
        state = native.environment_controller.state
        expected_subnets = expected["Subnets"]
        expected_agents = expected["Agents"]
        memberships_match = all(
            scenario.get_subnet_hosts(name) == subnet["Hosts"]
            for name, subnet in expected_subnets.items()
        )
        agents_match = (
            sorted(scenario.agents) == sorted(expected_agents)
            and all(
                scenario.get_agent_info(name).actions == info["actions"]
                and scenario.get_agent_info(name).allowed_subnets == info["AllowedSubnets"]
                for name, info in expected_agents.items()
            )
        )
        self.reward_calculators_match = {
            name: scenario.get_agent_info(name).reward_calculator_type
            for name in ("Blue", "Green", "Red")
        } == {
            "Blue": "HybridAvailabilityConfidentiality",
            "Green": "None",
            "Red": "HybridImpactPwn",
        }
        self.native_projection_matches = (
            set(scenario.hosts) == set(expected["Hosts"])
            and set(scenario.subnets) == set(expected_subnets)
            and agents_match
            and memberships_match
            and set(state.hosts) == set(expected["Hosts"])
            and set(state.subnet_name_to_cidr) == set(expected_subnets)
            and self.reward_calculators_match
        )
        return native

    def cleanup(self, handle):
        return self.delegate.cleanup(handle)

    def construct_execution(self, descriptor, *, seed, red_variant):
        return self.delegate.construct_execution(
            descriptor,
            seed=seed,
            red_variant=red_variant,
        )

    def step(self, handle, selection):
        return self.delegate.step(handle, selection)

    def project_evaluation(self, handle, **context):
        return self.delegate.project_evaluation(handle, **context)

    def reset(self, handle, *, seed):
        return self.delegate.reset(handle, seed=seed)

driver = AuditedSourceDriver()
target = create_cyborg_target(driver=driver, seed=3)
scenario = parse_sdl(
    textwrap.dedent(
        '''
        name: cyborg-adapter-smoke
        nodes:
          user: {type: switch}
          user0: {type: vm, os: windows}
        infrastructure:
          user:
            properties: {cidr: 10.20.0.0/24, gateway: 10.20.0.1}
          user0: {count: 1, links: [user]}
        '''
    )
)
execution_plan = RuntimeManager(target).plan(scenario)
if execution_plan.diagnostics:
    raise RuntimeError("CybORG adapter smoke plan was not admitted")
plan = execution_plan.provisioning
result = target.provisioner.apply(plan, RuntimeSnapshot())
configured = target.provisioner.configure_execution("sleep")
selection = ParticipantValidatedActionSelection(
    action_contract_address="participant.action-contract.restore",
    argument_shape_ref="participant.action-argument-shape.cage2",
    proposal_ref="proposal:qualification-restore",
    normalized_arguments=(("hostname", "user0"), ("session", 0)),
)
turn = target.provisioner.execute_turn(
    selection,
    run_id="qualification-run",
    episode_id="qualification-episode",
    action_instance_id="qualification-restore",
    logical_step=1,
    logical_step_limit=2,
)
target.provisioner.commit_evaluation("qualification-restore")
facts = target.provisioner.committed_evaluation()
adapter_reward_projection_checks = {
    "configured": configured,
    "action_succeeded": turn.external_action_succeeded,
    "one_fact": len(facts) == 1,
    "rewards": len(facts) == 1 and facts[0].rewards == (
        ("participant.behavior.blue", -1.1),
        ("participant.behavior.green", 0.0),
        ("participant.behavior.red", 0.1),
    ),
    "components": len(facts) == 1
    and facts[0].components
    == (
        (
            "participant.behavior.blue",
            "provision.node.user0",
            "confidentiality",
            -0.1,
            "source-ledger:reward-components",
        ),
        (
            "participant.behavior.blue",
            None,
            "action-cost",
            -1.0,
            "source-ledger:reward-objectives",
        ),
        (
            "participant.behavior.red",
            "provision.node.user0",
            "confidentiality",
            0.1,
            "source-ledger:reward-components",
        ),
    ),
}
adapter_reward_projection_matches = all(adapter_reward_projection_checks.values())
cleaned = target.provisioner.cleanup()
print(
    json.dumps(
        {
            "backend": CYBORG_BACKEND_NAME,
            "constructed": result.success,
            "cleaned": cleaned,
            "native_projection_matches": driver.native_projection_matches,
            "reward_calculators_match": driver.reward_calculators_match,
            "adapter_reward_projection_matches": adapter_reward_projection_matches,
            "recorded_resources": len(result.snapshot.entries),
            "realization_recorded": result.snapshot.realization_envelope is not None,
        },
        sort_keys=True,
    )
)
"""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_wheel_sha256(path: Path) -> str:
    """Hash wheel member paths and bytes without timestamp-bearing ZIP metadata."""
    digest = hashlib.sha256()
    with zipfile.ZipFile(path) as archive:
        for member in sorted(archive.infolist(), key=lambda item: item.filename):
            digest.update(member.filename.encode("utf-8"))
            digest.update(b"\0")
            digest.update(archive.read(member.filename))
    return digest.hexdigest()


def sanitized_subprocess_env(root: Path) -> dict[str, str]:
    """Create the small public-build environment forwarded to child processes."""
    home = root / "home"
    cache = root / "cache"
    uv_cache = root / "uv-cache"
    for path in (home, cache, uv_cache):
        path.mkdir(parents=True, exist_ok=True)
    return {
        "PATH": os.environ.get("PATH", ""),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "HOME": str(home),
        "XDG_CACHE_HOME": str(cache),
        "UV_CACHE_DIR": str(uv_cache),
        "PIP_CACHE_DIR": str(root / "pip-cache"),
        "PYTHONPATH": "",
        "PYTHONSAFEPATH": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
    }


def validate_smoke(actual: dict[str, Any], expected: dict[str, Any]) -> None:
    """Require the exact bounded structural smoke result and forbid native state."""
    forbidden = {"native_state", "observation_values", "reward_vector", "action_id"}
    if actual != expected or forbidden & set(actual):
        raise RuntimeError("CybORG qualification smoke result mismatch")


def validate_adapter_smoke(actual: dict[str, Any], expected: dict[str, Any]) -> None:
    """Require the exact bounded RAES adapter construction/cleanup result."""

    forbidden = {
        "action_id",
        "native_handle",
        "native_state",
        "observation_values",
        "reward_vector",
    }
    if actual != expected or forbidden & set(actual):
        raise RuntimeError("CybORG qualification adapter smoke result mismatch")


def validate_reproducer_runtime(
    *,
    actual_python: str,
    actual_platform: dict[str, str],
    evidence_runtime: dict[str, Any],
) -> None:
    """Keep the reproducer on the evidence family without claiming range support."""
    expected_python_family = evidence_runtime["python"].split(".")[:2]
    actual_python_family = actual_python.split(".")[:2]
    expected_platform = evidence_runtime["platform"]
    same_platform_family = (
        actual_platform.get("system") == expected_platform["system"]
        and actual_platform.get("machine") == expected_platform["machine"]
        and actual_platform.get("libc", "").partition("-")[0]
        == expected_platform["libc"].partition("-")[0]
    )
    if actual_python_family != expected_python_family or not same_platform_family:
        raise RuntimeError("CybORG qualification reproducer runtime is incompatible")


def _run(
    stage: str,
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=300,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"CybORG qualification stage failed: {stage}")
    return result


def _git_value(source: Path, env: dict[str, str], revision: str) -> str:
    return _run(
        "source identity",
        ["git", "rev-parse", revision],
        cwd=source,
        env=env,
    ).stdout.strip()


def _download_sha256(url: str) -> str:
    digest = hashlib.sha256()
    opener = build_opener(ProxyHandler({}))
    request = Request(url, headers={"User-Agent": "raes-adapters-qualification/1"})
    with opener.open(request, timeout=60) as response:
        for chunk in iter(lambda: response.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _single_wheel(directory: Path) -> Path:
    wheels = sorted(directory.glob("*.whl"))
    if len(wheels) != 1:
        raise RuntimeError("CybORG qualification wheel count mismatch")
    return wheels[0]


def _wheel_members(path: Path) -> set[str]:
    with zipfile.ZipFile(path) as archive:
        return set(archive.namelist())


def _venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _normalized_freeze(
    python: Path,
    *,
    cwd: Path,
    env: dict[str, str],
) -> tuple[list[str], str]:
    output = _run(
        "dependency freeze",
        ["uv", "pip", "freeze", "--python", str(python)],
        cwd=cwd,
        env=env,
    ).stdout
    lines = sorted(
        line.strip()
        for line in output.splitlines()
        if line.strip() and not line.lower().startswith("cyborg")
    )
    normalized = "".join(f"{line}\n" for line in lines)
    return lines, hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _verify_source_files(source: Path, selected_files: list[dict[str, str]]) -> None:
    root = source.resolve()
    for item in selected_files:
        relative = Path(item["path"])
        candidate = (root / relative).resolve()
        if relative.is_absolute() or not candidate.is_relative_to(root) or not candidate.is_file():
            raise RuntimeError("CybORG qualification selected path is invalid")
        if _sha256(candidate) != item["sha256"]:
            raise RuntimeError("CybORG qualification selected source digest mismatch")


def python_source_tree_identity(package_root: Path) -> tuple[int, str]:
    """Return the canonical identity used for pre-import source verification."""

    root = package_root.resolve()
    files = sorted(
        root.rglob("*.py"),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    digest = hashlib.sha256()
    for path in files:
        resolved = path.resolve()
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise RuntimeError("CybORG qualification Python source path is invalid")
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(resolved.read_bytes()).digest())
    return len(files), digest.hexdigest()


def verify_qualification(repo_root: Path = REPO_ROOT) -> None:
    """Rebuild and execute the selected profile from public immutable inputs."""
    record = cyborg.load_qualification()
    patch_text = cyborg.read_compatibility_patch()
    source_record = record["source"]
    patch_record = record["patches"][0]
    runtime_record = record["runtime"]
    dependency_record = record["dependency_resolution"]
    expected_versions = {
        item["name"].lower().replace("_", "-"): item["version"] for item in record["dependencies"]
    }
    dependency_pins = sorted(f"{name}=={version}" for name, version in expected_versions.items())

    if _sha256(repo_root / "uv.lock") != dependency_record["uv_lock_sha256"]:
        raise RuntimeError("CybORG qualification canonical lock digest mismatch")
    if hashlib.sha256(patch_text.encode("utf-8")).hexdigest() != patch_record["sha256"]:
        raise RuntimeError("CybORG qualification patch digest mismatch")

    with tempfile.TemporaryDirectory(prefix="raes-cyborg-qualification-") as directory:
        root = Path(directory)
        source = root / "source"
        env = sanitized_subprocess_env(root)
        _run(
            "source clone",
            [
                "git",
                "clone",
                "--no-checkout",
                "--filter=blob:none",
                source_record["repository"],
                str(source),
            ],
            cwd=root,
            env=env,
        )
        _run(
            "source checkout",
            ["git", "checkout", "--detach", source_record["commit"]],
            cwd=source,
            env=env,
        )
        identities = {
            "commit": _git_value(source, env, "HEAD"),
            "tree": _git_value(source, env, "HEAD^{tree}"),
            "cyborg_tree": _git_value(source, env, "HEAD:CybORG"),
            "package_tree": _git_value(source, env, "HEAD:CybORG/CybORG"),
        }
        if any(identities[key] != source_record[key] for key in identities):
            raise RuntimeError("CybORG qualification source identity mismatch")
        _verify_source_files(source, record["selected_files"])
        integrity = runtime_record["integrity"]
        source_count, source_digest = python_source_tree_identity(source / "CybORG" / "CybORG")
        if (
            source_count != integrity["python_source_count"]
            or source_digest != integrity["python_source_tree_sha256"]
        ):
            raise RuntimeError("CybORG qualification Python source identity mismatch")
        source_problems = source_ledger.validate_source_checkout(
            source,
            source_ledger.load_source_ledger(),
        )
        if source_problems:
            raise RuntimeError("CybORG source ledger source verification failed")

        archive_url = (
            "https://codeload.github.com/cage-challenge/cage-challenge-2/tar.gz/"
            f"{source_record['commit']}"
        )
        if _download_sha256(archive_url) != source_record["archive_sha256"]:
            raise RuntimeError("CybORG qualification source archive digest mismatch")

        original_dist = root / "original-dist"
        _run(
            "original wheel build",
            [
                "uv",
                "build",
                "--wheel",
                "--out-dir",
                str(original_dist),
                str(source / "CybORG"),
            ],
            cwd=root,
            env=env,
        )
        original_wheel = _single_wheel(original_dist)
        original_record = record["packaging"]["unmodified_wheel"]
        if normalized_wheel_sha256(original_wheel) != original_record["normalized_sha256"]:
            raise RuntimeError("CybORG qualification original wheel identity mismatch")
        original_members = _wheel_members(original_wheel)
        if original_members & _RUNTIME_FILES:
            raise RuntimeError(
                "CybORG qualification original wheel unexpectedly includes runtime files"
            )
        if any(
            member.startswith(_SCENARIO_IMAGE_PREFIX) and member.endswith(".yaml")
            for member in original_members
        ):
            raise RuntimeError(
                "CybORG qualification original wheel unexpectedly includes scenarios"
            )

        original_venv = root / "original-venv"
        _run(
            "original venv",
            ["uv", "venv", "--python", "3.12", str(original_venv)],
            cwd=root,
            env=env,
        )
        original_python = _venv_python(original_venv)
        _run(
            "original wheel install",
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(original_python),
                str(original_wheel),
                *dependency_pins,
            ],
            cwd=root,
            env=env,
        )
        import_result = _run(
            "original wheel import",
            [str(original_python), "-c", "import CybORG"],
            cwd=root,
            env=env,
            check=False,
        )
        if import_result.returncode == 0 or "CybORG/version.txt" not in import_result.stderr:
            raise RuntimeError("CybORG qualification original wheel failure mismatch")

        patch_path = root / "cage2-wheel-package-data.patch"
        patch_path.write_text(patch_text, encoding="utf-8")
        _run(
            "patch applicability",
            ["git", "apply", "--check", str(patch_path)],
            cwd=source,
            env=env,
        )
        _run(
            "patch application",
            ["git", "apply", str(patch_path)],
            cwd=source,
            env=env,
        )
        setup_path = source / "CybORG/setup.py"
        if _sha256(setup_path) != patch_record["patched_setup_sha256"]:
            raise RuntimeError("CybORG qualification patched setup digest mismatch")
        patched_blob = _run(
            "patched setup identity",
            ["git", "hash-object", str(setup_path)],
            cwd=source,
            env=env,
        ).stdout.strip()
        if patched_blob != patch_record["patched_setup_blob"]:
            raise RuntimeError("CybORG qualification patched setup identity mismatch")

        patched_dist = root / "patched-dist"
        _run(
            "patched wheel build",
            [
                "uv",
                "build",
                "--wheel",
                "--out-dir",
                str(patched_dist),
                str(source / "CybORG"),
            ],
            cwd=root,
            env=env,
        )
        patched_wheel = _single_wheel(patched_dist)
        patched_record = record["packaging"]["patched_wheel"]
        if normalized_wheel_sha256(patched_wheel) != patched_record["normalized_sha256"]:
            raise RuntimeError("CybORG qualification patched wheel identity mismatch")
        patched_members = _wheel_members(patched_wheel)
        if not patched_members >= _RUNTIME_FILES:
            raise RuntimeError("CybORG qualification patched wheel runtime data mismatch")
        if not any(
            member.startswith(_SCENARIO_IMAGE_PREFIX) and member.endswith(".yaml")
            for member in patched_members
        ):
            raise RuntimeError("CybORG qualification patched wheel scenario data mismatch")

        patched_venv = root / "patched-venv"
        _run(
            "patched venv",
            ["uv", "venv", "--python", "3.12", str(patched_venv)],
            cwd=root,
            env=env,
        )
        patched_python = _venv_python(patched_venv)
        _run(
            "patched wheel install",
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(patched_python),
                str(patched_wheel),
                *dependency_pins,
            ],
            cwd=root,
            env=env,
        )
        frozen, frozen_sha256 = _normalized_freeze(patched_python, cwd=root, env=env)
        if frozen_sha256 != dependency_record["normalized_environment_sha256"]:
            raise RuntimeError("CybORG qualification dependency resolution mismatch")
        if frozen != sorted(f"{name}=={version}" for name, version in expected_versions.items()):
            raise RuntimeError("CybORG qualification dependency set mismatch")

        runtime_dir = root / "runtime"
        runtime_dir.mkdir()
        smoke_result = _run(
            "source-native smoke",
            [
                str(patched_python),
                "-c",
                _SMOKE_CODE,
                str(runtime_record["smoke"]["seed"]),
                str(record["selection"]["wrapper"]["smoke_max_steps"]),
            ],
            cwd=runtime_dir,
            env=env,
        )
        try:
            probe = json.loads(smoke_result.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("CybORG qualification smoke output is invalid") from exc
        if probe.get("version") != source_record["version"]:
            raise RuntimeError("CybORG qualification simulator version mismatch")
        validate_reproducer_runtime(
            actual_python=probe.get("python", ""),
            actual_platform=probe.get("platform", {}),
            evidence_runtime=runtime_record,
        )
        if probe.get("dependencies") != expected_versions:
            raise RuntimeError("CybORG qualification dependency metadata mismatch")
        validate_smoke(probe.get("smoke", {}), runtime_record["smoke"])

        adapter_dist = root / "adapter-dist"
        _run(
            "adapter wheel build",
            [
                "uv",
                "build",
                "--wheel",
                "--out-dir",
                str(adapter_dist),
                str(repo_root),
            ],
            cwd=root,
            env=env,
        )
        adapter_wheel = _single_wheel(adapter_dist)
        _run(
            "adapter wheel install",
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(patched_python),
                str(adapter_wheel),
            ],
            cwd=root,
            env=env,
        )
        adapter_result = _run(
            "RAES adapter construction",
            [str(patched_python), "-c", _ADAPTER_SMOKE_CODE],
            cwd=runtime_dir,
            env=env,
        )
        try:
            adapter_probe = json.loads(adapter_result.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("CybORG qualification adapter smoke output is invalid") from exc
        validate_adapter_smoke(
            adapter_probe,
            runtime_record["adapter_smoke"],
        )


def main(argv: list[str]) -> int:
    if argv:
        raise RuntimeError("CybORG qualification driver accepts no arguments")
    verify_qualification()
    print("CybORG qualification: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
