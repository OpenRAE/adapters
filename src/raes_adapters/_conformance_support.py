"""Backend-neutral inventory of unresolved manifest capability claims.

Traversal is mechanical and RAES-payload-shaped. It deliberately produces no
positive evidence join: a broad conformance result, source-ledger disposition,
or adapter probe cannot certify every affirmative manifest leaf.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import cast

from raes_adapters._diagnostics import escape_pointer_token

_NON_CAPABILITY_KEYS = frozenset({"constraints", "name"})


def affirmative_capability_pointers(payload: Mapping[str, object]) -> tuple[str, ...]:
    """Return JSON pointers for manifest capability values that declare support."""

    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, Mapping):
        return ()
    pointers: list[str] = []
    for name, value in sorted(capabilities.items(), key=lambda item: str(item[0])):
        if not _is_affirmative_capability_value(value):
            continue
        surface = f"/capabilities/{escape_pointer_token(str(name))}"
        if isinstance(value, Mapping):
            nested = tuple(
                _iter_affirmative_capability_pointers(
                    cast(Mapping[object, object], value),
                    surface,
                )
            )
            pointers.extend(nested or (surface,))
        else:
            pointers.append(surface)
    return tuple(pointers)


def manifest_capability_gaps(payload: Mapping[str, object]) -> tuple[str, ...]:
    """Return every affirmative manifest leaf as unresolved inventory."""

    return affirmative_capability_pointers(payload)


def _iter_affirmative_capability_pointers(
    value: Mapping[object, object],
    base_pointer: str,
) -> Iterable[str]:
    """Yield nested affirmative capability pointers below a manifest surface."""

    for key, child in sorted(value.items(), key=lambda item: str(item[0])):
        if key in _NON_CAPABILITY_KEYS or not _is_affirmative_capability_value(child):
            continue
        pointer = f"{base_pointer}/{escape_pointer_token(str(key))}"
        if isinstance(child, Mapping):
            nested = tuple(
                _iter_affirmative_capability_pointers(
                    cast(Mapping[object, object], child),
                    pointer,
                )
            )
            yield from nested or (pointer,)
        else:
            yield pointer


def _is_affirmative_capability_value(value: object) -> bool:
    """Return whether a manifest capability value makes an affirmative claim."""

    if value in (None, False):
        affirmative = False
    elif value is True:
        affirmative = True
    elif isinstance(value, str | int | float):
        affirmative = bool(value)
    elif isinstance(value, list | tuple | set | frozenset):
        affirmative = any(_is_affirmative_capability_value(item) for item in value)
    elif isinstance(value, Mapping):
        affirmative = any(
            _is_affirmative_capability_value(child)
            for key, child in cast(Mapping[object, object], value).items()
            if key not in _NON_CAPABILITY_KEYS
        )
    else:
        affirmative = False
    return affirmative


__all__ = [
    "affirmative_capability_pointers",
    "manifest_capability_gaps",
]
