"""Default-deny handling for native values and bounded safe context labels."""

from __future__ import annotations

import re

REDACTED = "[redacted]"
_MAX_LABEL_LENGTH = 128
_SAFE_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_WINDOWS_PATH = re.compile(r"^[A-Za-z]:[\\/]")
_HIGH_ENTROPY_HEX = re.compile(r"[0-9A-Fa-f]{32,}")
_SENSITIVE_MARKERS = (
    "api-key",
    "api_key",
    "authorization",
    "bearer",
    "credential",
    "password",
    "private-key",
    "secret",
    "token",
    "traceback",
)
_SAFE_EXCEPTION_TYPES = frozenset({TimeoutError})


def redact_native_value(value: object) -> str:
    """Return a fixed sentinel without inspecting or rendering ``value``.

    Only exact, hard-coded safe exception classes may contribute their type
    name. Subclasses are denied so backend code cannot smuggle a crafted class
    name through the allowlist.
    """

    value_type = type(value)
    if value_type in _SAFE_EXCEPTION_TYPES:
        return value_type.__name__
    return REDACTED


def bounded_context_label(text: str, *, max_length: int = _MAX_LABEL_LENGTH) -> str:
    """Admit one intentionally supplied, non-sensitive diagnostic label.

    This is not a general string scrubber. Exact strings must satisfy a small
    ASCII grammar and defense-in-depth path, secret-marker, traceback, control,
    and high-entropy checks. Everything else becomes the fixed sentinel.
    """

    if not 1 <= max_length <= _MAX_LABEL_LENGTH:
        raise ValueError("max_length must be between 1 and 128.")
    if type(text) is not str:
        label = REDACTED
    else:
        lowered = text.lower()
        safe = (
            bool(text)
            and len(text) <= max_length
            and not text.startswith(("/", "~"))
            and _WINDOWS_PATH.match(text) is None
            and not any(marker in lowered for marker in _SENSITIVE_MARKERS)
            and _HIGH_ENTROPY_HEX.search(text) is None
            and _SAFE_LABEL.fullmatch(text) is not None
        )
        label = text if safe else REDACTED
    return label


__all__ = ["bounded_context_label", "redact_native_value"]
