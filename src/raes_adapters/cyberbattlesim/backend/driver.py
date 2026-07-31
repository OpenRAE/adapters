"""Private CyberBattleSim lifecycle and source-transition boundary."""

from __future__ import annotations

import hashlib
import importlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.metadata import Distribution, PackageNotFoundError, distribution
from importlib.util import find_spec
from pathlib import Path, PurePosixPath
from threading import RLock
from typing import Any, Protocol, cast

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
_RUNTIME_SOURCE_PATHS = (
    "cyberbattle/__init__.py",
    "cyberbattle/_env/cyberbattle_env.py",
    "cyberbattle/_env/defender.py",
    "cyberbattle/_env/cyberbattle_chain.py",
    "cyberbattle/samples/chainpattern/chainpattern.py",
)


@dataclass(frozen=True)
class DriverResetReport:
    """Sanitized reset and stochastic-control dispositions."""

    operation_ref: str
    applied_streams: tuple[str, ...]
    unbound_streams: tuple[str, ...]


@dataclass(frozen=True)
class DriverStep:
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
class DriverEvaluation:
    """Evaluator-only source facts; never a participant result."""

    step_count: int
    cumulative_reward: float
    terminated: bool
    truncated: bool
    terminal_cause: str | None
    execution_ref: str = "driver.reset.injected"
    projection_ref: str = "driver.reset.injected.evaluation.1"


@dataclass(frozen=True)
class DriverCleanupReport:
    """Sanitized close and verification facts."""

    operation_ref: str
    closed: bool
    verified: bool
    already_closed: bool


class CyberBattleSimDriverProtocol(Protocol):
    """Injectable boundary implemented by the live and test drivers."""

    def construct(self) -> None: ...

    def reset(self, seed: int | None) -> DriverResetReport: ...

    def step(self, action_kind: str) -> DriverStep: ...

    def evaluate(self) -> DriverEvaluation: ...

    def close(self) -> DriverCleanupReport: ...

    def verify_closed(self) -> bool: ...


