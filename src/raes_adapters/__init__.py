"""RAES simulator adapters.

A single distribution, ``raes-adapters``, that ships shared adapter plumbing
(:mod:`raes_adapters.base`), one importable module per simulator backend
(:mod:`raes_adapters.cyborg`, ...), and backend-local qualification evidence.
Simulator install surfaces are optional extras, so ``pip install
raes-adapters`` gives the base plumbing and ``pip install
raes-adapters[cyborg]`` selects the CybORG adapter surface. Maintainer selection
admits a simulator; qualification limitations bound the claims made for that
surface and may require native dependencies to be installed separately.

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
except PackageNotFoundError:
    # Source tree without installed metadata; coverage excludes this fallback via
    # [tool.coverage.report] exclude_also in pyproject.toml.
    __version__ = "0.0.0"
