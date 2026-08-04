"""Portable orchestration state for PrimAITE episodes.

The orchestrator owns only the workflow lifecycle. It never advances the source
(the participant runtime owns the single aggregate ``env.step``), and it never
fabricates orchestration operations: an empty compiled-SDL orchestration is a
valid no-op. The neutral :class:`GymEpisodeOrchestrator` already realizes exactly
that lifecycle, so PrimAITE parameterizes it by name rather than restating it.
"""

from __future__ import annotations

from raes_adapters._gym_backend.orchestrator import GymEpisodeOrchestrator


class PrimaiteOrchestrator(GymEpisodeOrchestrator):
    """Own workflow lifecycle only; the participant runtime owns source steps."""

    def __init__(self) -> None:
        super().__init__("primaite")


__all__ = ["PrimaiteOrchestrator"]
