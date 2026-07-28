"""RAES simulator adapters.

A single distribution, ``raes-adapters``, that ships shared adapter plumbing
(:mod:`raes_adapters.base`) plus one importable module per simulator backend
(:mod:`raes_adapters.cyborg`, ...). Simulator-specific dependencies are optional
extras, so ``pip install raes-adapters`` gives the base plumbing and
``pip install raes-adapters[cyborg]`` adds the CybORG backend.

Packaging boundary: RAES owns the *contracts* an adapter must honor; how this
repository structures its packages, locks, and releases is a local decision
(RAES ADR-069 as amended — see RAESystem/rae#949 — and
``docs/decisions/adrs/adr-003-single-distribution-and-trusted-publishing``).
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

__all__ = ["__version__"]

try:
    __version__ = version("raes-adapters")
except PackageNotFoundError:  # pragma: no cover - source tree without installed metadata
    __version__ = "0.0.0"
