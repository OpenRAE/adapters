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
the selected source identity through the shared ``_source_admission`` plumbing
and then **fails closed** rather than pretending to run or mutating global state.
The injected ``FakeDriver`` in the test suite proves every portable mechanic; a
real live run awaits the worker boundary and bounded 3.12 qualification evidence.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from threading import RLock
from typing import NoReturn, Protocol, cast

from raes_adapters import _source_admission
from raes_adapters.primaite import load_qualification

_QUALIFICATION_INVALID = _source_admission.QUALIFICATION_INVALID
_RUNTIME_UNQUALIFIED = "selected simulator runtime is not the qualified runtime"
_INPROCESS_UNSUPPORTED = (
    "the selected PrimAITE live target does not run in-process: it writes to platform "
    "application directories on import and exposes no explicit path binding, so safe "
    "isolation requires a reviewed worker-process boundary (redirect env set at child "
    "launch) that is not implemented, and the qualified runtime is CPython 3.11"
)
_SOURCE_PACKAGE = "primaite"


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

    def reset(self, seed: int | None, /) -> DriverResetReport: ...

    def step(self, action_contract: str) -> DriverStep: ...

    def evaluate(self) -> DriverEvaluation: ...

    def close(self) -> DriverCleanupReport: ...

    def verify_closed(self) -> bool: ...


class PrimaiteDriver(object):
    """Source-verifying, fail-closed live driver for the selected profile.

    It verifies the selected PrimAITE distribution version and the complete
    runtime artifact identity through the shared ``_source_admission`` plumbing,
    then refuses in-process construction: a real run needs the worker-process
    isolation boundary and 3.12 qualification described in the module docstring.
    It never imports PrimAITE (which would write to the platform home) and never
    mutates process-global ``HOME`` or the working directory.
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
            selected_distribution = _source_admission.resolve_selected_distribution(
                source["package"],
                source["version"],
            )
            _source_admission.verify_runtime_artifacts(
                qualification,
                selected_distribution,
                expected_names=frozenset({_SOURCE_PACKAGE}),
                primary_name=_SOURCE_PACKAGE,
            )
            raise RuntimeError(_INPROCESS_UNSUPPORTED)

    def reset(self, _seed: int | None) -> DriverResetReport:
        """Refuse an in-process reset after verifying the selected identity."""

        self.construct()

    @staticmethod
    def step(action_contract: str) -> DriverStep:
        """Refuse an in-process step; the live target never constructs."""

        raise RuntimeError(_INPROCESS_UNSUPPORTED)

    @staticmethod
    def evaluate() -> DriverEvaluation:
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

    @staticmethod
    def _selected_source() -> tuple[dict[str, object], dict[str, str]]:
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
