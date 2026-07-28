"""Shared plumbing for RAES simulator adapters (always installed).

Convenience library for simulator drivers: target factories, clock/seed
controls, action/observation/reward projector bases, redaction helpers, and
conformance-probe wrappers land under REP-004. Per RAES ADR-069 §4 it consumes
RAES published contracts and MUST NOT define a new semantic model, schema
registry, backend protocol, diagnostic envelope, exception hierarchy,
conformance-profile table, fixture corpus, concept catalog, or policy gate.
"""

from __future__ import annotations

__all__: list[str] = []
