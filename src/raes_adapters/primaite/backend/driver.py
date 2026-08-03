"""Private PrimAITE source-identity boundary and fail-closed live target.

The live target does **not** run PrimAITE in-process. PrimAITE writes session,
log, and application directories under the platform home via ``platformdirs`` on
import, and exposes no explicit per-instance path binding. The only safe way to
confine those writes is a reviewed worker-process boundary that sets the
redirect environment (``XDG_DATA_HOME``/``XDG_CACHE_HOME``/``HOME``) in the
child's launch environment before import — the same isolation shape Gymnasium's
own ``AsyncVectorEnv`` uses — never by mutating this process's global ``HOME`` or
current working directory (both are process-wide and not thread-safe, so a
concurrent request or an exception before restore would break tenant isolation).

That worker boundary is not implemented here, and the qualified runtime is
CPython 3.11 while this distribution requires 3.12+. So the live driver verifies
the selected source identity and then **fails closed** rather than pretending to
run or mutating global state. The injected ``FakeDriver`` in the test suite
proves every portable mechanic; a real live run awaits the worker boundary and
bounded 3.12 qualification evidence.
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from importlib.metadata import Distribution, PackageNotFoundError, distribution
from pathlib import Path
from threading import RLock
from typing import NoReturn, Protocol, cast

from raes_adapters.base.source_identity import (
    installed_root_paths,
    installed_tree_digest,
    is_sha256,
    reject_unverifiable_install,
)
from raes_adapters.primaite import load_qualification

_QUALIFICATION_INVALID = "selected simulator qualification is invalid"
_SOURCE_IDENTITY_INVALID = "selected simulator source identity could not be verified"
_ARTIFACT_IDENTITY_INVALID = "selected simulator runtime artifact could not be verified"
_RUNTIME_UNQUALIFIED = "selected simulator runtime is not the qualified runtime"
_SOURCE_NOT_INSTALLED = "selected simulator source is not installed"
_SOURCE_VERSION_MISMATCH = "installed simulator version does not match the selected source"
_INPROCESS_UNSUPPORTED = (
    "the selected PrimAITE live target does not run in-process: it writes to platform "
    "application directories on import and exposes no explicit path binding, so safe "
    "isolation requires a reviewed worker-process boundary (redirect env set at child "
    "launch) that is not implemented, and the qualified runtime is CPython 3.11"
)

# Critical selected-source files whose exact bytes are re-verified before the
# fail-closed refusal, beyond the complete-tree digest.
_CRITICAL_SOURCE_PATHS = (
    "primaite/__init__.py",
    "primaite/session/environment.py",
    "primaite/game/game.py",
)
_SOURCE_PACKAGE = "primaite"
_SOURCE_ROOT = "primaite"


@dataclass(frozen=True)
class DriverResetReport(object):
    """Sanitized reset and stochastic-control dispositions.

    The four PrimAITE stochastic sources are reported in distinct dispositions: a
    seam that could be applied, one broken by an upstream defect, one absent on
    the qualified route, and one reachable but uncontrolled. A non-empty
    ``applied_streams`` never implies deterministic replay.
    """

    operation_ref: str
    applied_streams: tuple[str, ...] = ()
    broken_streams: tuple[str, ...] = ()
    absent_streams: tuple[str, ...] = ()
    unbound_streams: tuple[str, ...] = ()


@dataclass(frozen=True)
class DriverStep(object):
    """Sanitized facts from at most one aggregate source transition.

    ``representable`` is false when no qualified deterministic mapping selects a
    single native operation for the admitted contract; ``source_transition`` is
    then false and no source step ran.
    """

    operation_ref: str
    step_number: int
    representable: bool
    source_transition: bool
    processed: bool
    terminated: bool
    truncated: bool
    terminal_cause: str | None
    rejection_reason: str | None = None


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
    """Sanitized close, workspace-removal, and verification facts."""

    operation_ref: str
    closed: bool
    verified: bool
    already_closed: bool
    workspace_removed: bool


class PrimaiteDriverProtocol(Protocol):
    """Injectable boundary implemented by the live and test drivers."""

    def construct(self) -> None: ...

    def reset(self, seed: int | None) -> DriverResetReport: ...

    def step(self, action_contract: str) -> DriverStep: ...

    def evaluate(self) -> DriverEvaluation: ...

    def close(self) -> DriverCleanupReport: ...

    def verify_closed(self) -> bool: ...


class PrimaiteDriver(object):
    """Source-verifying, fail-closed live driver for the selected profile.

    It verifies the selected PrimAITE distribution version, complete import-root
    tree, critical source-file bytes, and runtime artifact identity, then refuses
    in-process construction: a real run needs the worker-process isolation
    boundary and 3.12 qualification described in the module docstring. It never
    imports PrimAITE (which would write to the platform home) and never mutates
    process-global ``HOME`` or the working directory.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._operation_count = 0
        self._closed = True

    def construct(self) -> NoReturn:
        """Verify the selected source identity, then fail closed in-process."""

        with self._lock:
            qualification, source = self._selected_source()
            self._verify_qualified_runtime(qualification)
            selected_distribution = self._require_distribution(source)
            self._verify_selected_source(qualification, selected_distribution)
            self._verify_runtime_artifact(qualification, selected_distribution)
            raise RuntimeError(_INPROCESS_UNSUPPORTED)

    def reset(self, seed: int | None) -> DriverResetReport:
        """Refuse an in-process reset after verifying the selected identity."""

        self.construct()

    def step(self, action_contract: str) -> DriverStep:
        """Refuse an in-process step; the live target never constructs."""

        raise RuntimeError(_INPROCESS_UNSUPPORTED)

    def evaluate(self) -> DriverEvaluation:
        """Refuse an in-process evaluation; the live target never constructs."""

        raise RuntimeError(_INPROCESS_UNSUPPORTED)

    def close(self) -> DriverCleanupReport:
        """Return a bounded no-op cleanup receipt; nothing was opened in-process."""

        with self._lock:
            already_closed = self._closed
            self._closed = True
            return DriverCleanupReport(
                operation_ref=self._next_operation_ref("close"),
                closed=True,
                verified=True,
                already_closed=already_closed,
                workspace_removed=False,
            )

    def verify_closed(self) -> bool:
        """The in-process live driver never holds an open native resource."""

        with self._lock:
            return self._closed

    # -- source identity ---------------------------------------------------- #
    @staticmethod
    def _selected_source() -> tuple[dict[str, object], dict[str, object]]:
        """Load and normalize the maintainer-selected native source identity."""

        qualification = cast(dict[str, object], load_qualification())
        source = qualification.get("source")
        if not isinstance(source, dict):
            raise RuntimeError(_QUALIFICATION_INVALID)
        package = source.get("package")
        version = source.get("version")
        if not isinstance(package, str) or not isinstance(version, str):
            raise RuntimeError(_QUALIFICATION_INVALID)
        return qualification, {"package": package, "version": version}

    @staticmethod
    def _verify_qualified_runtime(qualification: dict[str, object]) -> None:
        """Reject a runtime other than the qualified CPython interpreter.

        The selected source proof is CPython 3.11 only; a different runtime needs
        its own bounded qualification evidence before any live claim.
        """

        runtime = qualification.get("runtime")
        recorded = runtime.get("python") if isinstance(runtime, dict) else None
        if not isinstance(recorded, str):
            raise RuntimeError(_QUALIFICATION_INVALID)
        parts = recorded.split(".")
        if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
            raise RuntimeError(_QUALIFICATION_INVALID)
        qualified = (int(parts[0]), int(parts[1]))
        if sys.version_info[:2] != qualified:
            raise RuntimeError(_RUNTIME_UNQUALIFIED)

    @staticmethod
    def _require_distribution(source: dict[str, object]) -> Distribution:
        """Resolve the installed selected distribution at the qualified version."""

        try:
            selected_distribution = distribution(str(source["package"]))
        except PackageNotFoundError as exc:
            raise RuntimeError(_SOURCE_NOT_INSTALLED) from exc
        if selected_distribution.version != source["version"]:
            raise RuntimeError(_SOURCE_VERSION_MISMATCH)
        return selected_distribution

    @staticmethod
    def _verify_selected_source(
        qualification: dict[str, object],
        selected_distribution: Distribution,
    ) -> None:
        """Verify the complete import-root tree and critical source-file bytes."""

        tree = qualification.get("runtime_source_tree")
        if not isinstance(tree, dict):
            raise RuntimeError(_SOURCE_IDENTITY_INVALID)
        expected_digest = tree.get("sha256")
        expected_count = tree.get("file_count")
        if not is_sha256(expected_digest) or not isinstance(expected_count, int):
            raise RuntimeError(_SOURCE_IDENTITY_INVALID)
        paths = installed_root_paths(selected_distribution, _SOURCE_ROOT, _SOURCE_IDENTITY_INVALID)
        if len(paths) != expected_count:
            raise RuntimeError(_SOURCE_IDENTITY_INVALID)
        package_root = cast(Path, selected_distribution.locate_file(_SOURCE_ROOT)).resolve()
        observed = installed_tree_digest(
            selected_distribution,
            paths,
            _SOURCE_IDENTITY_INVALID,
            package_root=package_root,
        )
        if observed != expected_digest:
            raise RuntimeError(_SOURCE_IDENTITY_INVALID)
        PrimaiteDriver._verify_critical_source_files(qualification, selected_distribution)

    @staticmethod
    def _verify_critical_source_files(
        qualification: dict[str, object],
        selected_distribution: Distribution,
    ) -> None:
        """Re-verify the exact bytes of the critical selected-source files."""

        source_files = qualification.get("source_files")
        if not isinstance(source_files, list):
            raise RuntimeError(_SOURCE_IDENTITY_INVALID)
        expected: dict[str, str] = {}
        for entry in source_files:
            if not isinstance(entry, dict):
                continue
            path = entry.get("path")
            digest = entry.get("sha256")
            if isinstance(path, str) and isinstance(digest, str):
                # source_files paths are recorded under src/; the installed tree
                # roots at ``primaite/``.
                expected[path.removeprefix("src/")] = digest
        try:
            for source_path in _CRITICAL_SOURCE_PATHS:
                installed = cast(Path, selected_distribution.locate_file(source_path))
                observed = hashlib.sha256(installed.read_bytes()).hexdigest()
                if observed != expected[source_path]:
                    raise RuntimeError(_SOURCE_IDENTITY_INVALID)
        except (KeyError, OSError) as exc:
            raise RuntimeError(_SOURCE_IDENTITY_INVALID) from exc

    @staticmethod
    def _verify_runtime_artifact(
        qualification: dict[str, object],
        selected_distribution: Distribution,
    ) -> None:
        """Verify the single selected runtime artifact (PrimAITE root only).

        Gymnasium, NumPy, and setuptools are observed dependency evidence, not
        separately attested runtime artifacts, so only the PrimAITE artifact and
        its import roots are re-verified here.
        """

        artifacts = qualification.get("runtime_artifacts")
        if not isinstance(artifacts, list) or len(artifacts) != 1:
            raise RuntimeError(_ARTIFACT_IDENTITY_INVALID)
        record = artifacts[0]
        if not isinstance(record, dict) or record.get("name") != _SOURCE_PACKAGE:
            raise RuntimeError(_ARTIFACT_IDENTITY_INVALID)
        artifact = record.get("artifact")
        if not isinstance(artifact, dict) or not is_sha256(artifact.get("sha256")):
            raise RuntimeError(_ARTIFACT_IDENTITY_INVALID)
        require_archive = artifact.get("require_direct_archive_sha256")
        if not isinstance(require_archive, bool):
            raise RuntimeError(_ARTIFACT_IDENTITY_INVALID)
        reject_unverifiable_install(
            selected_distribution,
            _ARTIFACT_IDENTITY_INVALID,
            expected_archive_sha256=cast(str, artifact.get("sha256")),
            require_archive_digest=require_archive,
        )
        PrimaiteDriver._verify_artifact_roots(record, selected_distribution)

    @staticmethod
    def _verify_artifact_roots(
        record: dict[object, object],
        selected_distribution: Distribution,
    ) -> None:
        """Verify every declared import-root tree for the selected artifact."""

        roots = record.get("roots")
        if not isinstance(roots, list) or not roots:
            raise RuntimeError(_ARTIFACT_IDENTITY_INVALID)
        for root in roots:
            if not isinstance(root, dict):
                raise RuntimeError(_ARTIFACT_IDENTITY_INVALID)
            root_path = root.get("path")
            expected_count = root.get("file_count")
            expected_digest = root.get("sha256")
            if not isinstance(root_path, str) or not isinstance(expected_count, int):
                raise RuntimeError(_ARTIFACT_IDENTITY_INVALID)
            if not is_sha256(expected_digest):
                raise RuntimeError(_ARTIFACT_IDENTITY_INVALID)
            paths = installed_root_paths(
                selected_distribution, root_path, _ARTIFACT_IDENTITY_INVALID
            )
            if len(paths) != expected_count:
                raise RuntimeError(_ARTIFACT_IDENTITY_INVALID)
            observed = installed_tree_digest(
                selected_distribution, paths, _ARTIFACT_IDENTITY_INVALID
            )
            if observed != expected_digest:
                raise RuntimeError(_ARTIFACT_IDENTITY_INVALID)

    def _next_operation_ref(self, operation: str) -> str:
        self._operation_count += 1
        return f"driver.{operation}.{self._operation_count}"


__all__ = [
    "DriverCleanupReport",
    "DriverEvaluation",
    "DriverResetReport",
    "DriverStep",
    "PrimaiteDriver",
    "PrimaiteDriverProtocol",
]
