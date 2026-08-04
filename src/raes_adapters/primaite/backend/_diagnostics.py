"""Diagnostic helpers for the PrimAITE backend boundary."""

from __future__ import annotations

from raes_adapters._diagnostics import diagnostic_address as _shared_diagnostic_address

_FALLBACK = "/primaite"


def diagnostic_address(address: str) -> str:
    """Project a dotted PrimAITE address into a RAES pointer address."""

    return _shared_diagnostic_address(address, fallback=_FALLBACK)


__all__ = ["diagnostic_address"]
