"""Diagnostic address helpers for the CybORG backend boundary."""

from __future__ import annotations


def _escape_pointer_token(token: str) -> str:
    """Escape one JSON Pointer token."""

    return token.replace("~", "~0").replace("/", "~1")


def diagnostic_address(address: str) -> str:
    """Project a portable artifact address into RAES JSON Pointer syntax."""

    if address.startswith("/"):
        return address
    tokens = [token for token in address.replace(".", "/").split("/") if token]
    if not tokens:
        return "/cyborg"
    return "/" + "/".join(_escape_pointer_token(token) for token in tokens)


__all__ = ["diagnostic_address"]
