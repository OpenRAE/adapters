"""Backend-neutral RAES diagnostic-address projection.

RAES diagnostics use JSON Pointer syntax while adapter runtime addresses are
dotted RAES artifact addresses. This module is the single shared projection so
each backend does not carry its own copy (see the NASim backend guardrails
"Projection and failure hygiene" row: do not add a third copied
diagnostic-address helper). Backends supply their own bounded ``fallback`` for
an otherwise-empty address; nothing here is simulator-specific.
"""

from __future__ import annotations


def escape_pointer_token(token: str) -> str:
    """Escape one JSON Pointer token."""

    return token.replace("~", "~0").replace("/", "~1")


def diagnostic_address(address: str, *, fallback: str) -> str:
    """Project a dotted portable address into a RAES DiagnosticModel address.

    Each dot-delimited segment becomes a pointer token without changing the
    underlying published address identity. An address that is already a JSON
    Pointer is returned unchanged; an address with no usable tokens becomes the
    caller's bounded ``fallback``.
    """

    if address.startswith("/"):
        return address
    tokens = [token for token in address.replace(".", "/").split("/") if token]
    if not tokens:
        return fallback
    return "/" + "/".join(escape_pointer_token(token) for token in tokens)


__all__ = ["diagnostic_address", "escape_pointer_token"]
