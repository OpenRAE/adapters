"""Explicit logical-clock transition dispatch over the RAES reference runtime."""

from __future__ import annotations

from raes_contracts.runtime_state import (  # type: ignore[import-untyped]
    ApplyResult,
    RuntimeSnapshot,
)
from raes_runtime.time_coordinator import (  # type: ignore[import-untyped]
    ClockTransitionKind,
    ReferenceTimeRuntime,
)


def _reject_unused_arguments(
    *,
    ticks: int | None,
    tick: int | None,
    microstep: int,
) -> None:
    """Reject coordinates for transitions whose RAES operation has none."""

    if ticks is not None or tick is not None or microstep != 0:
        raise ValueError("This logical-clock transition does not accept coordinate arguments.")


def _apply_advance(
    runtime: ReferenceTimeRuntime,
    snapshot: RuntimeSnapshot,
    clock_address: str,
    ticks: int | None,
    tick: int | None,
    microstep: int,
) -> ApplyResult:
    """Validate and apply a relative logical-clock advance."""

    if ticks is None:
        raise ValueError("Advance requires explicit ticks.")
    if tick is not None:
        raise ValueError("Advance accepts ticks, not an absolute tick.")
    return runtime.advance(clock_address, ticks, microstep, snapshot)


def _apply_jump(
    runtime: ReferenceTimeRuntime,
    snapshot: RuntimeSnapshot,
    clock_address: str,
    ticks: int | None,
    tick: int | None,
    microstep: int,
) -> ApplyResult:
    """Validate and apply an absolute logical-clock jump."""

    if tick is None:
        raise ValueError("Jump requires an explicit absolute tick.")
    if ticks is not None:
        raise ValueError("Jump accepts an absolute tick, not ticks.")
    return runtime.jump(clock_address, tick, microstep, snapshot)


def _apply_reset(
    runtime: ReferenceTimeRuntime,
    snapshot: RuntimeSnapshot,
    clock_address: str,
    transition: ClockTransitionKind,
) -> ApplyResult:
    """Apply reset or replay after rejecting irrelevant coordinates."""

    return runtime.reset(
        clock_address,
        transition == ClockTransitionKind.REPLAY,
        snapshot,
    )


def apply_logical_clock_transition(
    runtime: ReferenceTimeRuntime,
    snapshot: RuntimeSnapshot,
    *,
    transition: ClockTransitionKind,
    clock_address: str,
    ticks: int | None = None,
    tick: int | None = None,
    microstep: int = 0,
) -> ApplyResult:
    """Apply one caller-selected transition and return the RAES ``ApplyResult``.

    There is intentionally no native-event inference here. An adapter must map
    its own event to an exact RAES transition and supply explicit coordinates;
    a simulator call is never assumed to equal one logical tick.
    """

    if transition == ClockTransitionKind.INITIALIZE:
        raise ValueError(
            "Initialize logical clocks through ReferenceTimeRuntime.initialize "
            "with a published declaration."
        )
    if transition == ClockTransitionKind.ADVANCE:
        result = _apply_advance(runtime, snapshot, clock_address, ticks, tick, microstep)
    elif transition == ClockTransitionKind.PAUSE:
        _reject_unused_arguments(ticks=ticks, tick=tick, microstep=microstep)
        result = runtime.pause(clock_address, snapshot)
    elif transition == ClockTransitionKind.RESUME:
        _reject_unused_arguments(ticks=ticks, tick=tick, microstep=microstep)
        result = runtime.resume(clock_address, snapshot)
    elif transition == ClockTransitionKind.JUMP:
        result = _apply_jump(runtime, snapshot, clock_address, ticks, tick, microstep)
    elif transition in {ClockTransitionKind.RESET, ClockTransitionKind.REPLAY}:
        _reject_unused_arguments(ticks=ticks, tick=tick, microstep=microstep)
        result = _apply_reset(runtime, snapshot, clock_address, transition)
    else:
        raise ValueError("Unsupported logical-clock transition.")
    return result


__all__ = ["apply_logical_clock_transition"]
