"""Diagnostic helpers for the CyberBattleSim backend boundary."""

from __future__ import annotations


def _escape_pointer_token(token: str) -> str:
    """Escape one JSON Pointer token."""

    return token.replace("~", "~0").replace("/", "~1")


def diagnostic_address(address: str) -> str:
    """Project a dotted portable address into a RAES DiagnosticModel address.

    RAES diagnostics use JSON Pointer syntax. The backend's runtime addresses
    are dotted RAES artifact addresses, so each dot-delimited segment becomes a
    pointer token without changing the underlying published address identity.
    """

    if address.startswith("/"):
        return address
    tokens = [token for token in address.replace(".", "/").split("/") if token]
    if not tokens:
        return "/cyberbattlesim"
    return "/" + "/".join(_escape_pointer_token(token) for token in tokens)


__all__ = ["diagnostic_address"]
