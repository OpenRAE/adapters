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
    if ticks is not None or tick is not None or microstep != 0:
        raise ValueError("This logical-clock transition does not accept coordinate arguments.")


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
        if ticks is None:
            raise ValueError("Advance requires explicit ticks.")
        if tick is not None:
            raise ValueError("Advance accepts ticks, not an absolute tick.")
        return runtime.advance(clock_address, ticks, microstep, snapshot)
    if transition == ClockTransitionKind.PAUSE:
        _reject_unused_arguments(ticks=ticks, tick=tick, microstep=microstep)
        return runtime.pause(clock_address, snapshot)
    if transition == ClockTransitionKind.RESUME:
        _reject_unused_arguments(ticks=ticks, tick=tick, microstep=microstep)
        return runtime.resume(clock_address, snapshot)
    if transition == ClockTransitionKind.JUMP:
        if tick is None:
            raise ValueError("Jump requires an explicit absolute tick.")
        if ticks is not None:
            raise ValueError("Jump accepts an absolute tick, not ticks.")
        return runtime.jump(clock_address, tick, microstep, snapshot)
    if transition in {ClockTransitionKind.RESET, ClockTransitionKind.REPLAY}:
        _reject_unused_arguments(ticks=ticks, tick=tick, microstep=microstep)
        return runtime.reset(
            clock_address,
            transition == ClockTransitionKind.REPLAY,
            snapshot,
        )
    raise ValueError("Unsupported logical-clock transition.")


__all__ = ["apply_logical_clock_transition"]
