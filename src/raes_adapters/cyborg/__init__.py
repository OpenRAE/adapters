"""CybORG backend-local qualification evidence.

Issue #12 binds one immutable CAGE-2 source closure and its qualification
outcome here.  The record and packaging-only patch are evidence; they do not
implement an adapter, backend manifest, conformance profile, RAES semantic
model, or native-state serializer.

The native simulator is deliberately not imported by this module.  The current
qualification is fail-closed because no governed public artifact contains the
required packaging fix, so base-only installations remain independent.
"""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any, cast

__all__ = ["load_qualification", "read_compatibility_patch"]


def load_qualification() -> dict[str, Any]:
    """Load a fresh copy of the selected CAGE-2 qualification record."""
    resource = files(__package__).joinpath("qualification.json")
    return cast(dict[str, Any], json.loads(resource.read_text(encoding="utf-8")))


def read_compatibility_patch() -> str:
    """Read the qualification-only packaging patch verbatim."""
    resource = files(__package__).joinpath("cage2-wheel-package-data.patch")
    return resource.read_text(encoding="utf-8")
