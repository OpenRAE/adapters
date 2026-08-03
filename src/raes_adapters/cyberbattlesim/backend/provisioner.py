"""CyberBattleSim provisioner over the selected source profile."""

from __future__ import annotations

from raes_adapters._gym_backend.provisioner import GymProvisioner

from .driver import CyberBattleSimDriverProtocol


class CyberBattleSimProvisioner(GymProvisioner):
    """Realize the selected generated chain while preserving portable intent."""

    def __init__(self, driver: CyberBattleSimDriverProtocol) -> None:
        super().__init__(driver, "cyberbattlesim")


__all__ = ["CyberBattleSimProvisioner"]
