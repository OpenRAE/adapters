"""Source-backed terminal-cause classification for the pinned public protocol."""

from __future__ import annotations

import math

WINNING_REWARD = 5000.0
LOSING_REWARD = 0.0
DEFENDER_SLA_FLOOR = 0.8


def classify_terminal_cause(
    *,
    last_reward: float | None,
    network_availability: float | None,
    step_count: int,
    maximum_steps: int,
    terminated: bool,
    truncated: bool,
    defender_sla_floor: float = DEFENDER_SLA_FLOOR,
) -> str | None:
    """Classify one terminal fact using the pinned evaluator's public signals.

    CyberBattleSim uses the same winning reward for attacker ownership and a
    broken defender SLA, so availability is required to distinguish them.
    Unknown source terminal rewards remain generic rather than being guessed.
    """

    if terminated:
        if last_reward is not None and math.isclose(last_reward, WINNING_REWARD):
            if network_availability is None:
                return "source-terminated"
            return (
                "defender-sla"
                if network_availability < defender_sla_floor
                else "attacker-ownership"
            )
        if last_reward is not None and math.isclose(last_reward, LOSING_REWARD):
            return "defender-eviction"
        return "source-terminated"
    if truncated:
        return "source-truncated"
    if step_count >= maximum_steps:
        return "evaluator-cutoff"
    return None


__all__ = [
    "DEFENDER_SLA_FLOOR",
    "LOSING_REWARD",
    "WINNING_REWARD",
    "classify_terminal_cause",
]
