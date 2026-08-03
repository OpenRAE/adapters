"""NASim provisioner over the selected static-benchmark profile."""

from __future__ import annotations

from raes_adapters._gym_backend.provisioner import GymProvisioner

from .driver import NasimDriverProtocol


class NasimProvisioner(GymProvisioner):
    """Realize the selected static tiny benchmark while preserving intent."""

    def __init__(self, driver: NasimDriverProtocol) -> None:
        super().__init__(driver, "nasim")


__all__ = ["NasimProvisioner"]
