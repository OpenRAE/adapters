"""Portable orchestration state for CyberBattleSim episodes."""

from __future__ import annotations

from raes_adapters._gym_backend.orchestrator import GymEpisodeOrchestrator


class CyberBattleSimOrchestrator(GymEpisodeOrchestrator):
    """Own workflow lifecycle only; participant runtime owns source steps."""

    def __init__(self) -> None:
        super().__init__("cyberbattlesim")


__all__ = ["CyberBattleSimOrchestrator"]