class CyberBattleSimDriver:
    """Lazy in-process driver for the selected public chain profile.

    Native objects never leave this class. The portable action selects one
    semantic action kind; the driver resolves the first currently available
    native coordinate from the private source mask. This keeps discovery-order
    indices and credential-cache positions out of RAES artifacts.
    """

    def __init__(self) -> None:
        self._max_steps: int | None = None
        self._lock = RLock()
        self._environment: Any | None = None
        self._numpy: Any | None = None
        self._last_observation: object | None = None
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
        """Construct the selected source environment once, on demand."""

        with self._lock:
            if self._environment is not None and not self._closed:
                return
            qualification, source, selection = self._selected_configuration()
            try:
                selected_distribution = distribution(source["package"])
            except PackageNotFoundError as exc:
                raise RuntimeError("selected simulator source is not installed") from exc
            if selected_distribution.version != source["version"]:
                raise RuntimeError("installed simulator version does not match the selected source")

            if not self._artifacts_verified:
                distributions = self._verify_runtime_artifacts(
                    qualification,
                    selected_distribution,
                )
                self._verify_selected_source(qualification, selected_distribution)
                self._verify_package_origin(
                    "cyberbattle",
                    selected_distribution,
                    "cyberbattle/__init__.py",
                )
                self._verify_package_origin(
                    "gymnasium",
                    distributions["gymnasium"],
                    "gymnasium/__init__.py",
                )
                self._verify_package_origin(
                    "numpy",
                    distributions["numpy"],
                    "numpy/__init__.py",
                )
            # Importing ``cyberbattle`` registers CyberBattleChain-v0.
            importlib.import_module("cyberbattle")
            gymnasium: Any = importlib.import_module("gymnasium")
            numpy: Any = importlib.import_module("numpy")
            self._verify_package_origin(
                "cyberbattle._env.cyberbattle_env",
                selected_distribution,
                "cyberbattle/_env/cyberbattle_env.py",
            )
            self._verify_package_origin(
                "cyberbattle._env.defender",
                selected_distribution,
                "cyberbattle/_env/defender.py",
            )
            self._artifacts_verified = True
            source_environment: Any = importlib.import_module("cyberbattle._env.cyberbattle_env")
            defender: Any = importlib.import_module("cyberbattle._env.defender")
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
            return DriverResetReport(
                operation_ref=operation_ref,
                applied_streams=applied,
                unbound_streams=unbound,
            )

    def step(self, action_kind: str) -> DriverStep:
        """Resolve one private native action and perform at most one source step."""

        with self._lock:
            if action_kind not in _SUPPORTED_ACTION_KINDS:
                raise ValueError("unsupported CyberBattleSim action kind")
            environment = self._require_environment()
            if self._last_observation is None:
                raise RuntimeError("selected simulator must be reset before action execution")
            operation_ref = self._next_operation_ref("step")
            native_action = self._resolve_native_action(action_kind)
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
                raise RuntimeError("selected simulator step returned an unsupported shape")
            observation, reward, terminated, truncated, _source_info = step_result
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

    def _require_environment(self) -> Any:
        if self._environment is None or self._closed:
            raise RuntimeError("selected simulator environment is not constructed")
        return self._environment

    def _require_max_steps(self) -> int:
        if self._max_steps is None:
            raise RuntimeError("selected simulator cutoff is unavailable")
        return self._max_steps

    @staticmethod
    def _selected_configuration() -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
        qualification = load_qualification()
        source = qualification.get("source")
        protocol = qualification.get("protocol")
        selection = protocol.get("selection") if isinstance(protocol, dict) else None
        if (
            not isinstance(source, dict)
            or not isinstance(selection, dict)
            or not isinstance(source.get("package"), str)
            or not isinstance(source.get("version"), str)
        ):
            raise RuntimeError("selected simulator qualification is invalid")
        try:
            scenario = selection["scenario"]
            termination = selection["termination"]
            defender = selection["defender"]
            valid = (
                isinstance(scenario, dict)
                and isinstance(scenario["gym_id"], str)
                and isinstance(scenario["size"], int)
                and isinstance(termination, dict)
                and isinstance(termination["attacker_own_atleast"], int)
                and isinstance(termination["attacker_own_atleast_percent"], (int, float))
                and isinstance(termination["defender_maintain_sla"], (int, float))
                and isinstance(termination["evaluator_cutoff_steps"], int)
                and termination["evaluator_cutoff_steps"] > 0
                and isinstance(defender, dict)
                and isinstance(defender["probability"], (int, float))
                and isinstance(defender["scan_capacity"], int)
                and isinstance(defender["scan_frequency"], int)
            )
        except KeyError as exc:
            raise RuntimeError("selected simulator qualification is invalid") from exc
        if not valid:
            raise RuntimeError("selected simulator qualification is invalid")
        return (
            qualification,
            {
                "package": source["package"],
                "version": source["version"],
            },
            selection,
        )

    @staticmethod
    def _verify_selected_source(
        qualification: dict[str, Any],
        selected_distribution: Distribution,
    ) -> None:
        CyberBattleSimDriver._verify_runtime_source_tree(
            qualification,
            selected_distribution,
        )
        source_files = qualification.get("source_files")
        if not isinstance(source_files, list):
            raise RuntimeError("selected simulator source identity could not be verified")
        expected: dict[str, str] = {}
        for entry in source_files:
            if not isinstance(entry, dict):
                continue
            path = entry.get("path")
            digest = entry.get("sha256")
            if isinstance(path, str) and isinstance(digest, str):
                expected[path] = digest
        try:
            for source_path in _RUNTIME_SOURCE_PATHS:
                expected_digest = expected[source_path]
                installed_source = cast(
                    Path,
                    selected_distribution.locate_file(source_path),
                )
                content = installed_source.read_bytes()
                if hashlib.sha256(content).hexdigest() != expected_digest:
                    raise RuntimeError("selected simulator source identity could not be verified")
        except (KeyError, OSError) as exc:
            raise RuntimeError("selected simulator source identity could not be verified") from exc

    @staticmethod
    def _verify_runtime_source_tree(
        qualification: dict[str, Any],
        selected_distribution: Distribution,
    ) -> None:
        tree = qualification.get("runtime_source_tree")
        distribution_files = selected_distribution.files
        if not isinstance(tree, dict) or distribution_files is None:
            raise RuntimeError("selected simulator source identity could not be verified")
        expected_digest = tree.get("sha256")
        expected_count = tree.get("file_count")
        if not isinstance(expected_digest, str) or not isinstance(expected_count, int):
            raise RuntimeError("selected simulator source identity could not be verified")
        paths = CyberBattleSimDriver._runtime_root_paths(
            selected_distribution,
            "cyberbattle",
        )
        if len(paths) != expected_count:
            raise RuntimeError("selected simulator source identity could not be verified")
        digest = hashlib.sha256()
        package_root = cast(
            Path,
            selected_distribution.locate_file("cyberbattle"),
        ).resolve()
        try:
            for source_path in paths:
                portable_path = PurePosixPath(source_path)
                if portable_path.is_absolute() or ".." in portable_path.parts:
                    raise RuntimeError("selected simulator source identity could not be verified")
                installed_source = cast(
                    Path,
                    selected_distribution.locate_file(source_path),
                ).resolve()
                if not installed_source.is_relative_to(package_root):
                    raise RuntimeError("selected simulator source identity could not be verified")
                content_digest = hashlib.sha256(installed_source.read_bytes()).hexdigest()
                digest.update(source_path.encode("utf-8"))
                digest.update(b"\0")
                digest.update(content_digest.encode("ascii"))
                digest.update(b"\n")
        except OSError as exc:
            raise RuntimeError("selected simulator source identity could not be verified") from exc
        if digest.hexdigest() != expected_digest:
            raise RuntimeError("selected simulator source identity could not be verified")

    @staticmethod
    def _verify_runtime_artifacts(
        qualification: dict[str, Any],
        selected_distribution: Distribution,
    ) -> dict[str, Distribution]:
        artifacts = qualification.get("runtime_artifacts")
        dependencies = qualification.get("dependencies")
        if not isinstance(artifacts, list) or not isinstance(dependencies, list):
            raise RuntimeError("selected simulator dependency identity could not be verified")
        selected_versions = {
            str(entry["name"]).casefold(): entry["version"]
            for entry in dependencies
            if isinstance(entry, dict)
            and isinstance(entry.get("name"), str)
            and isinstance(entry.get("version"), str)
        }
        records = {
            str(entry["name"]).casefold(): entry
            for entry in artifacts
            if isinstance(entry, dict) and isinstance(entry.get("name"), str)
        }
        if set(records) != {"cyberbattlesim", "gymnasium", "numpy"}:
            raise RuntimeError("selected simulator dependency identity could not be verified")
        verified: dict[str, Distribution] = {"cyberbattlesim": selected_distribution}
        for package_name, record in records.items():
            expected_version = record.get("version")
            artifact = record.get("artifact")
            artifact_filename = artifact.get("filename") if isinstance(artifact, dict) else None
            artifact_digest = artifact.get("sha256") if isinstance(artifact, dict) else None
            archive_digest_required = (
                artifact.get("require_direct_archive_sha256")
                if isinstance(artifact, dict)
                else None
            )
            runtime_identity = (
                artifact.get("runtime_identity") if isinstance(artifact, dict) else None
            )
            dependency_version = selected_versions.get(package_name)
            if (
                not isinstance(expected_version, str)
                or not isinstance(artifact_filename, str)
                or not CyberBattleSimDriver._is_sha256(artifact_digest)
                or not isinstance(archive_digest_required, bool)
                or runtime_identity != "complete-root-tree"
                or dependency_version != expected_version
            ):
                raise RuntimeError("selected simulator dependency identity could not be verified")
            dependency = verified.get(package_name)
            if dependency is None:
                try:
                    dependency = distribution(package_name)
                except PackageNotFoundError as exc:
                    raise RuntimeError(
                        "selected simulator dependency identity could not be verified"
                    ) from exc
            if dependency.version != expected_version:
                raise RuntimeError("selected simulator dependency identity could not be verified")
            CyberBattleSimDriver._verify_direct_installation(record, dependency)
            CyberBattleSimDriver._verify_artifact_roots(record, dependency)
            verified[package_name] = dependency
        return verified

    @staticmethod
    def _verify_direct_installation(
        record: dict[str, Any],
        selected_distribution: Distribution,
    ) -> None:
        read_text = getattr(selected_distribution, "read_text", None)
        if not callable(read_text):
            return
        direct_url_text = read_text("direct_url.json")
        if direct_url_text is None:
            return
        artifact = record.get("artifact")
        expected_digest = artifact.get("sha256") if isinstance(artifact, dict) else None
        require_archive_digest = (
            artifact.get("require_direct_archive_sha256") if isinstance(artifact, dict) else None
        )
        if not isinstance(expected_digest, str) or not isinstance(require_archive_digest, bool):
            raise RuntimeError("selected simulator dependency identity could not be verified")
        try:
            direct_url = json.loads(direct_url_text)
        except (TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                "selected simulator dependency identity could not be verified"
            ) from exc
        if not isinstance(direct_url, dict) or "dir_info" in direct_url or "vcs_info" in direct_url:
            raise RuntimeError("selected simulator dependency identity could not be verified")
        archive_info = direct_url.get("archive_info")
        hashes = archive_info.get("hashes") if isinstance(archive_info, dict) else None
        legacy_hash = archive_info.get("hash") if isinstance(archive_info, dict) else None
        observed_digest = hashes.get("sha256") if isinstance(hashes, dict) else None
        if observed_digest is None and isinstance(legacy_hash, str):
            algorithm, separator, digest = legacy_hash.partition("=")
            if algorithm == "sha256" and separator:
                observed_digest = digest
        if require_archive_digest and observed_digest != expected_digest:
            raise RuntimeError("selected simulator dependency identity could not be verified")

    @staticmethod
    def _verify_artifact_roots(
        record: dict[str, Any],
        selected_distribution: Distribution,
    ) -> None:
        roots = record.get("roots")
        if not isinstance(roots, list) or not roots:
            raise RuntimeError("selected simulator dependency identity could not be verified")
        for root in roots:
            if not isinstance(root, dict):
                raise RuntimeError("selected simulator dependency identity could not be verified")
            root_path = root.get("path")
            expected_count = root.get("file_count")
            expected_digest = root.get("sha256")
            if (
                not isinstance(root_path, str)
                or not isinstance(expected_count, int)
                or not CyberBattleSimDriver._is_sha256(expected_digest)
            ):
                raise RuntimeError("selected simulator dependency identity could not be verified")
            paths = CyberBattleSimDriver._runtime_root_paths(
                selected_distribution,
                root_path,
            )
            if len(paths) != expected_count:
                raise RuntimeError("selected simulator dependency identity could not be verified")
            digest = hashlib.sha256()
            try:
                for artifact_path in paths:
                    installed_path = cast(
                        Path,
                        selected_distribution.locate_file(artifact_path),
                    )
                    content_digest = hashlib.sha256(installed_path.read_bytes()).hexdigest()
                    digest.update(artifact_path.encode("utf-8"))
                    digest.update(b"\0")
                    digest.update(content_digest.encode("ascii"))
                    digest.update(b"\n")
            except OSError as exc:
                raise RuntimeError(
                    "selected simulator dependency identity could not be verified"
                ) from exc
            if digest.hexdigest() != expected_digest:
                raise RuntimeError("selected simulator dependency identity could not be verified")

    @staticmethod
    def _runtime_root_paths(
        selected_distribution: Distribution,
        root_path: str,
    ) -> list[str]:
        portable_root = PurePosixPath(root_path)
        if portable_root.is_absolute() or ".." in portable_root.parts:
            raise RuntimeError("selected simulator dependency identity could not be verified")
        installed_root = cast(
            Path,
            selected_distribution.locate_file(root_path),
        )
        if installed_root.is_symlink() or not installed_root.is_dir():
            raise RuntimeError("selected simulator dependency identity could not be verified")
        paths: list[str] = []
        try:
            for installed_path in installed_root.rglob("*"):
                if installed_path.is_symlink():
                    raise RuntimeError(
                        "selected simulator dependency identity could not be verified"
                    )
                if installed_path.is_dir():
                    continue
                if not installed_path.is_file():
                    raise RuntimeError(
                        "selected simulator dependency identity could not be verified"
                    )
                relative_path = installed_path.relative_to(installed_root)
                paths.append(str(portable_root / PurePosixPath(relative_path.as_posix())))
        except OSError as exc:
            raise RuntimeError(
                "selected simulator dependency identity could not be verified"
            ) from exc
        return sorted(paths)

    @staticmethod
    def _is_sha256(value: object) -> bool:
        return (
            isinstance(value, str)
            and len(value) == 64
            and all(character in "0123456789abcdef" for character in value)
        )

    @staticmethod
    def _verify_package_origin(
        module_name: str,
        selected_distribution: Distribution,
        expected_relative_path: str,
    ) -> None:
        module_spec = find_spec(module_name)
        origin = module_spec.origin if module_spec is not None else None
        expected = cast(
            Path,
            selected_distribution.locate_file(expected_relative_path),
        ).resolve()
        if not isinstance(origin, str) or Path(origin).resolve() != expected:
            raise RuntimeError("selected simulator module origin could not be verified")

    def _next_operation_ref(self, operation: str) -> str:
        self._operation_count += 1
        return f"driver.{operation}.{self._operation_count}"


__all__ = [
    "CyberBattleSimDriver",
    "CyberBattleSimDriverProtocol",
    "DriverCleanupReport",
    "DriverEvaluation",
    "DriverResetReport",
    "DriverStep",
]
