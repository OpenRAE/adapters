"""Shared plumbing for RAES simulator adapters.

This package is a *convenience library* for simulator drivers. Per RAES ADR-069
§4 it consumes RAES published contracts and MUST NOT define a new semantic
model, schema registry, backend protocol, diagnostic envelope, exception
hierarchy, conformance-profile table, fixture corpus, concept catalog, or
policy gate.

REP-002 stands up this package as a buildable skeleton; its helpers (target
factories, clock/seed controls, action/observation/reward projector bases,
redaction helpers, conformance-probe wrappers) are implemented under REP-004.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.0.0"
