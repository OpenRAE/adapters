"""Diagnostic helpers for the NASim backend boundary."""

from __future__ import annotations

from raes_adapters._diagnostics import diagnostic_address as _shared_diagnostic_address

_FALLBACK = "/nasim"


def diagnostic_address(address: str) -> str:
    """Project a dotted NASim address into a RAES pointer address."""

    return _shared_diagnostic_address(address, fallback=_FALLBACK)


__all__ = ["diagnostic_address"]
