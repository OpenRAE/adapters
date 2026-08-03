"""Backend-neutral manifest capability-evidence composition.

Backends attest their affirmative manifest capability surfaces the same way:
enumerate the affirmative capability pointers in the manifest payload, and admit
each one that a passed executable probe backs. The traversal and the
passed-probe accounting are mechanical and RAES-payload-shaped; the probe
requirement map and the evidence-ref identities stay backend-local.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import cast

from raes_contracts.diagnostics import (  # type: ignore[import-untyped]
    Diagnostic,
    diagnostic_model,
)

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


def manifest_capability_evidence(
    payload: Mapping[str, object],
    *,
    probe_requirements: Mapping[str, tuple[str, ...]],
    passed_evidence_refs: Iterable[str],
) -> dict[str, tuple[str, ...]]:
    """Return evidence references for declared affirmative manifest surfaces."""

    passed = set(passed_evidence_refs)
    evidence: dict[str, tuple[str, ...]] = {}
    for pointer in affirmative_capability_pointers(payload):
        requirements = probe_requirements.get(pointer)
        if requirements is not None and set(requirements) <= passed:
            evidence[pointer] = requirements
    return evidence


def manifest_capability_evidence_gaps(
    payload: Mapping[str, object],
    *,
    probe_requirements: Mapping[str, tuple[str, ...]],
    passed_evidence_refs: Iterable[str],
) -> tuple[str, ...]:
    """Return declared affirmative capability surfaces with no probe evidence."""

    evidence = manifest_capability_evidence(
        payload,
        probe_requirements=probe_requirements,
        passed_evidence_refs=passed_evidence_refs,
    )
    return tuple(
        pointer for pointer in affirmative_capability_pointers(payload) if pointer not in evidence
    )


def passed_probe_evidence_refs(
    conformance_report: object | None,
    source_diagnostics: Iterable[Diagnostic],
    *,
    backend_conformance_evidence: str,
    source_protocol_evidence: str,
    source_validation_failed_code: str,
) -> tuple[str, ...]:
    """Return evidence refs only for executable probes that passed."""

    refs: list[str] = []
    if _conformance_passed(conformance_report):
        refs.append(backend_conformance_evidence)
    source_models = [diagnostic_model(diagnostic) for diagnostic in source_diagnostics]
    if source_models and all(
        model.code != source_validation_failed_code for model in source_models
    ):
        refs.append(source_protocol_evidence)
    return tuple(refs)


def _conformance_passed(conformance_report: object | None) -> bool:
    """Return whether a conformance report passed with no gaps or failed cases."""

    if conformance_report is None:
        return False
    return bool(
        getattr(conformance_report, "passed", False)
        and not getattr(conformance_report, "unsupported_contract_gaps", ())
        and not getattr(conformance_report, "unsupported_capability_gaps", ())
        and all(case.passed for case in getattr(conformance_report, "cases", ()))
    )


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
    "manifest_capability_evidence",
    "manifest_capability_evidence_gaps",
    "passed_probe_evidence_refs",
]
