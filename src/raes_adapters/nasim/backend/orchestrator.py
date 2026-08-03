"""Portable orchestration state for NASim episodes."""

from __future__ import annotations

from raes_adapters._gym_backend.orchestrator import GymEpisodeOrchestrator


class NasimOrchestrator(GymEpisodeOrchestrator):
    """Own workflow lifecycle only; the participant runtime owns source steps."""

    def __init__(self) -> None:
        super().__init__("nasim")


__all__ = ["NasimOrchestrator"]
