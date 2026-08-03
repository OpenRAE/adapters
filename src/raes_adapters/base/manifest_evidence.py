"""Mechanical manifest capability-evidence helpers shared across backends.

A backend declares affirmative capability surfaces in its RAES manifest and then
shows which of them are backed by an executable conformance probe. Walking the
manifest payload into JSON Pointers, deciding whether a capability value is
affirmative, and intersecting the declared surfaces with the evidence a probe
produced is pure mechanical plumbing with no simulator semantics. It lives here
as one copy; each backend supplies its own capability→evidence requirement map,
its own passed-probe evidence resolution, and its own default manifest factory.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import cast

from raes_backend_protocols.backend_manifest import (  # type: ignore[import-untyped]
    BackendManifest,
)
from raes_backend_protocols.manifest import (  # type: ignore[import-untyped]
    backend_manifest_payload,
)
from raes_conformance.conformance import (  # type: ignore[import-untyped]
    BackendConformanceReport,
)
from raes_conformance.conformance.report import (  # type: ignore[import-untyped]
    backend_conformance_report_payload,
)

_NON_CAPABILITY_KEYS = frozenset({"constraints", "name"})


def escape_pointer_token(token: str) -> str:
    """Escape one token for inclusion in a JSON Pointer."""

    return token.replace("~", "~0").replace("/", "~1")


def backend_conformance_payload(report: BackendConformanceReport) -> dict[str, object]:
    """Serialize a canonical conformance report through the published projector."""

    return cast(dict[str, object], backend_conformance_report_payload(report))


def manifest_payload(
    manifest: BackendManifest | None,
    payload: Mapping[str, object] | None,
    default_factory: Callable[[], BackendManifest],
) -> Mapping[str, object]:
    """Resolve an explicit payload or serialize a manifest (default when both None)."""

    if payload is not None:
        return payload
    return cast(
        Mapping[str, object],
        backend_manifest_payload(manifest or default_factory()),
    )


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


def declared_capability_evidence(
    payload: Mapping[str, object],
    requirements: Mapping[str, tuple[str, ...]],
    passed_evidence_refs: Iterable[str],
) -> tuple[dict[str, tuple[str, ...]], tuple[str, ...]]:
    """Split declared affirmative surfaces into evidenced and gap pointers.

    A surface is evidenced when its required refs are all present in
    ``passed_evidence_refs``; every other declared affirmative surface is a gap.
    """

    passed = set(passed_evidence_refs)
    pointers = affirmative_capability_pointers(payload)
    evidence: dict[str, tuple[str, ...]] = {}
    for pointer in pointers:
        required = requirements.get(pointer)
        if required is not None and set(required) <= passed:
            evidence[pointer] = required
    gaps = tuple(pointer for pointer in pointers if pointer not in evidence)
    return evidence, gaps


__all__ = [
    "affirmative_capability_pointers",
    "backend_conformance_payload",
    "declared_capability_evidence",
    "escape_pointer_token",
    "manifest_payload",
]
