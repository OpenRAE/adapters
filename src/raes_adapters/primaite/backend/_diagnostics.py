"""Diagnostic helpers for the PrimAITE backend boundary."""

from __future__ import annotations

from raes_adapters.base.manifest_evidence import escape_pointer_token


def diagnostic_address(address: str) -> str:
    """Project a dotted portable address into a RAES DiagnosticModel address.

    RAES diagnostics use JSON Pointer syntax. The backend's runtime addresses are
    dotted RAES artifact addresses, so each dot-delimited segment becomes a
    pointer token without changing the underlying published address identity.
    """

    if address.startswith("/"):
        return address
    tokens = [token for token in address.replace(".", "/").split("/") if token]
    if not tokens:
        return "/primaite"
    return "/" + "/".join(escape_pointer_token(token) for token in tokens)


__all__ = ["diagnostic_address"]
